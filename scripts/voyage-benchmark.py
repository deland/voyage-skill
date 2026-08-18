#!/usr/bin/env python3
"""Run the disposable VoyageSkill full-ledger benchmark."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from voyage_skill.benchmark import DEFAULT_EVENT_COUNTS, run_benchmark  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark disposable full-ledger load, hash validation, and replay")
    parser.add_argument("--events", action="append", type=int, help="Synthetic event count; repeat as needed")
    parser.add_argument("--runs", type=int, default=3, help="Runs per event count (default: 3)")
    args = parser.parse_args()
    try:
        report = run_benchmark(event_counts=args.events or DEFAULT_EVENT_COUNTS, runs=args.runs)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
