#!/usr/bin/env python3
"""Build deterministic VoyageSkill artifacts from one Git commit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from voyage_skill.distribution import DistributionError, build_artifacts  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="voyage-build", description="Build commit-bound VoyageSkill artifacts")
    parser.add_argument("--source", default=".", help="Exact Git worktree root")
    parser.add_argument("--output", required=True, help="New output directory outside the source tree")
    parser.add_argument("--revision", default="HEAD", help="Readable Git commit")
    parser.add_argument("--source-date-epoch", type=int, default=0, help="Non-negative reproducible timestamp")
    args = parser.parse_args(argv)
    try:
        result = build_artifacts(args.source, args.output, revision=args.revision, source_date_epoch=args.source_date_epoch)
    except DistributionError as exc:
        print(f"voyage-build: error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
