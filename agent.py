"""Public Beeline agent orchestration. Statistical policy belongs to strategy/."""

from __future__ import annotations

from copy import deepcopy
from importlib import import_module
import math
from numbers import Integral, Real
from pathlib import Path
from time import monotonic

import pandas as pd

FILTERS = {
    "filter_arpu_segment": ("arpu_segment", {"LOW", "MID", "HIGH"}),
    "filter_data_segment": ("data_segment", {"NON_USER", "LITE", "HEAVY"}),
    "filter_call_segment": ("call_segment", {"LOW", "MEDIUM", "HIGH"}),
    "filter_current_tariff": ("current_tariff", None),
}
CAMPAIGN_KEYS = {"campaign_name", "target_tariff", "channel", *FILTERS}
PILOT_KEYS = {"target_tariff", "channel", "n_customers", *FILTERS}
ROOT = Path(__file__).resolve().parent


class ContractError(ValueError):
    """A policy returned an invalid request or campaign list."""


def _number(value, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ContractError(f"{label} must be a finite number")
    return float(value)


class _PilotSession:
    """Validated public facade for the official template and our orchestration."""

    def __init__(self, env, deadline: float, diagnostics: dict):
        self._env = env
        self.deadline = deadline
        self.diagnostics = diagnostics
        self.observations: list[dict] = []
        self.customer_profile = env.customer_profile.copy(deep=True)
        self.tariffs = env.tariffs.copy(deep=True)
        self.channels = deepcopy(env.channels)
        required = {"ID_NUMBER", "predicted_arpu", "current_tariff", "arpu_segment",
                    "data_segment", "call_segment"}
        if not required.issubset(self.customer_profile.columns):
            raise ContractError(f"Missing profile columns: {sorted(required - set(self.customer_profile.columns))}")
        if "tariff_plan_code" not in self.tariffs:
            raise ContractError("Missing tariffs.tariff_plan_code")
        self.tariff_codes = set(self.tariffs["tariff_plan_code"].dropna())
        self.attempts = 0

    @property
    def remaining_budget(self):
        return self._env.remaining_budget

    @property
    def remaining_contacts(self):
        return self._env.remaining_contacts

    @property
    def pilots_left(self):
        return self._env.pilots_left

    @property
    def pilot_history(self):
        return deepcopy(self._env.pilot_history)

    def seconds_left(self):
        return max(0.0, self.deadline - monotonic())

    def resources(self):
        budget = _number(self.remaining_budget, "remaining_budget")
        contacts = _number(self.remaining_contacts, "remaining_contacts")
        pilots = _number(self.pilots_left, "pilots_left")
        if min(budget, contacts, pilots) < 0 or contacts != int(contacts) or pilots != int(pilots):
            raise ContractError("Invalid public resource counters")
        return {"remaining_budget": budget, "remaining_contacts": int(contacts),
                "pilots_left": int(pilots), "seconds_left": self.seconds_left(),
                "max_campaigns": 10, "max_customers_per_campaign": 5000}

    def segment(self, campaign):
        result = self.customer_profile
        for key, (column, _) in FILTERS.items():
            value = campaign.get(key)
            if value is None:
                continue
            if key == "filter_current_tariff":
                result = result[result[column].isin([t.strip() for t in value.split(";")])]
            else:
                result = result[result[column] == value]
        return result

    def validate(self, campaign, *, pilot=False):
        if not isinstance(campaign, dict):
            raise ContractError("Campaign/request must be a dict")
        allowed = PILOT_KEYS if pilot else CAMPAIGN_KEYS
        if set(campaign) - allowed:
            raise ContractError(f"Unexpected fields: {sorted(set(campaign) - allowed)}")
        target, channel = campaign.get("target_tariff"), campaign.get("channel")
        if not isinstance(target, str) or target not in self.tariff_codes:
            raise ContractError("Unknown target_tariff")
        if not isinstance(channel, str) or channel not in self.channels:
            raise ContractError("Unknown channel")
        if "campaign_name" in campaign and not isinstance(campaign["campaign_name"], str):
            raise ContractError("campaign_name must be a string")
        for key, (_, valid) in FILTERS.items():
            value = campaign.get(key)
            if value is None:
                continue
            if not isinstance(value, str):
                raise ContractError(f"{key} must be a string or None")
            if key == "filter_current_tariff":
                tokens = [t.strip() for t in value.split(";")]
                if not tokens or any(not t or t not in self.tariff_codes for t in tokens):
                    raise ContractError("Invalid current tariff filter")
            elif value not in valid:
                raise ContractError(f"Invalid {key}")
        cost = _number(self.channels[channel]["cost_per_contact"], "cost_per_contact")
        if cost < 0:
            raise ContractError("Negative channel cost")
        count = len(self.segment(campaign))
        if count == 0:
            raise ContractError("Campaign selects no customers")
        if pilot:
            n = campaign.get("n_customers", 100)
            if isinstance(n, bool) or not isinstance(n, Integral) or not 10 <= n <= 200:
                raise ContractError("n_customers must be an integer in [10, 200]")
        return count, cost

    def run_pilot(self, candidate_id=None, **request):
        self.attempts += 1
        if self.attempts > 23 or self.pilots_left <= 0:
            raise RuntimeError("Pilot attempt limit exhausted")
        if self.seconds_left() <= 15:
            raise TimeoutError("Preserving time for final selection")
        count, price = self.validate(request, pilot=True)
        resources = self.resources()
        expected = min(int(request.get("n_customers", 100)), count, resources["remaining_contacts"])
        if price:
            expected = min(expected, int(resources["remaining_budget"] // price))
        if expected <= 0 or expected >= resources["remaining_contacts"]:
            raise ContractError("Pilot cannot run while preserving a final contact")
        result = self._env.run_pilot(**request)
        if not isinstance(result, dict):
            raise ContractError("Pilot result must be a dict")
        n = _number(result.get("n_customers"), "pilot n_customers")
        cost = _number(result.get("cost"), "pilot cost")
        _number(result.get("observed_lift_ratio"), "observed_lift_ratio")
        _number(result.get("observed_lift_total"), "observed_lift_total")
        if n != int(n) or not 1 <= n <= expected or not math.isclose(cost, n * price, abs_tol=1e-6):
            raise ContractError("Inconsistent pilot count or cost")
        after = self.resources()
        if (not math.isclose(resources["remaining_budget"] - after["remaining_budget"], cost, abs_tol=1e-6)
                or resources["remaining_contacts"] - after["remaining_contacts"] != int(n)
                or resources["pilots_left"] - after["pilots_left"] != 1):
            raise ContractError("Pilot counters do not match result")
        self.observations.append({"candidate_id": candidate_id,
                                  "request": deepcopy(request), "result": deepcopy(result)})
        return result

    def validate_final(self, campaigns):
        if not isinstance(campaigns, list) or not 1 <= len(campaigns) <= 10:
            raise ContractError("Expected 1-10 raw final campaigns")
        resources = self.resources()
        budget, contacts = resources["remaining_budget"], resources["remaining_contacts"]
        total_cost = total_contacts = 0
        for campaign in campaigns:
            count, price = self.validate(campaign)
            n = min(count, 5000, contacts)
            if price:
                n = min(n, int(budget // price))
            if n <= 0:
                raise ContractError("Final campaign has no remaining reach or budget")
            contacts -= n
            budget -= n * price
            total_contacts += n
            total_cost += n * price
        self.diagnostics["final_contacts"] = total_contacts
        self.diagnostics["final_cost"] = total_cost
        self.diagnostics["remaining_after_final"] = {"contacts": contacts, "budget": budget}
        return deepcopy(campaigns)


class Agent:
    def __init__(self, strategy=None, history_path=None, time_limit_seconds=270):
        self._strategy = strategy
        self.history_path = Path(history_path) if history_path is not None else None
        self.time_limit_seconds = min(270.0, max(1.0, float(time_limit_seconds)))
        self.diagnostics: dict = {}

    def _error(self, stage, error):
        self.diagnostics["errors"].append({"stage": stage, "type": type(error).__name__, "message": str(error)[:300]})

    def _history(self):
        # Official runners read package data relative to cwd, which may differ
        # from the imported agent's directory (for example evals/check_agent.py).
        package_history = Path.cwd() / "data/change_tariff.csv"
        history_path = self.history_path
        if history_path is None:
            history_path = package_history if package_history.is_file() else ROOT / "data/change_tariff.csv"
        try:
            return pd.read_csv(history_path)
        except (OSError, ValueError) as error:
            self._error("history", error)
            return pd.DataFrame()

    def _policy(self):
        if self._strategy is not None:
            return self._strategy
        try:
            return import_module("strategy")
        except ModuleNotFoundError as error:
            if error.name != "strategy":
                raise
            return None

    def _strategy_run(self, policy, session):
        profile, tariffs, channels = session.customer_profile, session.tariffs, session.channels
        candidates = policy.build_candidates(profile.copy(deep=True), tariffs.copy(deep=True), self._history())
        if not isinstance(candidates, list) or not candidates:
            raise ContractError("Strategy returned no candidates")
        by_id = {c["candidate_id"]: c for c in candidates}
        if len(by_id) != len(candidates) or any(not isinstance(k, str) for k in by_id):
            raise ContractError("Candidate IDs must be unique strings")
        failures = 0
        while session.pilots_left > 0 and session.seconds_left() > 15 and session.attempts < 23:
            try:
                decision = policy.choose_pilot(profile.copy(deep=True), tariffs.copy(deep=True),
                                               deepcopy(channels), deepcopy(candidates),
                                               deepcopy(session.observations), session.resources())
                if decision is None:
                    break
                if not isinstance(decision, dict) or set(decision) != {"candidate_id", "request"}:
                    raise ContractError("Invalid pilot decision envelope")
                candidate_id, request = decision["candidate_id"], decision["request"]
                if candidate_id not in by_id or not isinstance(request, dict):
                    raise ContractError("Unknown pilot candidate or invalid request")
                candidate = by_id[candidate_id]
                if request.get("target_tariff") != candidate["target_tariff"] or any(
                    request.get(key) != candidate["filters"].get(key) for key in FILTERS
                ):
                    raise ContractError("Pilot request differs from its candidate")
                session.run_pilot(candidate_id=candidate_id, **request)
                failures = 0
            except Exception as error:
                self._error("pilot", error)
                failures += 1
                if failures >= 3 or isinstance(error, TimeoutError):
                    break
        if not session.observations:
            raise ContractError("Strategy produced no successful pilot")
        if session.seconds_left() <= 0:
            raise TimeoutError("No time left for strategy selection")
        final = policy.select_campaigns(profile.copy(deep=True), tariffs.copy(deep=True),
                                        deepcopy(channels), deepcopy(candidates),
                                        deepcopy(session.observations), session.resources())
        return session.validate_final(final)

    def _recover(self, session):
        # Minimal recovery from measured actions; never invent a new statistical policy.
        observations = sorted(session.observations,
                              key=lambda item: item["result"]["observed_lift_ratio"], reverse=True)
        for observation in observations:
            campaign = {key: value for key, value in observation["request"].items() if key in CAMPAIGN_KEYS}
            campaign["campaign_name"] = "pilot_recovery"
            try:
                result = session.validate_final([campaign])
                self.diagnostics["mode"] = "pilot-recovery"
                return result
            except ContractError:
                continue
        raise ContractError("No feasible campaign can be recovered from successful pilots")

    def act(self, env) -> list[dict]:
        started = monotonic()
        self.diagnostics = {"mode": "strategy", "errors": []}
        session = _PilotSession(env, started + self.time_limit_seconds, self.diagnostics)
        try:
            try:
                policy = self._policy()
                if policy is not None:
                    return self._strategy_run(policy, session)
                self.diagnostics["mode"] = "official-template"
            except Exception as error:
                self._error("strategy", error)
                if session.observations:
                    return self._recover(session)
                self.diagnostics["mode"] = "official-template"
            try:
                template = import_module("agent_template")
                final = template.Agent().act(session)
                if not session.observations:
                    raise ContractError("Official template produced no successful pilot")
                return session.validate_final(final)
            except Exception as error:
                self._error("template", error)
                return self._recover(session)
        finally:
            self.diagnostics["elapsed_seconds"] = monotonic() - started
            self.diagnostics["pilots"] = len(session.observations)
            self.diagnostics["pilot_attempts"] = session.attempts
            self.diagnostics["observations"] = deepcopy(session.observations)
