"""Compare two agents on the same official mock seeds without altering scorer.

The output contains only aggregate metrics. Mock results are not hidden-score
predictions. Run raw contract and feedback checks separately before comparison.
"""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import statistics
import sys
from time import perf_counter

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evals.check_agent import load_agent


def evaluate(path: Path, package_dir: Path, seeds: range) -> dict:
    old_cwd, old_path = Path.cwd(), sys.path[:]
    rows = []
    try:
        os.chdir(package_dir)
        sys.path.insert(0, str(path.parent))
        sys.path.insert(0, str(package_dir))
        from local_eval import evaluate_agent
        for seed in seeds:
            agent = load_agent(path)
            output = io.StringIO()
            start = perf_counter()
            with redirect_stdout(output):
                result = evaluate_agent(agent, seed=seed, verbose=False)
            runtime = perf_counter() - start
            messages = output.getvalue()
            rows.append({
                "seed": seed,
                "net_arpu_gain": result["net_arpu_gain"] if result else None,
                "total_cost": result["total_cost"] if result else None,
                "total_contacts": result["total_contacts"] if result else None,
                "pilots": result["n_pilots"] if result else None,
                "runtime_seconds": round(runtime, 3),
                "warnings": [line for line in messages.splitlines() if "[!]" in line],
            })
    finally:
        sys.path[:] = old_path
        os.chdir(old_cwd)
    good = [row for row in rows if row["net_arpu_gain"] is not None]
    net = [row["net_arpu_gain"] for row in good]
    return {
        "runs": rows,
        "summary": {
            "completed": len(good), "requested": len(rows),
            "mean_net": statistics.mean(net) if net else None,
            "median_net": statistics.median(net) if net else None,
            "minimum_net": min(net) if net else None,
            "maximum_net": max(net) if net else None,
            "spread_net": max(net) - min(net) if net else None,
            "positive_runs": sum(value > 0 for value in net),
            "mean_cost": statistics.mean(row["total_cost"] for row in good) if good else None,
            "mean_contacts": statistics.mean(row["total_contacts"] for row in good) if good else None,
            "mean_pilots": statistics.mean(row["pilots"] for row in good) if good else None,
            "mean_runtime_seconds": statistics.mean(row["runtime_seconds"] for row in rows),
            "maximum_runtime_seconds": max(row["runtime_seconds"] for row in rows),
            "warning_runs": sum(bool(row["warnings"]) for row in rows),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-agent", type=Path, required=True)
    parser.add_argument("--candidate-agent", type=Path, required=True)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=10)
    args = parser.parse_args()
    if not 1 <= args.runs <= 100:
        parser.error("--runs must be between 1 and 100")
    package_dir = args.package.resolve()
    baseline = args.baseline_agent.resolve()
    candidate = args.candidate_agent.resolve()
    if not package_dir.is_dir() or not baseline.is_file() or not candidate.is_file():
        parser.error("package directory and both agent files must exist")
    seeds = range(args.runs)
    report = {
        "seeds": list(seeds),
        "baseline": evaluate(baseline, package_dir, seeds),
        "candidate": evaluate(candidate, package_dir, seeds),
    }
    b, c = report["baseline"]["summary"], report["candidate"]["summary"]
    report["delta_mean_net"] = (
        c["mean_net"] - b["mean_net"]
        if c["mean_net"] is not None and b["mean_net"] is not None else None
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(b["completed"] != args.runs or c["completed"] != args.runs or
               b["warning_runs"] > 0 or c["warning_runs"] > 0)


if __name__ == "__main__":
    raise SystemExit(main())
