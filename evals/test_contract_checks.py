"""Focused regression checks for the independent raw-answer verifier."""

import unittest

import pandas as pd

from evals.contract_checks import check_raw_answer
from evals.public_stub import PublicPilotStub


def sample_env(observed_ratio=0.2, total_budget=100_000):
    profile = pd.DataFrame({
        "ID_NUMBER": range(1, 41),
        "current_tariff": ["tariff_1"] * 40,
        "arpu_segment": ["HIGH"] * 20 + ["MID"] * 20,
        "data_segment": ["HEAVY"] * 40,
        "call_segment": ["LOW"] * 40,
        "predicted_arpu": [0.0] + [1000.0] * 38 + [float("nan")],
    })
    tariffs = pd.DataFrame({"tariff_plan_code": ["tariff_1", "tariff_2", "tariff_3"]})
    channels = {
        "push": {"cost_per_contact": 0, "conversion_multiplier": 0.5},
        "sms": {"cost_per_contact": 4, "conversion_multiplier": 0.65},
        "call": {"cost_per_contact": 160, "conversion_multiplier": 1.2},
    }
    return PublicPilotStub(profile, tariffs, channels, observed_ratio,
                           total_budget=total_budget)


def one_campaign(**changes):
    campaign = {
        "campaign_name": "demo", "filter_arpu_segment": "HIGH",
        "target_tariff": "tariff_2", "channel": "sms",
    }
    campaign.update(changes)
    return campaign


class RawContractTests(unittest.TestCase):
    def test_valid_answer_with_zero_and_missing_arpu(self):
        env = sample_env()
        env.run_pilot("tariff_2", "push", 10, filter_arpu_segment="HIGH")
        result = check_raw_answer([one_campaign()], env)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual((result.pilot_contacts, result.final_contacts), (10, 20))
        self.assertEqual((result.pilot_cost, result.final_cost), (0, 80))

    def test_raw_excess_is_not_hidden_by_sanitizer(self):
        env = sample_env()
        env.run_pilot("tariff_2", "push", 10)
        result = check_raw_answer([one_campaign()] * 11, env)
        self.assertFalse(result.ok)
        self.assertTrue(any("raw campaign count" in e for e in result.errors))

    def test_invalid_filters_tariff_channel_and_unsupported_key(self):
        env = sample_env()
        env.run_pilot("tariff_2", "push", 10)
        result = check_raw_answer([one_campaign(
            filter_arpu_segment="VIP", filter_current_tariff="tariff_99",
            target_tariff="tariff_99", channel="email", explicit_ids=[1],
        )], env)
        self.assertFalse(result.ok)
        self.assertGreaterEqual(len(result.errors), 5)

    def test_final_budget_and_repeated_contacts(self):
        env = sample_env(total_budget=100)
        env.run_pilot("tariff_2", "push", 10)
        result = check_raw_answer([one_campaign(channel="call")], env)
        self.assertFalse(result.ok)
        self.assertTrue(any("no contacts" in e for e in result.errors))

        env = sample_env()
        env.run_pilot("tariff_2", "push", 10)
        result = check_raw_answer([one_campaign(), one_campaign(campaign_name="again")], env)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.repeated_final_contacts, 20)

    def test_feedback_changes_a_public_agent_decision(self):
        class FeedbackAgent:
            def act(self, env):
                pilot = env.run_pilot("tariff_2", "push", 10)
                target = "tariff_2" if pilot["observed_lift_ratio"] > 0 else "tariff_3"
                return [one_campaign(target_tariff=target)]

        positive, negative = sample_env(0.5), sample_env(-0.5)
        pos_answer = FeedbackAgent().act(positive)
        neg_answer = FeedbackAgent().act(negative)
        self.assertNotEqual(pos_answer, neg_answer)
        self.assertTrue(check_raw_answer(pos_answer, positive).ok)
        self.assertTrue(check_raw_answer(neg_answer, negative).ok)

    def test_empty_segment_and_exhausted_contacts(self):
        env = sample_env()
        env.run_pilot("tariff_2", "push", 10)
        empty = check_raw_answer([one_campaign(filter_current_tariff="tariff_3")], env)
        self.assertTrue(any("empty audience" in e for e in empty.errors))

        env = sample_env()
        env.max_total_contacts = env.remaining_contacts = 10
        env.run_pilot("tariff_2", "push", 10)
        exhausted = check_raw_answer([one_campaign()], env)
        self.assertTrue(any("no contacts" in e for e in exhausted.errors))

    def test_zero_baseline_and_negative_pilot_observation(self):
        env = sample_env(observed_ratio=-0.4)
        env.customer_profile["predicted_arpu"] = 0.0
        pilot = env.run_pilot("tariff_2", "push", 10)
        self.assertEqual(pilot["observed_lift_total"], 0.0)
        result = check_raw_answer([one_campaign()], env)
        self.assertTrue(result.ok, result.errors)

    def test_audience_above_campaign_cap_is_reported(self):
        env = sample_env()
        expanded = pd.concat([env.customer_profile] * 126, ignore_index=True)
        expanded["ID_NUMBER"] = range(1, len(expanded) + 1)
        env.customer_profile = expanded
        env.run_pilot("tariff_2", "push", 10)
        result = check_raw_answer([one_campaign(filter_arpu_segment=None)], env)
        self.assertTrue(result.ok, result.errors)
        self.assertTrue(any("before the 5000 cap" in w for w in result.warnings))


if __name__ == "__main__":
    unittest.main()
