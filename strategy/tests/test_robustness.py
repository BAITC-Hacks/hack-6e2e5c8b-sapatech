"""Regression checks for pooled evidence and focused pilot confirmation."""

import unittest

import pandas as pd

from strategy import build_candidates, choose_pilot
from strategy.core import _channels, _estimate, _observations


CHANNELS = {
    "push": {"cost_per_contact": 0, "conversion_multiplier": 0.5},
    "sms": {"cost_per_contact": 4, "conversion_multiplier": 0.65},
    "digital_ads": {"cost_per_contact": 22, "conversion_multiplier": 0.85},
}


def observation(candidate, ratio, n=200, channel="push"):
    request = {"target_tariff": candidate["target_tariff"], "channel": channel,
               "n_customers": n, **candidate["filters"]}
    return {"candidate_id": candidate["candidate_id"], "request": request,
            "result": {"target_tariff": request["target_tariff"],
                       "channel": channel, "n_customers": n,
                       "observed_lift_ratio": ratio}}


class RobustnessTests(unittest.TestCase):
    def setUp(self):
        self.profile = pd.DataFrame({
            "ID_NUMBER": range(1000),
            "current_tariff": ["tariff_1"] * 1000,
            "arpu_segment": ["HIGH"] * 1000,
            "predicted_arpu": [6000.] * 1000,
        })
        self.tariffs = pd.DataFrame({
            "tariff_plan_code": ["tariff_1", "tariff_2", "tariff_3"]})
        self.candidates = build_candidates(self.profile, self.tariffs, pd.DataFrame())
        self.candidate = self.candidates[0]
        self.resources = {
            "remaining_budget": 100000, "remaining_contacts": 15000,
            "pilots_left": 20, "seconds_left": 240,
            "max_campaigns": 10, "max_customers_per_campaign": 5000,
        }

    def estimate(self, channel, observations):
        return _estimate(self.candidate, channel, _channels(CHANNELS),
                         _observations(observations))

    def test_splitting_a_source_sample_preserves_transferred_estimate(self):
        combined = [observation(self.candidate, 0.1)]
        split = [observation(self.candidate, 0.1, n=100),
                 observation(self.candidate, 0.1, n=100)]
        for channel in CHANNELS:
            with self.subTest(channel=channel):
                for whole, parts in zip(self.estimate(channel, combined),
                                        self.estimate(channel, split)):
                    self.assertAlmostEqual(whole, parts, places=12)

    def test_mixed_sign_source_samples_are_pooled_before_saturation_cap(self):
        # These are the same 200-person mean. The arbitrary partition must not
        # change the channel-transfer estimate or its uncertainty.
        combined = [observation(self.candidate, 0.1)]
        split = [observation(self.candidate, 0.4, n=100),
                 observation(self.candidate, -0.2, n=100)]
        for channel in ("push", "digital_ads"):
            with self.subTest(channel=channel):
                for whole, parts in zip(self.estimate(channel, combined),
                                        self.estimate(channel, split)):
                    self.assertAlmostEqual(whole, parts, places=12)

    def test_direct_evidence_converges_to_observed_channel_effect(self):
        observations = [observation(self.candidate, 0.4) for _ in range(20)]
        mean, error = self.estimate("push", observations)
        # A push observation already includes the 0.5 channel multiplier.
        # Applying it again would converge to 0.2 instead of 0.4.
        self.assertGreater(mean, 0.35)
        self.assertLess(mean, 0.4)
        self.assertLess(error, 0.02)

    def test_source_repeats_cannot_erase_transfer_uncertainty(self):
        few = [observation(self.candidate, 0.1) for _ in range(2)]
        many = [observation(self.candidate, 0.1) for _ in range(20)]
        _, direct_few = self.estimate("push", few)
        _, direct_many = self.estimate("push", many)
        _, transferred_few = self.estimate("digital_ads", few)
        _, transferred_many = self.estimate("digital_ads", many)
        self.assertLess(direct_many, 0.4 * direct_few)
        self.assertGreater(transferred_many, 0.65 * transferred_few)
        self.assertGreater(transferred_many, 2 * direct_many)

    def test_direct_paid_feedback_can_reverse_inferred_positive_effect(self):
        push = [observation(self.candidate, 0.15) for _ in range(10)]
        paid = [observation(self.candidate, -0.2, channel="digital_ads")
                for _ in range(5)]
        inferred_mean, inferred_error = self.estimate("digital_ads", push)
        measured_mean, measured_error = self.estimate("digital_ads", push + paid)
        self.assertGreater(inferred_mean, 0)
        self.assertLess(measured_mean, 0)
        self.assertLess(measured_error, inferred_error)

    def test_confirmation_precedes_an_unobserved_alternative_after_exploration(self):
        # Same audience and neutral history for both candidates. The unobserved
        # alternative has a larger optimistic bound, but the promising sampled
        # candidate needs confirmation, including beyond two full-size pilots.
        for n in (20, 50, 75):
            with self.subTest(total_observed=8 * n):
                observations = [observation(self.candidate, 0.05, n=n)
                                for _ in range(8)]
                resources = dict(self.resources, pilots_left=12,
                                 remaining_contacts=15000 - 8 * n)
                pilot = choose_pilot(self.profile, self.tariffs, CHANNELS,
                                     self.candidates, observations, resources)
                self.assertIsNotNone(pilot)
                self.assertEqual(pilot["candidate_id"], self.candidate["candidate_id"])
                self.assertTrue(10 <= pilot["request"]["n_customers"] <= 200)

    def test_sufficiently_confirmed_candidate_stops_consuming_pilots(self):
        observations = [observation(self.candidate, 0.05, n=100)
                        for _ in range(8)]
        resources = dict(self.resources, pilots_left=12, remaining_contacts=14200)
        self.assertIsNone(choose_pilot(
            self.profile, self.tariffs, CHANNELS, [self.candidate],
            observations, resources))

    def test_small_cohort_stops_after_crossing_confirmation_threshold(self):
        profile = self.profile.iloc[:197]
        candidate = build_candidates(profile, self.tariffs, pd.DataFrame())[0]
        observations = [observation(candidate, 0.05, n=197) for _ in range(4)]
        resources = dict(self.resources, pilots_left=16, remaining_contacts=14212)
        pilot = choose_pilot(profile, self.tariffs, CHANNELS, [candidate],
                             observations, resources)
        self.assertIsNotNone(pilot)
        n = pilot["request"]["n_customers"]
        self.assertTrue(10 <= n <= len(profile))
        # The policy uses 800 as a stop threshold, not an exact sample cap:
        # a partial-sized cohort can cross it on its last requested pilot.
        self.assertGreaterEqual(4 * 197 + n, 800)
        observations.append(observation(candidate, 0.05, n=n))
        resources["remaining_contacts"] -= n
        resources["pilots_left"] -= 1
        self.assertGreaterEqual(resources["remaining_contacts"], 10000)
        self.assertIsNone(choose_pilot(profile, self.tariffs, CHANNELS,
                                      [candidate], observations, resources))

    def test_confirmation_respects_resource_and_time_limits(self):
        observations = [observation(self.candidate, 0.05, n=50)
                        for _ in range(8)]
        resources = dict(self.resources, pilots_left=12, remaining_contacts=14600)
        for unavailable in ({"pilots_left": 0}, {"seconds_left": 20},
                            {"remaining_contacts": 20}):
            with self.subTest(unavailable=unavailable):
                self.assertIsNone(choose_pilot(
                    self.profile, self.tariffs, CHANNELS, self.candidates,
                    observations, dict(resources, **unavailable)))
        free = choose_pilot(self.profile, self.tariffs, CHANNELS, self.candidates,
                            observations, dict(resources, remaining_budget=0))
        self.assertEqual(free["request"]["channel"], "push")
        sms = {"sms": CHANNELS["sms"]}
        paid_observations = [observation(self.candidate, 0.05, n=50, channel="sms")
                             for _ in range(8)]
        self.assertIsNone(choose_pilot(
            self.profile, self.tariffs, sms, self.candidates, paid_observations,
            dict(resources, remaining_budget=100)))
        limited = choose_pilot(
            self.profile, self.tariffs, sms, self.candidates, paid_observations,
            dict(resources, remaining_budget=1000))
        self.assertTrue(10 <= limited["request"]["n_customers"] <= 25)


if __name__ == "__main__":
    unittest.main()
