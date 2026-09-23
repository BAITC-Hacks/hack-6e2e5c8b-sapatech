"""Paired public-interface evaluation in independent Python processes.

Each directory must contain agent.py, strategy/, the official participant
package and its data. Example (range stop is exclusive):
    python evals/compare_isolated.py --baseline-dir jobs/t10/baseline \
        --candidate-dir jobs/t10/candidate --seeds 0:20 --output jobs/t10/dev.json

The official evaluator is invoked unchanged. This harness never accesses its
hidden environment state. Mock comparisons do not predict the hidden score.
Non-finite ancillary metrics are encoded as "Infinity", "-Infinity" or "NaN";
non-finite required scores/resources still make a run invalid.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from dataclasses import asdict
import hashlib
import importlib
import importlib.util
import inspect
import io
import json
import math
from numbers import Real
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
from time import perf_counter


OFFICIAL_MODULES = ("local_eval", "environment", "mock_environment", "scoring_core",
                    "agent_template")
HARNESS_DIR = Path(__file__).resolve().parent


def parse_seeds(value: str) -> list[int]:
    """Accept comma-separated integers and half-open start:stop[:step] ranges."""
    seeds = []
    try:
        for part in value.split(","):
            numbers = [int(token) for token in part.split(":")]
            if len(numbers) == 1:
                seeds.extend(numbers)
            elif len(numbers) in (2, 3):
                seeds.extend(range(*numbers))
            else:
                raise ValueError("expected a seed or start:stop[:step]")
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid seeds: {value!r}: {exc}") from exc
    if not seeds or any(seed < 0 for seed in seeds) or len(set(seeds)) != len(seeds):
        raise argparse.ArgumentTypeError("seeds must be nonempty, nonnegative and unique")
    return seeds


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _harness_fingerprint() -> dict:
    return {"harness_sha256": _sha256(Path(__file__).resolve()),
            "validator_sha256": _sha256(HARNESS_DIR / "contract_checks.py")}


def manifest(directory: Path) -> dict:
    directory = directory.resolve(strict=True)
    for name in ("agent.py", "strategy/__init__.py", "local_eval.py", "customer_profile.csv"):
        if not (directory / name).is_file():
            raise ValueError(f"missing snapshot file: {directory / name}")
    if not (directory / "data").is_dir():
        raise ValueError(f"missing snapshot data directory: {directory / 'data'}")
    groups = {
        "agent_strategy": [directory / "agent.py", *sorted((directory / "strategy").rglob("*.py"))],
        "official": [directory / f"{name}.py" for name in OFFICIAL_MODULES
                     if (directory / f"{name}.py").is_file()],
        "data": [*sorted(directory.glob("*.csv")),
                 *sorted(path for path in (directory / "data").rglob("*") if path.is_file())],
    }
    # submission.csv is an output, not an input to the official evaluator.
    groups["data"] = [path for path in groups["data"] if path.name != "submission.csv"]
    answer = {}
    for group, paths in groups.items():
        for path in paths:
            if not path.resolve().is_relative_to(directory):
                raise ValueError(f"snapshot file escapes revision directory: {path}")
        hashes = {path.relative_to(directory).as_posix(): _sha256(path) for path in paths}
        answer[group] = {
            "files": hashes,
            "sha256": hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest(),
        }
    return answer


def _finite(value) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(value)


def distribution(values: list[float]) -> dict:
    if not values:
        return {key: None for key in ("mean", "median", "minimum", "maximum", "p10", "worst_10pct_mean")}
    ordered = sorted(values)
    position = (len(ordered) - 1) * 0.1
    lower = math.floor(position)
    p10 = ordered[lower] + (ordered[math.ceil(position)] - ordered[lower]) * (position - lower)
    return {
        "mean": statistics.mean(values), "median": statistics.median(values),
        "minimum": min(values), "maximum": max(values), "p10": p10,
        "worst_10pct_mean": statistics.mean(ordered[:max(1, math.ceil(len(values) * 0.1))]),
    }


def summarize(rows: list[dict]) -> dict:
    nets = [row["net_arpu_gain"] for row in rows if _finite(row.get("net_arpu_gain"))]
    return {
        "requested": len(rows), "completed": len(nets), "net": distribution(nets),
        "positive_runs": sum(value > 0 for value in nets),
        "losses": sum(value < 0 for value in nets), "zero_runs": sum(value == 0 for value in nets),
        "valid_runs": sum(row["valid"] for row in rows),
        "raw_error_runs": sum(bool(row.get("raw_errors")) for row in rows),
        "resource_error_runs": sum(bool(row.get("resource_errors")) for row in rows),
        "diagnostic_error_runs": sum(bool(row.get("diagnostic_errors")) for row in rows),
        "fallback_runs": sum(row.get("diagnostics", {}).get("mode") != "strategy" for row in rows),
        "runtime_seconds": distribution([row["runtime_seconds"] for row in rows]),
    }


def paired_summary(baseline: dict, candidate: dict) -> dict:
    if [row["seed"] for row in baseline["runs"]] != [row["seed"] for row in candidate["runs"]]:
        raise ValueError("baseline and candidate seed order differs")
    pairs = []
    for before, after in zip(baseline["runs"], candidate["runs"]):
        b, c = before.get("net_arpu_gain"), after.get("net_arpu_gain")
        pairs.append({"seed": before["seed"], "baseline_net": b, "candidate_net": c,
                      "delta_net": c - b if _finite(b) and _finite(c) else None,
                      "valid": before["valid"] and after["valid"]})
    deltas = [pair["delta_net"] for pair in pairs if _finite(pair["delta_net"])]
    b, c = baseline["summary"], candidate["summary"]
    all_valid = bool(pairs) and all(pair["valid"] for pair in pairs)
    return {
        "runs": pairs, "delta_net": distribution(deltas),
        "candidate_wins": sum(value > 0 for value in deltas),
        "baseline_wins": sum(value < 0 for value in deltas),
        "ties": sum(value == 0 for value in deltas), "all_valid": all_valid,
        "delta_p10_net": c["net"]["p10"] - b["net"]["p10"] if deltas else None,
        "delta_worst_10pct_mean_net": (c["net"]["worst_10pct_mean"] - b["net"]["worst_10pct_mean"]
                                       if deltas else None),
        "meets_acceptance": (all_valid and c["net"]["mean"] > b["net"]["mean"]
                             and c["losses"] <= b["losses"]
                             and c["net"]["minimum"] >= b["net"]["minimum"]),
    }


def _module_paths(directory: Path) -> dict:
    paths = {}
    for name, module in sorted(sys.modules.items()):
        if name not in ("agent", "strategy", *OFFICIAL_MODULES) and not name.startswith("strategy."):
            continue
        location = getattr(module, "__file__", None)
        if not location:
            raise RuntimeError(f"cannot verify imported module: {name}")
        path = Path(location).resolve()
        expected = directory / ("strategy" if name.startswith("strategy") else f"{name}.py")
        allowed = path.is_relative_to(expected) if name.startswith("strategy") else path == expected
        if not allowed:
            raise RuntimeError(f"wrong import path for {name}: {path}; expected {expected}")
        paths[name] = str(path)
    for name in ("agent", "strategy", "local_eval"):
        if name not in paths:
            raise RuntimeError(f"required module was not loaded: {name}")
    return paths


def _load_checker():
    # Load the current harness's validator without adding its repo to sys.path:
    # doing that would permit an absent revision dependency to leak in.
    spec = importlib.util.spec_from_file_location("isolated_contract_checks", HARNESS_DIR / "contract_checks.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.check_raw_answer


def _capture_requests(env) -> list[dict]:
    original = env.run_pilot
    signature = inspect.signature(original)
    requests = []

    def observed(*args, **kwargs):
        bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()
        result = original(*args, **kwargs)
        requests.append(deepcopy(dict(bound.arguments)))
        return result

    env.run_pilot = observed
    return requests


def _resource_errors(result, audit: dict) -> list[str]:
    errors = []
    if not isinstance(result, dict):
        return ["official evaluator did not return a result dictionary"]
    if not _finite(result.get("net_arpu_gain")):
        errors.append("official net_arpu_gain is missing or non-finite")
    for key, expected, limit in (
        ("total_contacts", audit.get("pilot_contacts", 0) + audit.get("final_contacts", 0), audit.get("contact_limit")),
        ("total_cost", audit.get("pilot_cost", 0) + audit.get("final_cost", 0), audit.get("budget_limit")),
        ("n_pilots", len(audit.get("pilot_history", [])), 20),
    ):
        value = result.get(key)
        if not _finite(value) or not _finite(limit) or value < 0 or value > limit + 1e-6:
            errors.append(f"official {key} is invalid or exceeds its public limit")
        elif not math.isclose(value, expected, rel_tol=1e-9, abs_tol=1e-6):
            errors.append(f"official {key} disagrees with public raw accounting")
    return errors


def evaluate_worker(directory: Path, seeds: list[int]) -> dict:
    harness = _harness_fingerprint()
    directory = directory.resolve(strict=True)
    initial = manifest(directory)
    os.chdir(directory)
    sys.path.insert(0, str(directory))
    check_raw_answer = _load_checker()
    agent_module = importlib.import_module("agent")
    importlib.import_module("strategy")
    evaluator = importlib.import_module("local_eval")
    paths = _module_paths(directory)
    rows = []
    for seed in seeds:
        audit = {}
        output = io.StringIO()
        started = perf_counter()
        agent = agent_module.Agent()

        class AuditedAgent:
            def act(self, env):
                requests = _capture_requests(env)
                audit["budget_limit"] = getattr(env, "total_budget", 100_000)
                audit["contact_limit"] = getattr(env, "max_total_contacts", 15_000)
                act_started = perf_counter()
                try:
                    raw = agent.act(env)
                    audit["campaigns"] = deepcopy(raw)
                    checked = check_raw_answer(raw, env, requests)
                    audit.update(asdict(checked))
                    audit["raw_errors"] = audit.pop("errors")
                    audit["raw_warnings"] = audit.pop("warnings")
                    return raw
                finally:
                    audit["agent_runtime_seconds"] = perf_counter() - act_started
                    audit["pilot_requests"] = requests
                    audit["pilot_history"] = deepcopy(env.pilot_history)

        result = None
        exception = None
        with redirect_stdout(output), redirect_stderr(output):
            try:
                result = evaluator.evaluate_agent(AuditedAgent(), seed=seed, verbose=False)
            except Exception as exc:
                exception = f"{type(exc).__name__}: {exc}"
        runtime = perf_counter() - started
        diagnostics = deepcopy(getattr(agent, "diagnostics", {}))
        diagnostic_errors = []
        if not isinstance(diagnostics, dict):
            diagnostic_errors.append("Agent.diagnostics is not a dictionary")
            diagnostics = {"reported_value": str(diagnostics)}
        if diagnostics.get("mode") != "strategy":
            diagnostic_errors.append(f"agent used fallback or unknown mode: {diagnostics.get('mode')!r}")
        if diagnostics.get("errors"):
            diagnostic_errors.append("Agent.diagnostics contains errors")
        if audit.get("agent_runtime_seconds", math.inf) >= 300:
            diagnostic_errors.append("agent exceeded the five-minute runtime target")
        audit.setdefault("raw_errors", ["Agent.act did not return a checked raw answer"])
        audit.setdefault("raw_warnings", [])
        resource_errors = _resource_errors(result, audit)
        row = {
            "seed": seed, "net_arpu_gain": result.get("net_arpu_gain") if isinstance(result, dict) else None,
            "runtime_seconds": runtime, "official_result": result, "evaluator_output": output.getvalue(),
            "exception": exception, "diagnostics": diagnostics, "diagnostic_errors": diagnostic_errors,
            "resource_errors": resource_errors, **audit,
        }
        row["valid"] = not (exception or audit["raw_errors"] or resource_errors or diagnostic_errors)
        rows.append(row)
        paths = _module_paths(directory)
    final = manifest(directory)
    if final != initial:
        raise RuntimeError(f"snapshot files changed during evaluation: {directory}")
    if _harness_fingerprint() != harness:
        raise RuntimeError("harness or validator changed during evaluation")
    return {"directory": str(directory), "pid": os.getpid(), "python": sys.version,
            "executable": sys.executable, "module_paths": paths, "manifest": initial,
            "bytecode_cache_prefix": sys.pycache_prefix, **harness,
            "runs": rows, "summary": summarize(rows)}


def _json_default(value):
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "item"):
        return value.item()
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if hasattr(value, "tolist"):
        return value.tolist()
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def _json_safe(value):
    """Keep infinite ROI from zero-cost campaigns without emitting invalid JSON."""
    if isinstance(value, float) and not math.isfinite(value):
        return "NaN" if math.isnan(value) else ("Infinity" if value > 0 else "-Infinity")
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return _json_safe(_json_default(value))


def _write_json(path: Path, report: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_safe(report), ensure_ascii=False, indent=2,
                               allow_nan=False) + "\n", encoding="utf-8")


def run_revision(directory: Path, seeds: list[int], *, timeout: float | None = None) -> dict:
    """Start an isolated interpreter; no caller modules or Python/API env leak in."""
    directory = directory.resolve(strict=True)
    # Windows needs these OS/runtime paths. Credentials and Python configuration
    # are deliberately absent; -I additionally disables user site and PYTHON*.
    allowed = {"systemroot", "windir", "temp", "tmp", "systemdrive", "comspec"}
    environment = {key: value for key, value in os.environ.items() if key.lower() in allowed}
    with tempfile.TemporaryDirectory(prefix="paired-agent-") as temp:
        output = Path(temp) / "worker.json"
        # -B only suppresses writes: the private empty prefix also prevents
        # existing timestamp-valid stale bytecode from being read.
        command = [sys.executable, "-I", "-B", "-X", f"pycache_prefix={Path(temp) / 'pycache'}",
                   str(Path(__file__).resolve()),
                   "--worker-dir", str(directory), "--seeds", ",".join(map(str, seeds)),
                   "--output", str(output)]
        completed = subprocess.run(command, cwd=directory, env=environment, capture_output=True,
                                   text=True, encoding="utf-8", errors="replace",
                                   timeout=timeout or max(60, 310 * len(seeds)))
        if completed.returncode != 0 or not output.is_file():
            raise RuntimeError(f"isolated worker failed for {directory} (exit {completed.returncode}):\n"
                               f"{completed.stderr[-6000:]}\n{completed.stdout[-2000:]}")
        return json.loads(output.read_text(encoding="utf-8"))


def compare(baseline_dir: Path, candidate_dir: Path, seeds: list[int], *, timeout=None) -> dict:
    harness = _harness_fingerprint()
    baseline_dir, candidate_dir = baseline_dir.resolve(strict=True), candidate_dir.resolve(strict=True)
    if baseline_dir == candidate_dir:
        raise ValueError("baseline and candidate must be separate snapshot directories")
    baseline_manifest, candidate_manifest = manifest(baseline_dir), manifest(candidate_dir)
    for group in ("official", "data"):
        if baseline_manifest[group] != candidate_manifest[group]:
            raise ValueError(f"paired snapshots have different {group} inputs")
    with ThreadPoolExecutor(max_workers=2) as pool:
        before = pool.submit(run_revision, baseline_dir, seeds, timeout=timeout)
        after = pool.submit(run_revision, candidate_dir, seeds, timeout=timeout)
        baseline, candidate = before.result(), after.result()
    if baseline["manifest"] != baseline_manifest or candidate["manifest"] != candidate_manifest:
        raise RuntimeError("snapshot changed between comparison setup and worker execution")
    if (_harness_fingerprint() != harness
            or any(result.get(key) != value for result in (baseline, candidate)
                   for key, value in harness.items())):
        raise RuntimeError("harness or validator changed between setup and worker execution")
    return {
        "seeds": seeds, "seed_range_convention": "start inclusive, stop exclusive",
        **harness, "nonfinite_encoding": "Ancillary non-finite values: Infinity, -Infinity, NaN strings",
        "baseline": baseline, "candidate": candidate, "paired": paired_summary(baseline, candidate),
        "limitation": "Mock results assess this seed set only; hidden judging effects differ.",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-dir", type=Path)
    parser.add_argument("--candidate-dir", type=Path)
    parser.add_argument("--seeds", type=parse_seeds, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, help="per-revision subprocess timeout in seconds")
    parser.add_argument("--worker-dir", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.worker_dir:
        report = evaluate_worker(args.worker_dir, args.seeds)
        _write_json(args.output, report)
        return 0
    if not args.baseline_dir or not args.candidate_dir:
        parser.error("--baseline-dir and --candidate-dir are required")
    if args.timeout is not None and args.timeout <= 0:
        parser.error("--timeout must be positive")
    try:
        report = compare(args.baseline_dir, args.candidate_dir, args.seeds, timeout=args.timeout)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        _write_json(args.output, {"error": f"{type(exc).__name__}: {exc}", "seeds": args.seeds})
        print(f"Comparison failed: {exc}", file=sys.stderr)
        return 1
    _write_json(args.output, report)
    print(json.dumps({"output": str(args.output.resolve()), "baseline": report["baseline"]["summary"],
                      "candidate": report["candidate"]["summary"],
                      "paired": {key: value for key, value in report["paired"].items() if key != "runs"}},
                     ensure_ascii=False, indent=2))
    # A valid experiment may reject a candidate. Reserve nonzero for invalid runs.
    return 0 if report["paired"]["all_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
