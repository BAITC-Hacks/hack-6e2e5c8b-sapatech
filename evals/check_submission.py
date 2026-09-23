"""Regenerate submission.csv twice inside a disposable local package copy.

The official participant package and generated CSV never enter Git. This tool
uses the official make_submission.py unchanged and removes OPENAI_API_KEY from
the child environment to exercise the deterministic offline path.
"""

from __future__ import annotations

import argparse
import csv
from hashlib import sha256
import importlib.metadata
import io
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--agent", type=Path, required=True)
    parser.add_argument("--strategy", type=Path,
                        help="optional strategy package directory used by agent.py")
    args = parser.parse_args()
    package, agent = args.package.resolve(), args.agent.resolve()
    strategy = args.strategy.resolve() if args.strategy else agent.parent / "strategy"
    if not (package / "make_submission.py").is_file() or not agent.is_file():
        parser.error("official package and agent file are required")

    with tempfile.TemporaryDirectory(prefix="beeline-submission-check-") as temp:
        child_env = os.environ.copy()
        child_env.pop("OPENAI_API_KEY", None)
        hashes = []
        counts = []
        logical_hashes = []
        lf_hashes = []
        crlf_hashes = []
        line_endings = []
        headers = []
        for attempt in (1, 2):
            run_dir = Path(temp) / f"participant_package_{attempt}"
            shutil.copytree(package, run_dir)
            shutil.copy2(agent, run_dir / "agent.py")
            if strategy.is_dir():
                shutil.copytree(strategy, run_dir / "strategy", dirs_exist_ok=True)
            completed = subprocess.run(
                [sys.executable, "make_submission.py"], cwd=run_dir,
                env=child_env, capture_output=True, text=True, timeout=300,
                check=False,
            )
            if completed.returncode:
                print(json.dumps({"attempt": attempt, "exit_code": completed.returncode,
                                  "stderr": completed.stderr[-2000:]}, ensure_ascii=False))
                return 1
            csv_path = run_dir / "submission.csv"
            if not csv_path.is_file():
                print(json.dumps({"attempt": attempt, "error": "submission.csv missing"}))
                return 1
            content = csv_path.read_bytes()
            hashes.append(sha256(content).hexdigest())
            lf = content.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
            lf_hashes.append(sha256(lf).hexdigest())
            crlf_hashes.append(sha256(lf.replace(b"\n", b"\r\n")).hexdigest())
            rows = list(csv.reader(io.StringIO(content.decode("utf-8"), newline="")))
            logical_hashes.append(sha256(json.dumps(
                rows, ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")).hexdigest())
            headers.append(rows[0] if rows else [])
            counts.append(max(len(rows) - 1, 0))
            line_endings.append({"lf": content.count(b"\n") - content.count(b"\r\n"),
                                 "crlf": content.count(b"\r\n")})
        report = {
            "identical": hashes[0] == hashes[1],
            "sha256_first": hashes[0], "sha256_second": hashes[1],
            "campaign_counts": counts,
            "logical_sha256": logical_hashes,
            "lf_sha256": lf_hashes,
            "crlf_sha256": crlf_hashes,
            "line_endings": line_endings,
            "headers": headers,
            "environment": {
                "python": platform.python_version(),
                "pandas": importlib.metadata.version("pandas"),
                "numpy": importlib.metadata.version("numpy"),
            },
            "isolated_copy": True, "api_key_removed": True,
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return int(not report["identical"] or not 1 <= counts[0] <= 10 or
                   counts[0] != counts[1] or headers[0] != headers[1] or
                   logical_hashes[0] != logical_hashes[1])


if __name__ == "__main__":
    raise SystemExit(main())
