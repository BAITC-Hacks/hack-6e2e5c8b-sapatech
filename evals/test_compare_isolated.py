"""Process/import and public-audit regressions without organizer data."""

from __future__ import annotations

import argparse
from contextlib import redirect_stderr
import io
import json
import os
from pathlib import Path
import py_compile
import shutil
import subprocess
import sys
import tempfile
import textwrap
import types
import unittest
from unittest.mock import patch

from evals.compare_isolated import compare, distribution, main, parse_seeds, run_revision


TOY_AGENT = """
import os
import strategy

class Agent:
    def act(self, env):
        env.run_pilot('tariff_2', 'sms', n_customers=10)
        self.diagnostics = {
            'mode': strategy.MODE, 'errors': strategy.ERRORS,
            'marker': strategy.VALUE,
            'leaked_environment': os.environ.get('ISOLATION_POISON'),
        }
        campaign = {'campaign_name': str(strategy.VALUE),
                    'target_tariff': 'tariff_2', 'channel': 'sms'}
        return [campaign.copy() for _ in range(strategy.COUNT)]
"""


# This fixture deliberately accepts raw excess campaigns as a sanitizer might.
# The harness must reject them using the independent public validator.
TOY_EVALUATOR = """
from types import SimpleNamespace
import pandas as pd

def evaluate_agent(agent, seed=None, verbose=True):
    env = SimpleNamespace(
        customer_profile=pd.DataFrame({
            'ID_NUMBER': range(30), 'current_tariff': ['tariff_1'] * 30,
            'arpu_segment': ['HIGH'] * 30, 'data_segment': ['HEAVY'] * 30,
            'call_segment': ['LOW'] * 30, 'predicted_arpu': [1000.] * 30,
        }),
        tariffs=pd.DataFrame({'tariff_plan_code': ['tariff_1', 'tariff_2']}),
        channels={'sms': {'cost_per_contact': 2.}},
        total_budget=100000., max_total_contacts=15000,
        remaining_budget=100000., remaining_contacts=15000,
        pilots_left=20, pilot_history=[],
    )
    def run_pilot(target_tariff, channel, n_customers=100):
        env.remaining_budget -= n_customers * 2
        env.remaining_contacts -= n_customers
        env.pilots_left -= 1
        result = {'target_tariff': target_tariff, 'channel': channel,
                  'n_customers': n_customers, 'cost': n_customers * 2.,
                  'observed_lift_ratio': .1, 'observed_lift_total': 1000.}
        env.pilot_history.append(result)
        return result
    env.run_pilot = run_pilot
    campaigns = agent.act(env)
    return {'net_arpu_gain': float(campaigns[0]['campaign_name']) + seed,
            'total_cost': 80., 'total_contacts': 40, 'n_pilots': 1}
"""


def write_toy(directory: Path, value: int, *, count=1, mode="strategy", errors=None):
    directory.mkdir(parents=True)
    (directory / "strategy").mkdir()
    (directory / "data").mkdir()
    (directory / "agent.py").write_text(textwrap.dedent(TOY_AGENT), encoding="utf-8")
    (directory / "local_eval.py").write_text(textwrap.dedent(TOY_EVALUATOR), encoding="utf-8")
    (directory / "strategy/__init__.py").write_text(
        f"VALUE = {value}\nCOUNT = {count}\nMODE = {mode!r}\nERRORS = {errors or []!r}\n",
        encoding="utf-8",
    )
    (directory / "customer_profile.csv").write_text("fixture\n1\n", encoding="utf-8")
    (directory / "data/change_tariff.csv").write_text("fixture\n1\n", encoding="utf-8")


class IsolatedComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="test-isolated-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.baseline = self.root / "baseline"
        self.candidate = self.root / "candidate"
        write_toy(self.baseline, 11)
        write_toy(self.candidate, 22)

    def test_processes_use_their_own_strategy_and_ignore_parent_environment(self):
        poison = types.ModuleType("strategy")
        poison.VALUE = -9999
        poison.__file__ = str(self.root / "wrong-strategy.py")
        with patch.dict(sys.modules, {"strategy": poison}), patch.dict(
            os.environ, {"ISOLATION_POISON": "must not leak", "PYTHONPATH": str(self.baseline)}
        ):
            report = compare(self.baseline, self.candidate, [3, 4])
        before, after = report["baseline"], report["candidate"]
        self.assertNotEqual(before["pid"], after["pid"])
        self.assertNotIn(os.getpid(), (before["pid"], after["pid"]))
        self.assertEqual([row["net_arpu_gain"] for row in before["runs"]], [14., 15.])
        self.assertEqual([row["net_arpu_gain"] for row in after["runs"]], [25., 26.])
        for result, directory, marker in ((before, self.baseline, 11), (after, self.candidate, 22)):
            self.assertEqual(Path(result["module_paths"]["agent"]), directory / "agent.py")
            self.assertEqual(Path(result["module_paths"]["strategy"]), directory / "strategy/__init__.py")
            self.assertEqual(Path(result["module_paths"]["local_eval"]), directory / "local_eval.py")
            self.assertEqual(result["summary"]["valid_runs"], 2)
            for row in result["runs"]:
                self.assertEqual(row["diagnostics"]["marker"], marker)
                self.assertIsNone(row["diagnostics"]["leaked_environment"])
                self.assertEqual(row["pilot_requests"][0]["n_customers"], 10)
                self.assertEqual(row["pilot_contacts"] + row["final_contacts"], 40)
        self.assertNotEqual(before["manifest"]["agent_strategy"], after["manifest"]["agent_strategy"])
        self.assertEqual(before["manifest"]["official"], after["manifest"]["official"])
        self.assertEqual(before["manifest"]["data"], after["manifest"]["data"])
        self.assertTrue(report["paired"]["meets_acceptance"])
        self.assertEqual(report["paired"]["candidate_wins"], 2)
        self.assertEqual(report["paired"]["delta_net"]["mean"], 11.)

    def test_raw_invalid_answer_and_recovery_fail_even_if_evaluator_scores_it(self):
        (self.candidate / "strategy/__init__.py").write_text(
            "VALUE = 22\nCOUNT = 11\nMODE = 'pilot-recovery'\nERRORS = ['strategy failed']\n",
            encoding="utf-8",
        )
        report = compare(self.baseline, self.candidate, [1])
        row = report["candidate"]["runs"][0]
        self.assertEqual(row["net_arpu_gain"], 23.)
        self.assertFalse(row["valid"])
        self.assertTrue(any("raw campaign count" in message for message in row["raw_errors"]))
        self.assertTrue(row["resource_errors"])
        self.assertTrue(any("fallback" in message for message in row["diagnostic_errors"]))
        self.assertEqual(report["candidate"]["summary"]["fallback_runs"], 1)
        self.assertFalse(report["paired"]["meets_acceptance"])

    def test_refuses_different_data_before_running_any_agent(self):
        (self.candidate / "data/change_tariff.csv").write_text("fixture\n2\n", encoding="utf-8")
        with patch("evals.compare_isolated.run_revision") as worker:
            with self.assertRaisesRegex(ValueError, "different data inputs"):
                compare(self.baseline, self.candidate, [0])
            worker.assert_not_called()

    def test_refuses_different_official_evaluators(self):
        with (self.candidate / "local_eval.py").open("a", encoding="utf-8") as stream:
            stream.write("\n# different evaluator\n")
        with self.assertRaisesRegex(ValueError, "different official inputs"):
            compare(self.baseline, self.candidate, [0])

    def test_detects_code_changed_during_block(self):
        strategy = self.candidate / "strategy/__init__.py"
        with strategy.open("a", encoding="utf-8") as stream:
            stream.write("\nwith open(__file__, 'a', encoding='utf-8') as stream:\n"
                         "    stream.write('\\n# mutation\\n')\n")
        with self.assertRaisesRegex(RuntimeError, "snapshot files changed during evaluation"):
            run_revision(self.candidate, [0])

    def test_ignores_stale_bytecode_with_matching_source_timestamp_and_size(self):
        strategy = self.candidate / "strategy/__init__.py"
        source = strategy.read_text(encoding="utf-8")
        stamp = strategy.stat().st_mtime_ns
        py_compile.compile(str(strategy), doraise=True,
                           invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP)
        strategy.write_text(source.replace("VALUE = 22", "VALUE = 99"), encoding="utf-8")
        os.utime(strategy, ns=(stamp, stamp))
        result = run_revision(self.candidate, [0])
        self.assertEqual(result["runs"][0]["diagnostics"]["marker"], 99)
        self.assertEqual(result["runs"][0]["net_arpu_gain"], 99.)
        self.assertTrue(result["bytecode_cache_prefix"])

    def test_infinite_ancillary_roi_exports_but_infinite_net_is_invalid(self):
        evaluator = self.candidate / "local_eval.py"
        source = evaluator.read_text(encoding="utf-8")
        evaluator.write_text(source.replace("'n_pilots': 1}",
                                            "'n_pilots': 1, 'roi': float('inf')}"), encoding="utf-8")
        result = run_revision(self.candidate, [0])
        self.assertTrue(result["runs"][0]["valid"])
        self.assertEqual(result["runs"][0]["official_result"]["roi"], "Infinity")
        evaluator.write_text(source.replace("float(campaigns[0]['campaign_name']) + seed",
                                            "float('inf')"), encoding="utf-8")
        result = run_revision(self.candidate, [0])
        self.assertFalse(result["runs"][0]["valid"])
        self.assertEqual(result["summary"]["completed"], 0)
        self.assertTrue(any("non-finite" in error for error in result["runs"][0]["resource_errors"]))

    def test_worker_rejects_validator_changed_during_run(self):
        copied = self.root / "harness"
        copied.mkdir()
        harness = Path(__file__).resolve().parent
        for filename in ("compare_isolated.py", "contract_checks.py"):
            shutil.copyfile(harness / filename, copied / filename)
        validator = copied / "contract_checks.py"
        strategy = self.candidate / "strategy/__init__.py"
        with strategy.open("a", encoding="utf-8") as stream:
            stream.write(f"\nwith open({str(validator)!r}, 'a', encoding='utf-8') as stream:\n"
                         "    stream.write('\\n# concurrent validator edit\\n')\n")
        completed = subprocess.run(
            [sys.executable, "-I", "-B", str(copied / "compare_isolated.py"),
             "--worker-dir", str(self.candidate), "--seeds", "0", "--output", str(self.root / "worker.json")],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("harness or validator changed during evaluation", completed.stderr)

    def test_cli_records_setup_failure_as_nonzero_json_result(self):
        output = self.root / "failure.json"
        with redirect_stderr(io.StringIO()):
            code = main(["--baseline-dir", str(self.baseline), "--candidate-dir", str(self.baseline),
                         "--seeds", "0:2", "--output", str(output)])
        self.assertEqual(code, 1)
        self.assertIn("separate snapshot", json.loads(output.read_text(encoding="utf-8"))["error"])

    def test_seed_ranges_and_lower_tail_statistics(self):
        self.assertEqual(parse_seeds("0:3,7,100:104:2"), [0, 1, 2, 7, 100, 102])
        for bad in ("", "0:0", "1,1", "-1", "0:2:0"):
            with self.subTest(bad=bad), self.assertRaises(argparse.ArgumentTypeError):
                parse_seeds(bad)
        values = [-100., -10., *range(18)]
        stats = distribution(values)
        self.assertEqual(stats["minimum"], -100.)
        self.assertEqual(stats["worst_10pct_mean"], -55.)
        self.assertAlmostEqual(stats["p10"], -1.)


if __name__ == "__main__":
    unittest.main()
