"""Full rebuild of DuckDB from raw sources (Day 8).

Order matters:
  1. schema
  2. results (football-data -> matches_staging)
  3. resolve teams (staging -> matches)
  4. understat xG join
  5. crowd snapshots
  6. fixtures + stadiums

Safe to re-run. Prefer --skip-download when CSVs/parquet already exist.
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

log = logging.getLogger("full_load")

ROOT = Path(__file__).resolve().parents[1]


def run(module_or_script: str, extra: list[str] | None = None) -> None:
    extra = extra or []
    if module_or_script.endswith(".py") and "scripts/" in module_or_script.replace("\\", "/"):
        cmd = [sys.executable, str(ROOT / module_or_script), *extra]
    else:
        cmd = [sys.executable, "-m", module_or_script, *extra]
    log.info(">> %s", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=ROOT)


def main() -> int:
    parser = argparse.ArgumentParser(description="Full DuckDB rebuild.")
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="reuse existing results CSVs and understat parquet",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    results_extra = ["--skip-download"] if args.skip_download else []
    understat_extra: list[str] = []
    parquet = ROOT / "data" / "raw" / "understat" / "team_match_xg.parquet"
    if args.skip_download and parquet.is_file():
        understat_extra = ["--from-parquet", str(parquet)]

    steps = [
        ("collectors.results", results_extra),
        ("loaders.resolve_team", []),
        ("collectors.understat", understat_extra),
        ("loaders.crowd_to_duck", []),
        ("collectors.fixtures", []),
    ]

    for mod, extra in steps:
        run(mod, extra)

    log.info("full load complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
