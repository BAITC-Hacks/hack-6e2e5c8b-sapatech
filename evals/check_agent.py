"""Run raw-contract and public-feedback checks against an agent implementation.

Example from a directory containing the official participant package:
    python /path/to/repo/evals/check_agent.py --agent ./agent_template.py --package .
"""

from __future__ import annotations

import argparse
import importlib.util
import inspect
import json
import os
from pathlib import Path
import sys
from time import perf_counter

import pandas as pd

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evals.contract_checks import check_raw_answer
from evals.public_stub import PublicPilotStub


def load_agent(path: Path):
    spec = importlib.util.spec_from_file_location("evaluated_agent", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Agent()


def capture_pilot_requests(env) -> list[dict]:
    """Observe successful public calls without changing their results."""
    original = env.run_pilot
    signature = inspect.signature(original)
    requests = []

    def observed(*args, **kwargs):
        bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()
        answer = original(*args, **kwargs)
        requests.append(dict(bound.arguments))
        return answer

    env.run_pilot = observed
    return requests


def run_agent(agent_path: Path, package_dir: Path, seed: int, mode: str,
              observed_ratio: float = 0.0) -> dict:
    old_cwd = Path.cwd()
    old_path = sys.path[:]
    try:
        os.chdir(package_dir)
        sys.path.insert(0, str(agent_path.parent))
        sys.path.insert(0, str(package_dir))
        agent = load_agent(agent_path)
        if mode == "official":
            from mock_environment import make_mock_env
            env, _ = make_mock_env(seed=seed)
        else:
            from mock_environment import CHANNELS
            env = PublicPilotStub(
                pd.read_csv(package_dir / "customer_profile.csv"),
                pd.read_csv(package_dir / "data/dict_tariff.csv"),
                CHANNELS, observed_ratio,
            )
        pilot_requests = capture_pilot_requests(env)
        start = perf_counter()
        raw = agent.act(env)
        runtime = perf_counter() - start
        checked = check_raw_answer(raw, env, pilot_requests)
        return {
            "mode": mode, "seed": seed, "runtime_seconds": round(runtime, 3),
            "raw_campaign_count": len(raw) if isinstance(raw, list) else None,
            "pilots": len(env.pilot_history),
            "pilot_contacts": checked.pilot_contacts,
            "pilot_cost": checked.pilot_cost,
            "final_contacts": checked.final_contacts,
            "final_cost": checked.final_cost,
            "repeated_final_contacts": checked.repeated_final_contacts,
            "errors": checked.errors, "warnings": checked.warnings,
            "campaigns": raw,
        }
    finally:
        sys.path[:] = old_path
        os.chdir(old_cwd)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", type=Path, required=True)
    parser.add_argument("--package", type=Path, required=True,
                        help="local extracted official participant package")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--mode", choices=("official", "stub"), default="official")
    parser.add_argument("--feedback-check", action="store_true",
                        help="compare fixed +0.5 and -0.5 public pilot responses")
    args = parser.parse_args()
    agent_path, package_dir = args.agent.resolve(), args.package.resolve()
    if not agent_path.is_file() or not package_dir.is_dir():
        parser.error("--agent must be a file and --package an extracted directory")
    try:
        if args.feedback_check:
            positive = run_agent(agent_path, package_dir, args.seed, "stub", 0.5)
            negative = run_agent(agent_path, package_dir, args.seed, "stub", -0.5)
            changed = positive["campaigns"] != negative["campaigns"]
            output = {"feedback_changes_campaigns": changed,
                      "positive": positive, "negative": negative}
            ok = changed and not positive["errors"] and not negative["errors"]
        else:
            output = run_agent(agent_path, package_dir, args.seed, args.mode)
            ok = not output["errors"]
    except Exception as exc:
        output = {"error": f"{type(exc).__name__}: {exc}"}
        ok = False
    print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
