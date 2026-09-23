"""Pure campaign planning: no environment access, files, or random state."""

import json
import math
from collections import defaultdict

import numpy as np
import pandas as pd


FILTERS = {
    "filter_arpu_segment": "arpu_segment",
    "filter_data_segment": "data_segment",
    "filter_call_segment": "call_segment",
    "filter_current_tariff": "current_tariff",
}
SEGMENTS = {"LOW", "MID", "HIGH"}
# Sampling noise is documented by the public environment, not fitted to mock effects.
PILOT_STD = 0.804


def _profile(profile, tariffs):
    required = {"ID_NUMBER", "current_tariff", "arpu_segment", "predicted_arpu"}
    missing = required - set(profile.columns)
    if missing:
        raise ValueError(f"profile missing required columns: {sorted(missing)}")
    if "tariff_plan_code" not in tariffs:
        raise ValueError("tariffs missing required column: tariff_plan_code")
    if profile.ID_NUMBER.isna().any() or profile.ID_NUMBER.duplicated().any():
        raise ValueError("profile ID_NUMBER must be non-null and unique")
    result = profile.sort_values("ID_NUMBER").reset_index(drop=True).copy()
    arpu = pd.to_numeric(result.predicted_arpu, errors="coerce")
    if not np.isfinite(arpu).all():
        raise ValueError("profile predicted_arpu must contain finite numbers")
    result["predicted_arpu"] = arpu
    return result


def _positions(profile, filters):
    mask = np.ones(len(profile), dtype=bool)
    for key, value in filters.items():
        if value is None:
            continue
        if key not in FILTERS:
            raise ValueError(f"unknown filter: {key}")
        col = FILTERS[key]
        if col not in profile:
            raise ValueError(f"profile missing filter column: {col}")
        if key == "filter_current_tariff":
            match = profile[col].isin([s.strip() for s in str(value).split(";")])
        else:
            match = profile[col].eq(value).fillna(False)
        mask &= match.to_numpy(dtype=bool)
    return np.flatnonzero(mask)


def _history(history):
    """Exclude invalid denominators; robust, bounded ratios prevent tiny-ARPU leverage."""
    columns = {"AVG_ARPU_PREV_3M", "AVG_ARPU_NEXT_3M",
               "tariff_plan_code_from", "tariff_plan_code_to"}
    if history.empty:
        return {}, {}
    if not columns.issubset(history.columns):
        raise ValueError(f"history missing required columns: {sorted(columns - set(history.columns))}")
    frame = history.copy()
    before = pd.to_numeric(frame.AVG_ARPU_PREV_3M, errors="coerce")
    after = pd.to_numeric(frame.AVG_ARPU_NEXT_3M, errors="coerce")
    good = np.isfinite(before) & np.isfinite(after) & (before > 0) & (after >= 0)
    frame = frame.loc[good].copy()
    before, after = before[good], after[good]
    frame["ratio"] = ((after - before) / before).clip(-1, 2)
    # Thresholds come from PARTICIPANT_GUIDE, not inferred hidden effect groups.
    frame["segment"] = np.where(before < 1000, "LOW", np.where(before <= 5000, "MID", "HIGH"))
    keys = ["tariff_plan_code_from", "tariff_plan_code_to"]
    def aggregate(cols):
        return {key: (len(group), float(group.ratio.median()))
                for key, group in frame.groupby(cols, sort=True)}
    return aggregate(keys + ["segment"]), aggregate(keys)


def _candidate_positions(profile, candidates):
    cohorts, result = {}, {}
    for candidate in candidates:
        key = json.dumps(candidate["filters"], sort_keys=True)
        if key not in cohorts:
            cohorts[key] = _positions(profile, candidate["filters"])
        result[candidate["candidate_id"]] = cohorts[key]
    return result


def build_candidates(profile, tariffs, history):
    """Current-tariff × ARPU cells, every different valid target, stable IDs."""
    profile = _profile(profile, tariffs)
    specific, pooled = _history(history)
    known = sorted(tariffs.tariff_plan_code.dropna().unique())
    candidates = []
    for current, cohort in profile.groupby("current_tariff", sort=True):
        if current not in known:
            continue
        cells = [(segment, cohort[cohort.arpu_segment == segment])
                 for segment in sorted(SEGMENTS)]
        # Missing/unknown ARPU labels cannot be expressed as an official filter.
        # A broader current-tariff candidate keeps these customers reachable.
        if (~cohort.arpu_segment.isin(SEGMENTS)).any():
            cells.append((None, cohort))
        for segment, cell in cells:
            if cell.empty:
                continue
            filters = {"filter_current_tariff": current}
            if segment is not None:
                filters["filter_arpu_segment"] = segment
            arpu_sum = float(cell.predicted_arpu.sum())
            for target in known:
                if target == current:
                    continue
                count, ratio = specific.get((current, target, segment),
                                           pooled.get((current, target), (0, 0.0)))
                # A neutral zero prior when history is absent; shrink small histories.
                prior = ratio * count / (count + 20)
                candidate_id = json.dumps([target, filters], sort_keys=True, separators=(",", ":"))
                candidates.append({
                    "candidate_id": candidate_id, "target_tariff": target,
                    "filters": dict(filters), "audience_n": len(cell),
                    "audience_arpu_sum": arpu_sum, "history_count": count,
                    "prior_change_ratio": float(prior),
                    "priority": float(max(arpu_sum, 0) * min(5000 / len(cell), 1)
                                      * (0.05 + 0.1 * prior)),
                })
    return sorted(candidates, key=lambda c: (-c["priority"], c["candidate_id"]))


def _channels(channels):
    result = {}
    for name in sorted(channels):
        if name not in {"push", "sms", "digital_ads", "call"}:
            continue
        cost = float(channels[name]["cost_per_contact"])
        multiplier = float(channels[name]["conversion_multiplier"])
        if math.isfinite(cost) and cost >= 0 and math.isfinite(multiplier) and multiplier > 0:
            result[name] = (cost, multiplier)
    if not result:
        raise ValueError("channels contains no valid official channel")
    return result


def _observations(observations):
    valid = defaultdict(list)
    for obs in observations:
        result, request = obs.get("result", {}), obs.get("request", {})
        try:
            ratio = float(result["observed_lift_ratio"])
            n = int(result["n_customers"])
            channel = result["channel"]
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if (math.isfinite(ratio) and 1 <= n <= 200
                and channel == request.get("channel")
                and result.get("target_tariff") == request.get("target_tariff")):
            valid[obs["candidate_id"]].append((channel, n, ratio))
    return valid


def _estimate(candidate, channel, channels, observations):
    """Weak historical prior, precision-weighted pilots, cautious channel transfer."""
    multiplier = channels[channel][1]
    mean = 0.1 * candidate["prior_change_ratio"] * multiplier
    precision = 1 / 0.15 ** 2
    weighted = mean * precision
    pooled = defaultdict(lambda: [0, 0.0])
    for source, n, ratio in observations.get(candidate["candidate_id"], []):
        if source in channels:
            pooled[source][0] += n
            pooled[source][1] += n * ratio
    for source, (n, total) in pooled.items():
        ratio = total / n
        factor = multiplier / channels[source][1]
        # Transfer error is shared by repeats; more source pilots cannot erase it.
        if ratio >= 0:
            factor = min(factor, 1.5)
        variance = PILOT_STD ** 2 / n * factor ** 2
        if source != channel:
            variance += (0.05 * abs(factor - 1) + 0.02) ** 2
        weighted += ratio * factor / variance
        precision += 1 / variance
    return weighted / precision, math.sqrt(1 / precision)


def _resources(resources):
    budget = float(resources["remaining_budget"])
    contacts = int(resources["remaining_contacts"])
    if not math.isfinite(budget) or budget < 0 or contacts < 0:
        raise ValueError("remaining budget/contacts must be finite and non-negative")
    return budget, contacts


def choose_pilot(profile, tariffs, channels, candidates, observations, resources):
    profile = _profile(profile, tariffs)
    channels = _channels(channels)
    budget, contacts = _resources(resources)
    if resources["pilots_left"] <= 0 or resources["seconds_left"] <= 20:
        return None
    observed = _observations(observations)
    spent = sum(n for rows in observed.values() for _, n, _ in rows)
    initial_contacts = contacts + spent
    reserve = max(1, min(10000, math.ceil(initial_contacts * 0.7)))
    available = contacts - reserve
    if available < 10:
        return None
    # Explore using the cheapest channel, preserving money for final allocation.
    channel = min(channels, key=lambda name: (channels[name][0], name))
    cost = channels[channel][0]
    if cost:
        available = min(available, int(budget * 0.1 // cost))
    if available < 10:
        return None
    cohort_trials = defaultdict(int)
    for candidate in candidates:
        cohort_trials[json.dumps(candidate["filters"], sort_keys=True)] += len(observed.get(candidate["candidate_id"], []))
    positions = _candidate_positions(profile, candidates)
    # Use at most eight initial pilots before prioritizing repeated evidence.
    # Four full samples halve the sampling error of a single 200-contact pilot.
    confirming = sum(len(rows) for rows in observed.values()) >= 8
    choices, confirmations = [], []
    for candidate in candidates:
        size = len(positions[candidate["candidate_id"]])
        if size < 10:
            continue
        evidence = observed.get(candidate["candidate_id"], [])
        n_seen = sum(n for _, n, _ in evidence)
        mean, error = _estimate(candidate, channel, channels, observed)
        if n_seen >= 800 or (evidence and mean + 1.64 * error <= 0):
            continue
        arpu = max(candidate["audience_arpu_sum"], 0) * min(5000 / size, 1)
        diversity = 1 + cohort_trials[json.dumps(candidate["filters"], sort_keys=True)]
        score = arpu * max(0, mean + 1.64 * error) / math.sqrt(diversity)
        n = min(200, size, available)
        if n >= 10:
            choices.append((-score, candidate["candidate_id"], candidate, int(n)))
            if evidence and mean > 0 and n_seen < 800:
                confirmation_score = arpu * (mean + error)
                confirmations.append((-confirmation_score, candidate["candidate_id"], candidate, int(n)))
    if confirming and confirmations:
        choices = confirmations
    if not choices:
        return None
    _, _, candidate, n = min(choices, key=lambda item: item[:2])
    return {"candidate_id": candidate["candidate_id"], "request": {
        "target_tariff": candidate["target_tariff"], "channel": channel,
        "n_customers": n, **candidate["filters"],
    }}


def select_campaigns(profile, tariffs, channels, candidates, observations, resources):
    profile = _profile(profile, tariffs)
    channels = _channels(channels)
    budget, contacts = _resources(resources)
    maximum = min(10, max(0, int(resources["max_campaigns"])))
    cap = min(5000, max(0, int(resources["max_customers_per_campaign"])))
    if not candidates or profile.empty or maximum == 0 or cap == 0:
        raise ValueError("no feasible final campaign: empty candidates/audience or zero campaign limits")
    observed = _observations(observations)
    arpu = profile.predicted_arpu.to_numpy(dtype=float)
    positions = _candidate_positions(profile, candidates)
    # Expected pilot coverage, never claimed to be known individual pilot IDs.
    pilot_probability = np.zeros(len(profile))
    pilot_best = np.zeros(len(profile))
    for candidate in candidates:
        ids = positions[candidate["candidate_id"]]
        if not len(ids):
            continue
        for channel, n, _ in observed.get(candidate["candidate_id"], []):
            if channel not in channels:
                continue
            mean, _ = _estimate(candidate, channel, channels, observed)
            probability = min(n / len(ids), 1)
            pilot_probability[ids] = 1 - (1 - pilot_probability[ids]) * (1 - probability)
            pilot_best[ids] = np.maximum(pilot_best[ids], mean * arpu[ids])
    best = np.zeros(len(profile))
    touched = np.zeros(len(profile), dtype=bool)
    selected, used = [], set()
    estimates = {(c["candidate_id"], channel): _estimate(c, channel, channels, observed)
                 for c in candidates for channel in channels}
    for _ in range(maximum):
        options = []
        for candidate in candidates:
            cid = candidate["candidate_id"]
            for channel, (cost, _) in channels.items():
                if (cid, channel) in used:
                    continue
                reachable = min(cap, contacts)
                if cost:
                    reachable = min(reachable, int(budget // cost))
                ids = positions[cid][:reachable]
                if not len(ids):
                    continue
                mean, error = estimates[cid, channel]
                ratio = mean - 0.5 * error
                lift = ratio * arpu[ids]
                # For untouched customers negative effects are real, not clipped to zero.
                gain_without_pilot = np.where(touched[ids], np.maximum(lift - best[ids], 0), lift)
                previous_with_pilot = np.where(touched[ids], np.maximum(best[ids], pilot_best[ids]), pilot_best[ids])
                gain_with_pilot = np.maximum(lift - previous_with_pilot, 0)
                gain = ((1 - pilot_probability[ids]) * gain_without_pilot
                        + pilot_probability[ids] * gain_with_pilot).sum() - len(ids) * cost
                options.append((-float(gain), cid, channel, candidate, ids, lift))
        if not options:
            break
        neg_gain, cid, channel, candidate, ids, lift = min(options, key=lambda item: item[:3])
        if selected and neg_gain >= 0:
            break
        selected.append({"campaign_name": f"c{len(selected) + 1:02d}",
                         "target_tariff": candidate["target_tariff"],
                         "channel": channel, **candidate["filters"]})
        used.add((cid, channel))
        best[ids] = np.where(touched[ids], np.maximum(best[ids], lift), lift)
        touched[ids] = True
        contacts -= len(ids)
        budget -= len(ids) * channels[channel][0]
    if not selected:
        # A legal declaration even if the caller has exhausted all execution resources.
        candidate = min(candidates, key=lambda c: (c["audience_n"], c["candidate_id"]))
        channel = min(channels, key=lambda name: (channels[name][0], name))
        selected = [{"campaign_name": "c01", "target_tariff": candidate["target_tariff"],
                     "channel": channel, **candidate["filters"]}]
    return selected
