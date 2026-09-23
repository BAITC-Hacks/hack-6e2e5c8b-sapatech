"""Install the official participant ZIP locally, without changing its files."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
MEMBERS = (
    "environment.py", "mock_environment.py", "scoring_core.py", "local_eval.py",
    "make_submission.py", "agent_template.py", "customer_profile.csv",
    "tariff_dictionary.csv", "feature_dictionary.csv", "data/dict_tariff.csv",
    "data/traffic.csv", "data/arpu_monthly.csv", "data/change_tariff.csv",
)


def install(archive: Path, destination: Path, *, baseline: bool = False) -> None:
    destination = destination.resolve()
    with ZipFile(archive) as package:
        # Exact allowlist: no archive-supplied paths, scripts, or symlinks are extracted.
        contents = {name: package.read(name) for name in MEMBERS}
    if baseline:
        contents["agent.py"] = contents["agent_template.py"]
    # Preflight all files before writing anything. Never overwrite local edits.
    for name, data in contents.items():
        target = destination / name
        if not target.resolve().is_relative_to(destination):
            raise ValueError(f"Target escapes destination: {name}")
        if target.exists() and target.read_bytes() != data:
            raise FileExistsError(f"Refusing to overwrite different file: {target}")
    for name, data in contents.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(data)
    print(f"Installed {len(contents)} unchanged files in {destination}")
    print(f"Archive SHA256: {hashlib.sha256(archive.read_bytes()).hexdigest()}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--baseline", action="store_true",
                        help="Install separate template workspace in jobs/template_baseline")
    args = parser.parse_args()
    destination = ROOT / "jobs" / "template_baseline" if args.baseline else ROOT
    install(args.archive, destination, baseline=args.baseline)


if __name__ == "__main__":
    main()
