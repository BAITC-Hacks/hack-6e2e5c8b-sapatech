"""Focused T-03 orchestration tests; synthetic fixtures, no organizer data."""

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
import unittest

import pandas as pd

from agent import Agent, ContractError, _PilotSession


class PublicEnvironment:
    def __init__(self, size=40, contacts=100, budget=1000, lift=0.1):
        self.customer_profile = pd.DataFrame({
            "ID_NUMBER": range(size), "predicted_arpu": [100.0] * size,
            "current_tariff": ["tariff_1"] * size, "arpu_segment": ["HIGH"] * size,
            "data_segment": ["HEAVY"] * size, "call_segment": ["HIGH"] * size,
        })
        self.tariffs = pd.DataFrame({"tariff_plan_code": ["tariff_1", "tariff_2", "tariff_3"]})
        self.channels = {"push": {"cost_per_contact": 0, "conversion_multiplier": 0.5},
                         "sms": {"cost_per_contact": 4, "conversion_multiplier": 0.65}}
        self.remaining_contacts, self.remaining_budget = contacts, budget
        self.pilots_left, self.pilot_history, self.calls = 20, [], 0
        self.lift = lift

    def run_pilot(self, **request):
        self.calls += 1
        price = self.channels[request["channel"]]["cost_per_contact"]
        n = min(request.get("n_customers", 100), len(self.customer_profile), self.remaining_contacts)
        if price:
            n = min(n, int(self.remaining_budget // price))
        self.remaining_contacts -= n
        self.remaining_budget -= n * price
        self.pilots_left -= 1
        result = {"pilot": self.calls, "target_tariff": request["target_tariff"],
                  "channel": request["channel"], "n_customers": n, "cost": n * price,
                  "observed_lift_ratio": self.lift, "observed_lift_total": self.lift * n * 100,
                  "remaining_budget": self.remaining_budget, "remaining_contacts": self.remaining_contacts}
        self.pilot_history.append(result)
        return result


class Policy:
    def __init__(self):
        self.choices = []
        self.selection = None

    def build_candidates(self, profile, tariffs, history):
        self.history_rows = len(history)
        self.profile_rows = len(profile)
        return [{"candidate_id": "c1", "target_tariff": "tariff_2",
                 "filters": {"filter_arpu_segment": "HIGH"}}]

    def choose_pilot(self, profile, tariffs, channels, candidates, observations, resources):
        self.choices.append((deepcopy(observations), deepcopy(resources)))
        if observations:
            return None
        return {"candidate_id": "c1", "request": {"target_tariff": "tariff_2",
                "channel": "sms", "n_customers": 10, "filter_arpu_segment": "HIGH"}}

    def select_campaigns(self, profile, tariffs, channels, candidates, observations, resources):
        self.selection = (deepcopy(observations), deepcopy(resources))
        target = "tariff_2" if observations[0]["result"]["observed_lift_ratio"] > 0 else "tariff_3"
        return [{"target_tariff": target, "channel": "push", "filter_arpu_segment": "HIGH"}]


class AgentTests(unittest.TestCase):
    def session(self, env=None):
        return _PilotSession(env or PublicEnvironment(), monotonic() + 100, {})

    def test_observations_resources_and_history_reach_policy(self):
        policy, env = Policy(), PublicEnvironment()
        with TemporaryDirectory() as directory:
            history = Path(directory) / "history.csv"
            history.write_text("arpu_before,arpu_after\n10,12\n", encoding="utf-8")
            agent = Agent(strategy=policy, history_path=history)
            final = agent.act(env)
        self.assertEqual(policy.history_rows, 1)
        self.assertEqual(policy.profile_rows, 40)
        obs, resources = policy.selection
        self.assertEqual(obs[0]["candidate_id"], "c1")
        self.assertEqual(obs[0]["request"]["filter_arpu_segment"], "HIGH")
        self.assertEqual(resources["remaining_contacts"], 90)
        self.assertEqual(resources["remaining_budget"], 960)
        self.assertEqual(resources["pilots_left"], 19)
        self.assertEqual(policy.choices[1][0], obs)
        self.assertEqual(final[0]["target_tariff"], "tariff_2")
        self.assertEqual(agent.diagnostics["mode"], "strategy")

    def test_changed_public_pilot_changes_decision(self):
        positive = Agent(strategy=Policy()).act(PublicEnvironment(lift=0.2))
        negative = Agent(strategy=Policy()).act(PublicEnvironment(lift=-0.2))
        self.assertNotEqual(positive, negative)

    def test_actual_small_pilot_and_missing_history(self):
        policy = Policy()
        with TemporaryDirectory() as directory:
            agent = Agent(strategy=policy, history_path=Path(directory) / "missing.csv")
            agent.act(PublicEnvironment(size=5, contacts=20))
        self.assertEqual(policy.history_rows, 0)
        self.assertEqual(policy.selection[0][0]["result"]["n_customers"], 5)
        self.assertEqual(policy.selection[1]["remaining_contacts"], 15)
        self.assertEqual(agent.diagnostics["errors"][0]["stage"], "history")

    def test_invalid_requests_never_call_environment(self):
        base = {"target_tariff": "tariff_2", "channel": "push", "n_customers": 10}
        changes = [{"target_tariff": "unknown"}, {"channel": "email"},
                   {"n_customers": 9}, {"n_customers": 201}, {"n_customers": True},
                   {"filter_arpu_segment": "TYPO"}, {"explicit_ids": [1]},
                   {"filter_current_tariff": "tariff_1;missing"}]
        for change in changes:
            with self.subTest(change=change):
                env = PublicEnvironment()
                with self.assertRaises(ContractError):
                    self.session(env).run_pilot(**(base | change))
                self.assertEqual(env.calls, 0)

    def test_repeated_policy_errors_stop_after_three(self):
        class BrokenAfterPilot(Policy):
            def choose_pilot(self, *args):
                if args[-2]:
                    self.invalid_calls = getattr(self, "invalid_calls", 0) + 1
                    raise ValueError("broken policy")
                return super().choose_pilot(*args)
        policy = BrokenAfterPilot()
        agent = Agent(strategy=policy)
        agent.act(PublicEnvironment())
        self.assertEqual(policy.invalid_calls, 3)
        self.assertEqual(agent.diagnostics["pilots"], 1)

    def test_final_caps_and_repeated_contacts_charge_again(self):
        session = self.session(PublicEnvironment(size=12000, contacts=6000, budget=22000))
        final = [{"target_tariff": "tariff_2", "channel": "sms"},
                 {"target_tariff": "tariff_2", "channel": "push"}]
        session.validate_final(final)
        self.assertEqual(session.diagnostics["final_contacts"], 6000)
        self.assertEqual(session.diagnostics["final_cost"], 20000)
        self.assertEqual(session.diagnostics["remaining_after_final"], {"contacts": 0, "budget": 2000})
        with self.assertRaises(ContractError):
            session.validate_final(final + [{"target_tariff": "tariff_2", "channel": "push"}])

    def test_raw_final_output_not_silently_sanitized(self):
        session = self.session()
        campaign = {"target_tariff": "tariff_2", "channel": "push"}
        for value in [[], [campaign] * 11, [campaign | {"candidate_id": "private"}],
                      [campaign | {"filter_call_segment": "invalid"}]]:
            with self.subTest(value=value):
                with self.assertRaises(ContractError):
                    session.validate_final(value)

    def test_selection_error_recovers_from_observed_action(self):
        class BrokenSelection(Policy):
            def select_campaigns(self, *args):
                raise ValueError("selection broke")
        agent = Agent(strategy=BrokenSelection())
        final = agent.act(PublicEnvironment())
        self.assertEqual(agent.diagnostics["mode"], "pilot-recovery")
        self.assertEqual(final[0]["channel"], "sms")
        self.assertEqual(final[0]["target_tariff"], "tariff_2")

    def test_preserves_final_contact_and_time_reserve(self):
        env = PublicEnvironment(size=10, contacts=10)
        with self.assertRaises(ContractError):
            self.session(env).run_pilot(target_tariff="tariff_2", channel="push", n_customers=10)
        session = self.session(env)
        session.deadline = monotonic() + 10
        with self.assertRaises(TimeoutError):
            session.run_pilot(target_tariff="tariff_2", channel="push", n_customers=10)
        self.assertEqual(env.calls, 0)

    def test_malformed_result_is_not_an_observation(self):
        class MalformedEnvironment(PublicEnvironment):
            def run_pilot(self, **request):
                result = super().run_pilot(**request)
                result["observed_lift_ratio"] = float("nan")
                return result
        env = MalformedEnvironment()
        session = self.session(env)
        with self.assertRaises(ContractError):
            session.run_pilot(target_tariff="tariff_2", channel="push", n_customers=10)
        self.assertEqual(session.observations, [])
        self.assertEqual(env.remaining_contacts, 90)

    def test_policy_mutation_cannot_change_validation_or_environment(self):
        class MutatingPolicy(Policy):
            def choose_pilot(self, profile, tariffs, channels, candidates, observations, resources):
                result = super().choose_pilot(profile, tariffs, channels, candidates, observations, resources)
                profile["current_tariff"] = "tampered"
                channels["sms"]["cost_per_contact"] = 0
                candidates.clear()
                return result

            def select_campaigns(self, profile, tariffs, channels, candidates, observations, resources):
                self.observed_cost = channels["sms"]["cost_per_contact"]
                self.observed_tariff = profile.iloc[0]["current_tariff"]
                profile.drop(profile.index, inplace=True)
                return [{"target_tariff": "tariff_2", "channel": "sms"}]
        env, policy = PublicEnvironment(), MutatingPolicy()
        agent = Agent(strategy=policy)
        agent.act(env)
        self.assertEqual(policy.observed_cost, 4)
        self.assertEqual(policy.observed_tariff, "tariff_1")
        self.assertEqual(agent.diagnostics["final_cost"], 160)
        self.assertEqual(env.customer_profile.iloc[0]["current_tariff"], "tariff_1")
        self.assertEqual(env.channels["sms"]["cost_per_contact"], 4)


if __name__ == "__main__":
    unittest.main()
