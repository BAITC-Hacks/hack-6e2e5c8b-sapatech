import copy
import math
import unittest

import pandas as pd

from strategy import build_candidates, choose_pilot, select_campaigns
from strategy.core import _estimate, _observations


CHANNELS = {
    "push": {"cost_per_contact": 0, "conversion_multiplier": 0.5},
    "sms": {"cost_per_contact": 4, "conversion_multiplier": 0.65},
    "digital_ads": {"cost_per_contact": 22, "conversion_multiplier": 0.85},
    "call": {"cost_per_contact": 160, "conversion_multiplier": 1.2},
}


def observation(candidate, ratio, channel="push", n=200):
    request = {"target_tariff": candidate["target_tariff"], "channel": channel,
               "n_customers": n, **candidate["filters"]}
    return {"candidate_id": candidate["candidate_id"], "request": request,
            "result": {"target_tariff": request["target_tariff"], "channel": channel,
                       "n_customers": n, "observed_lift_ratio": ratio}}


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.profile = pd.DataFrame({
            "ID_NUMBER": list(range(1199, -1, -1)),
            "current_tariff": ["tariff_1"] * 600 + ["tariff_2"] * 600,
            "arpu_segment": ["HIGH"] * 600 + ["LOW"] * 600,
            "predicted_arpu": [6000.] * 600 + [500.] * 600,
        })
        self.tariffs = pd.DataFrame({"tariff_plan_code": ["tariff_1", "tariff_2", "tariff_3"]})
        self.resources = {"remaining_budget": 100000, "remaining_contacts": 15000,
                          "pilots_left": 20, "seconds_left": 240,
                          "max_campaigns": 10, "max_customers_per_campaign": 5000}
        self.candidates = build_candidates(self.profile, self.tariffs, pd.DataFrame())

    def test_history_zero_denominators_and_finite_candidates(self):
        history = pd.DataFrame({
            "AVG_ARPU_PREV_3M": [0, -1, float("nan"), 6000, 6000],
            "AVG_ARPU_NEXT_3M": [500, 500, 500, 9000, float("inf")],
            "tariff_plan_code_from": ["tariff_1"] * 5,
            "tariff_plan_code_to": ["tariff_3"] * 5})
        result = build_candidates(self.profile, self.tariffs, history)
        candidate = next(c for c in result if c["target_tariff"] == "tariff_3"
                         and c["filters"]["filter_current_tariff"] == "tariff_1")
        self.assertEqual(candidate["history_count"], 1)
        self.assertGreater(candidate["prior_change_ratio"], 0)
        for c in result:
            for key in ("prior_change_ratio", "audience_arpu_sum", "priority"):
                self.assertTrue(math.isfinite(c[key]))

    def test_empty_history_neutral_and_no_mutation(self):
        before = self.profile.copy(deep=True)
        candidates = copy.deepcopy(self.candidates)
        resources = dict(self.resources)
        first = choose_pilot(self.profile, self.tariffs, CHANNELS, candidates, [], resources)
        second = choose_pilot(self.profile, self.tariffs, CHANNELS, candidates, [], resources)
        self.assertEqual(first, second)
        self.assertTrue(all(c["prior_change_ratio"] == 0 for c in candidates))
        self.assertEqual(self.candidates, candidates)
        self.assertEqual(self.resources, resources)
        pd.testing.assert_frame_equal(before, self.profile)
        self.assertNotEqual(first["request"]["target_tariff"], first["request"]["filter_current_tariff"])

    def test_invalid_profile_diagnostic(self):
        with self.assertRaisesRegex(ValueError, "predicted_arpu"):
            build_candidates(self.profile.drop(columns="predicted_arpu"), self.tariffs, pd.DataFrame())
        invalid = self.profile.copy()
        invalid.loc[0, "predicted_arpu"] = float("inf")
        with self.assertRaisesRegex(ValueError, "finite"):
            build_candidates(invalid, self.tariffs, pd.DataFrame())

    def test_missing_segment_and_zero_arpu(self):
        profile = self.profile.copy()
        profile.loc[:10, "arpu_segment"] = None
        profile["predicted_arpu"] = 0.
        candidates = build_candidates(profile, self.tariffs, pd.DataFrame())
        self.assertTrue(any("filter_arpu_segment" not in c["filters"] for c in candidates))
        result = select_campaigns(profile, self.tariffs, CHANNELS, candidates, [], self.resources)
        self.assertEqual(len(result), 1)

    def test_pilot_limits_and_reserved_contacts(self):
        for changes in ({"pilots_left": 0}, {"seconds_left": 20}, {"remaining_contacts": 20}):
            self.assertIsNone(choose_pilot(self.profile, self.tariffs, CHANNELS,
                                          self.candidates, [], dict(self.resources, **changes)))
        resources = dict(self.resources, remaining_contacts=100, remaining_budget=0)
        pilot = choose_pilot(self.profile, self.tariffs, CHANNELS, self.candidates, [], resources)
        self.assertEqual(pilot["request"]["channel"], "push")
        self.assertTrue(10 <= pilot["request"]["n_customers"] <= 30)

    def test_observations_change_target_and_research(self):
        candidates = [c for c in self.candidates if c["filters"]["filter_current_tariff"] == "tariff_1"]
        a, b = candidates
        for positive, negative in ((a, b), (b, a)):
            observations = [observation(positive, 0.8, n=60), observation(negative, -0.8, n=60)]
            campaigns = select_campaigns(self.profile, self.tariffs, CHANNELS, candidates,
                                         observations, dict(self.resources, max_campaigns=1))
            self.assertEqual(campaigns[0]["target_tariff"], positive["target_tariff"])
            pilot = choose_pilot(self.profile, self.tariffs, CHANNELS, candidates, observations, self.resources)
            self.assertEqual(pilot["candidate_id"], positive["candidate_id"])

    def test_same_channel_pilot_not_multiplied_twice(self):
        candidate = self.candidates[0]
        obs = [observation(candidate, 0.4)] * 10
        mean, error = _estimate(candidate, "push", {"push": (0, 0.5)}, _observations(obs))
        self.assertGreater(mean, 0.39)
        self.assertLess(mean, 0.4)
        self.assertLess(error, 0.02)

    def test_actual_sample_size_and_failed_observations(self):
        candidate = self.candidates[0]
        obs = observation(candidate, 0.5, n=10)
        obs["request"]["n_customers"] = 200
        valid = _observations([obs, {"candidate_id": "failed", "request": {}, "result": {"error": "failed"}}])
        self.assertEqual(valid[candidate["candidate_id"]][0][1], 10)
        self.assertNotIn("failed", valid)

    def test_paid_channels_and_budget(self):
        candidate = self.candidates[0]
        observed = [observation(candidate, 0.8, n=60)]
        for budget in (0, 100, 100000):
            resources = dict(self.resources, remaining_budget=budget, remaining_contacts=25, max_campaigns=1)
            result = select_campaigns(self.profile, self.tariffs, CHANNELS, [candidate], observed, resources)
            cost = CHANNELS[result[0]["channel"]]["cost_per_contact"]
            n = min(25, candidate["audience_n"], int(budget // cost) if cost else 25)
            self.assertLessEqual(n * cost, budget)
            if budget == 0:
                self.assertEqual(result[0]["channel"], "push")
            if budget == 100000:
                self.assertNotEqual(result[0]["channel"], "push")

    def test_overlap_not_counted_twice_and_negative_fallback(self):
        candidate = self.candidates[0]
        clone = copy.deepcopy(candidate)
        clone["candidate_id"] = "equivalent"
        observations = [observation(candidate, 0.8, n=60), observation(clone, 0.8, n=60)]
        push = {"push": CHANNELS["push"]}
        result = select_campaigns(self.profile, self.tariffs, push, [candidate, clone], observations, self.resources)
        self.assertEqual(len(result), 1)
        negative = [observation(c, -0.8, n=60) for c in self.candidates]
        result = select_campaigns(self.profile, self.tariffs, push, self.candidates, negative, self.resources)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["filter_current_tariff"], "tariff_2")

    def test_final_schema_and_determinism(self):
        result = select_campaigns(self.profile, self.tariffs, CHANNELS, self.candidates, [], self.resources)
        self.assertEqual(result, select_campaigns(self.profile, self.tariffs, CHANNELS, self.candidates, [], self.resources))
        for campaign in result:
            self.assertFalse({"candidate_id", "n_customers", "explicit_ids"} & campaign.keys())
            self.assertIn(campaign["target_tariff"], set(self.tariffs.tariff_plan_code))
        shuffled = self.profile.sample(frac=1, random_state=42)
        self.assertEqual(self.candidates, build_candidates(shuffled, self.tariffs, pd.DataFrame()))

    def test_id_order_and_campaign_cap_affect_selection(self):
        # Group 1 has high total ARPU but its first ten IDs have little value.
        profile = self.profile.copy()
        profile["predicted_arpu"] = 1000.
        profile.loc[profile.current_tariff == "tariff_1", "predicted_arpu"] = 10000.
        profile.loc[profile.ID_NUMBER.between(600, 609), "predicted_arpu"] = 0.
        candidates = build_candidates(profile, self.tariffs, pd.DataFrame())
        observations = [observation(c, 0.5, n=10) for c in candidates]
        result = select_campaigns(profile, self.tariffs, {"push": CHANNELS["push"]},
                                  candidates, observations,
                                  dict(self.resources, max_customers_per_campaign=10, max_campaigns=1))
        self.assertEqual(result[0]["filter_current_tariff"], "tariff_2")

    def test_confirmation_after_exploration(self):
        a, b = self.candidates[:2]
        observations = [observation(a, 0.4, n=10)] * 10
        pilot = choose_pilot(self.profile, self.tariffs, CHANNELS, [a, b], observations, self.resources)
        self.assertEqual(pilot["candidate_id"], a["candidate_id"])

    def test_full_pilot_loop_preserves_final_resources(self):
        observations = []
        resources = dict(self.resources)
        while True:
            pilot = choose_pilot(self.profile, self.tariffs, CHANNELS, self.candidates, observations, resources)
            if pilot is None:
                break
            request = pilot["request"]
            n = request["n_customers"]
            self.assertTrue(10 <= n <= 200)
            resources["remaining_contacts"] -= n
            resources["remaining_budget"] -= n * CHANNELS[request["channel"]]["cost_per_contact"]
            resources["pilots_left"] -= 1
            observations.append({**pilot, "result": {"target_tariff": request["target_tariff"],
                                "channel": request["channel"], "n_customers": n,
                                "observed_lift_ratio": 0.2}})
            self.assertLessEqual(len(observations), 20)
        self.assertGreaterEqual(resources["remaining_contacts"], 10000)
        self.assertGreaterEqual(resources["remaining_budget"], 0)


if __name__ == "__main__":
    unittest.main()
