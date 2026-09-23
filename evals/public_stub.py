"""Small public-only environment for independent pilot feedback checks.

It intentionally has no hidden impact model or scoring internals. The caller
chooses the observed lift; the same request is otherwise deterministic.
"""

from __future__ import annotations

import pandas as pd

from .contract_checks import _filter_audience


class PublicPilotStub:
    def __init__(self, customer_profile: pd.DataFrame, tariffs: pd.DataFrame,
                 channels: dict, observed_ratio: float,
                 total_budget: float = 100_000, max_total_contacts: int = 15_000):
        self.customer_profile = customer_profile.copy()
        self.tariffs = tariffs.copy()
        self.channels = dict(channels)
        self.total_budget = total_budget
        self.max_total_contacts = max_total_contacts
        self.remaining_budget = total_budget
        self.remaining_contacts = max_total_contacts
        self.pilots_left = 20
        self.pilot_history = []
        self.observed_ratio = observed_ratio
        self.requests = []

    def run_pilot(self, target_tariff, channel, n_customers=100,
                  filter_arpu_segment=None, filter_data_segment=None,
                  filter_call_segment=None, filter_current_tariff=None):
        if self.pilots_left <= 0:
            raise RuntimeError("no pilots left")
        if target_tariff not in set(self.tariffs["tariff_plan_code"]):
            raise ValueError("unknown tariff")
        if channel not in self.channels:
            raise ValueError("unknown channel")
        n_customers = max(10, min(int(n_customers), 200))
        request = {
            "target_tariff": target_tariff, "channel": channel,
            "n_customers": n_customers,
            "filter_arpu_segment": filter_arpu_segment,
            "filter_data_segment": filter_data_segment,
            "filter_call_segment": filter_call_segment,
            "filter_current_tariff": filter_current_tariff,
        }
        audience = _filter_audience(self.customer_profile, request)
        cost_each = self.channels[channel]["cost_per_contact"]
        affordable = self.remaining_contacts
        if cost_each:
            affordable = min(affordable, int(self.remaining_budget // cost_each))
        n_actual = min(n_customers, len(audience), affordable)
        if n_actual <= 0:
            raise RuntimeError("empty audience or exhausted resources")
        picked = audience.iloc[:n_actual]
        cost = n_actual * cost_each
        self.remaining_budget -= cost
        self.remaining_contacts -= n_actual
        self.pilots_left -= 1
        self.requests.append(request)
        result = {
            "pilot": f"pilot_{len(self.pilot_history) + 1}",
            "target_tariff": target_tariff,
            "channel": channel,
            "n_customers": n_actual,
            "cost": cost,
            "observed_lift_ratio": self.observed_ratio,
            "observed_lift_total": self.observed_ratio * picked["predicted_arpu"].sum(),
            "remaining_budget": self.remaining_budget,
            "remaining_contacts": self.remaining_contacts,
        }
        self.pilot_history.append(result)
        return result
