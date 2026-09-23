"""Independent checks for the public Beeline Agent.act contract.

This module deliberately receives only public environment attributes. It does
not sanitize, truncate, score, or change the agent's answer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import pandas as pd


FILTER_VALUES = {
    "filter_arpu_segment": {"LOW", "MID", "HIGH"},
    "filter_data_segment": {"NON_USER", "LITE", "HEAVY"},
    "filter_call_segment": {"LOW", "MEDIUM", "HIGH"},
}
FILTER_COLUMNS = {
    "filter_arpu_segment": "arpu_segment",
    "filter_data_segment": "data_segment",
    "filter_call_segment": "call_segment",
}
ALLOWED_KEYS = {
    "campaign_name", "target_tariff", "channel", "filter_current_tariff",
    *FILTER_VALUES,
}
MAX_CAMPAIGNS = 10
MAX_CUSTOMERS_PER_CAMPAIGN = 5_000
MAX_PILOTS = 20
MIN_PILOT_CUSTOMERS = 10
MAX_PILOT_CUSTOMERS = 200


@dataclass
class CheckResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    final_contacts: int = 0
    final_cost: float = 0.0
    repeated_final_contacts: int = 0
    pilot_contacts: int = 0
    pilot_cost: float = 0.0

    @property
    def ok(self) -> bool:
        return not self.errors


def _finite_number(value: object) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _known_key(value: object, known: set | dict) -> bool:
    try:
        return value in known
    except TypeError:
        return False


def _filter_audience(profile: pd.DataFrame, campaign: dict) -> pd.DataFrame:
    audience = profile
    for key, column in FILTER_COLUMNS.items():
        value = campaign.get(key)
        if value is not None and not pd.isna(value):
            audience = audience[audience[column] == value]
    tariff_filter = campaign.get("filter_current_tariff")
    if tariff_filter is not None and not pd.isna(tariff_filter):
        wanted = [part.strip() for part in tariff_filter.split(";") if part.strip()]
        audience = audience[audience["current_tariff"].isin(wanted)]
    return audience.sort_values("ID_NUMBER")


def check_raw_answer(campaigns: object, env: object) -> CheckResult:
    """Check the unsanitized answer and account for pilots already executed.

    Campaign contact/cost accounting uses the official order and caps. The
    campaign schema has no requested audience size, so an audience above 5000
    or partially served by resources is a planning warning, not invalid JSON.
    Pilot customer IDs are not public, so overlap with pilots is not asserted.
    """
    result = CheckResult()
    if not isinstance(campaigns, list):
        result.errors.append("Agent.act must return a list")
        return result
    if not 1 <= len(campaigns) <= MAX_CAMPAIGNS:
        result.errors.append(f"raw campaign count is {len(campaigns)}; expected 1..10")

    profile = getattr(env, "customer_profile", None)
    tariffs = getattr(env, "tariffs", None)
    channels = getattr(env, "channels", None)
    if not isinstance(profile, pd.DataFrame) or not isinstance(tariffs, pd.DataFrame):
        result.errors.append("public customer_profile/tariffs DataFrames are missing")
        return result
    if not isinstance(channels, dict):
        result.errors.append("public channels dictionary is missing")
        return result
    required_profile = {"ID_NUMBER", "current_tariff", *FILTER_COLUMNS.values()}
    if not required_profile.issubset(profile.columns):
        result.errors.append(f"profile missing {sorted(required_profile - set(profile.columns))}")
        return result
    if "tariff_plan_code" not in tariffs.columns:
        result.errors.append("tariffs missing tariff_plan_code")
        return result
    known_tariffs = set(tariffs["tariff_plan_code"].dropna())

    pilot_history = getattr(env, "pilot_history", None)
    if not isinstance(pilot_history, list):
        result.errors.append("public pilot_history is missing")
        return result
    if not 1 <= len(pilot_history) <= MAX_PILOTS:
        result.errors.append(f"pilot count is {len(pilot_history)}; expected 1..20")
    for index, pilot in enumerate(pilot_history, 1):
        if not isinstance(pilot, dict):
            result.errors.append(f"pilot {index} is not a public result dict")
            continue
        n, cost = pilot.get("n_customers"), pilot.get("cost")
        if not isinstance(n, (int, float)) or not _finite_number(n) or int(n) != n:
            result.errors.append(f"pilot {index} has invalid n_customers")
            continue
        n = int(n)
        if not MIN_PILOT_CUSTOMERS <= n <= MAX_PILOT_CUSTOMERS:
            result.errors.append(f"pilot {index} reached {n}; expected 10..200")
        result.pilot_contacts += n
        if not _finite_number(cost) or float(cost) < 0:
            result.errors.append(f"pilot {index} has invalid cost")
        else:
            result.pilot_cost += float(cost)
        if not _known_key(pilot.get("target_tariff"), known_tariffs):
            result.errors.append(f"pilot {index} has unknown target tariff")
        if not _known_key(pilot.get("channel"), channels):
            result.errors.append(f"pilot {index} has unknown channel")
        if not _finite_number(pilot.get("observed_lift_ratio")):
            result.errors.append(f"pilot {index} has invalid observed_lift_ratio")

    remaining_contacts = getattr(env, "remaining_contacts", None)
    remaining_budget = getattr(env, "remaining_budget", None)
    total_contacts = getattr(env, "max_total_contacts", 15_000)
    total_budget = getattr(env, "total_budget", 100_000)
    if not all(_finite_number(x) for x in (remaining_contacts, remaining_budget,
                                           total_contacts, total_budget)):
        result.errors.append("public resource counters are missing or non-finite")
        return result
    remaining_contacts = int(remaining_contacts)
    remaining_budget = float(remaining_budget)
    total_contacts = int(total_contacts)
    total_budget = float(total_budget)
    if remaining_contacts < 0 or remaining_budget < -1e-6:
        result.errors.append("pilot execution exceeded a resource limit")
    if result.pilot_contacts > total_contacts or result.pilot_cost > total_budget + 1e-6:
        result.errors.append("pilot totals exceed original resource limits")
    if total_contacts - remaining_contacts != result.pilot_contacts:
        result.errors.append("pilot contact total disagrees with env.remaining_contacts")
    if not math.isclose(total_budget - remaining_budget, result.pilot_cost, abs_tol=1e-6):
        result.errors.append("pilot cost total disagrees with env.remaining_budget")
    pilots_left = getattr(env, "pilots_left", None)
    if pilots_left is not None and pilots_left != MAX_PILOTS - len(pilot_history):
        result.errors.append("pilot count disagrees with env.pilots_left")

    seen_ids: set = set()
    for index, campaign in enumerate(campaigns, 1):
        label = f"campaign {index}"
        if not isinstance(campaign, dict):
            result.errors.append(f"{label} is not a dict")
            continue
        extras = set(campaign) - ALLOWED_KEYS
        if extras:
            result.errors.append(f"{label} has unsupported keys {sorted(extras)}")
        target, channel = campaign.get("target_tariff"), campaign.get("channel")
        if not _known_key(target, known_tariffs):
            result.errors.append(f"{label} has unknown target tariff {target!r}")
        if not _known_key(channel, channels):
            result.errors.append(f"{label} has unknown channel {channel!r}")
        for key, allowed in FILTER_VALUES.items():
            value = campaign.get(key)
            if value is not None and not _known_key(value, allowed):
                result.errors.append(f"{label} has invalid {key}={value!r}")
        tariff_filter = campaign.get("filter_current_tariff")
        if tariff_filter is not None:
            if not isinstance(tariff_filter, str):
                result.errors.append(f"{label} has non-string filter_current_tariff")
            else:
                listed = [part.strip() for part in tariff_filter.split(";") if part.strip()]
                if not listed or set(listed) - known_tariffs:
                    result.errors.append(f"{label} has invalid filter_current_tariff")
        if result.errors and any(error.startswith(label) for error in result.errors):
            continue

        audience = _filter_audience(profile, campaign)
        if audience.empty:
            result.errors.append(f"{label} has an empty audience")
            continue
        if len(audience) > MAX_CUSTOMERS_PER_CAMPAIGN:
            result.warnings.append(f"{label} reaches {len(audience)} before the 5000 cap")
        selected = audience.iloc[:MAX_CUSTOMERS_PER_CAMPAIGN]
        selected = selected.iloc[:max(remaining_contacts - result.final_contacts, 0)]
        cost_per_contact = channels[channel].get("cost_per_contact")
        if not _finite_number(cost_per_contact) or float(cost_per_contact) < 0:
            result.errors.append(f"{label} has invalid channel cost")
            continue
        cost_per_contact = float(cost_per_contact)
        if cost_per_contact:
            affordable = int(max(remaining_budget - result.final_cost, 0) // cost_per_contact)
            selected = selected.iloc[:affordable]
        if selected.empty:
            result.errors.append(f"{label} would reach no contacts after resource caps")
        elif len(selected) < min(len(audience), MAX_CUSTOMERS_PER_CAMPAIGN):
            result.warnings.append(f"{label} would be truncated by remaining resources")
        ids = set(selected["ID_NUMBER"])
        result.repeated_final_contacts += len(ids & seen_ids)
        seen_ids.update(ids)
        result.final_contacts += len(selected)
        result.final_cost += len(selected) * cost_per_contact

    if result.repeated_final_contacts:
        result.warnings.append(
            f"{result.repeated_final_contacts} repeated final contacts spend resources but do not duplicate lift"
        )
    if result.final_contacts + result.pilot_contacts > total_contacts:
        result.errors.append("pilot + final contacts exceed total limit")
    if result.final_cost + result.pilot_cost > total_budget + 1e-6:
        result.errors.append("pilot + final cost exceeds total budget")
    return result
