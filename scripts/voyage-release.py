#!/usr/bin/env python3
"""Create or verify local release evidence without publishing anything."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from voyage_skill.release import ReleaseEvidenceError, create_release_evidence, verify_release_evidence  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="voyage-release", description="Create or verify local release evidence; performs no publication")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="Create content-addressed local evidence")
    create.add_argument("--source", required=True)
    create.add_argument("--artifacts", required=True)
    create.add_argument("--checks", required=True)
    create.add_argument("--output", required=True)
    create.add_argument("--revision", required=True)
    verify = commands.add_parser("verify", help="Verify local evidence against immutable inputs")
    verify.add_argument("--source", required=True)
    verify.add_argument("--artifacts", required=True)
    verify.add_argument("--checks", required=True)
    verify.add_argument("--manifest", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            result = create_release_evidence(args.source, args.artifacts, args.checks, args.output, revision=args.revision)
        else:
            result = verify_release_evidence(args.manifest, args.source, args.artifacts, args.checks)
    except ReleaseEvidenceError as exc:
        print(f"voyage-release: error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
