"""Optional local integration harness; run from an extracted official package.

PYTHONPATH=/path/to/repository python /path/to/repository/strategy/tests/official_smoke.py --runs 10
Uses the official evaluator unchanged; no private environment inspection.
"""

import argparse
import json
from pathlib import Path
import sys
import time

import pandas as pd

from strategy import build_candidates, choose_pilot, select_campaigns


class StrategyAdapter:
    """Test-only wrapper; root agent.py remains the integrator's responsibility."""

    def act(self, env):
        start = time.monotonic()
        profile, tariffs = env.customer_profile, env.tariffs
        history = pd.read_csv("data/change_tariff.csv")
        candidates = build_candidates(profile, tariffs, history)
        observations = []
        while True:
            resources = {"remaining_budget": env.remaining_budget,
                         "remaining_contacts": env.remaining_contacts,
                         "pilots_left": env.pilots_left,
                         "seconds_left": 240 - (time.monotonic() - start),
                         "max_campaigns": 10, "max_customers_per_campaign": 5000}
            pilot = choose_pilot(profile, tariffs, env.channels, candidates, observations, resources)
            if pilot is None:
                break
            result = env.run_pilot(**pilot["request"])
            observations.append({**pilot, "result": result})
        campaigns = select_campaigns(profile, tariffs, env.channels, candidates, observations, resources)
        from scoring_core import apply_filters, sanitize_campaigns, validate_strategy
        assert 1 <= len(campaigns) <= 10
        assert sanitize_campaigns(campaigns, tariffs) == campaigns
        validate_strategy(pd.DataFrame(campaigns), tariffs)
        budget, contacts = env.remaining_budget, env.remaining_contacts
        for campaign in campaigns:
            n = min(len(apply_filters(profile, campaign)), 5000, contacts)
            cost = env.channels[campaign["channel"]]["cost_per_contact"]
            if cost:
                n = min(n, int(budget // cost))
            assert n > 0
            contacts -= n
            budget -= n * cost
        assert contacts >= 0 and budget >= 0 and observations
        self.campaigns = campaigns
        self.observations = observations
        self.elapsed = time.monotonic() - start
        assert self.elapsed < 300
        return campaigns


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=1)
    args = parser.parse_args()
    sys.path.insert(0, str(Path.cwd()))
    from local_eval import evaluate_agent
    results = []
    for seed in ([42] if args.runs == 1 else range(args.runs)):
        adapter = StrategyAdapter()
        result = evaluate_agent(adapter, seed=seed, verbose=False)
        assert result is not None and hasattr(adapter, "campaigns"), "adapter failed"
        assert result["total_contacts"] <= 15000 and result["total_cost"] <= 100000
        assert 1 <= result["n_pilots"] <= 20
        results.append(result["net_arpu_gain"])
        print(json.dumps({"seed": seed, "net_gain": result["net_arpu_gain"],
                          "contacts": result["total_contacts"], "cost": result["total_cost"],
                          "pilots": result["n_pilots"], "campaigns": len(adapter.campaigns),
                          "seconds": round(adapter.elapsed, 3)}), flush=True)
    # Repeat the last seed and compare both decisions and public pilot observations.
    repeat = StrategyAdapter()
    evaluate_agent(repeat, seed=seed, verbose=False)
    assert adapter.campaigns == repeat.campaigns
    assert adapter.observations == repeat.observations
    print(json.dumps({"repeatable": True, "min": min(results), "max": max(results),
                      "median": float(pd.Series(results).median())}))


if __name__ == "__main__":
    main()
