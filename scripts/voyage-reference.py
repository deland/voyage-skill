#!/usr/bin/env python3
"""Print, check, or update the argparse-derived VoyageSkill CLI reference."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from voyage_skill.reference import check_cli_reference_file, render_cli_reference, replace_cli_reference  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--print", action="store_true", dest="print_reference")
    mode.add_argument("--check", type=Path, metavar="RUNBOOK")
    mode.add_argument("--write", type=Path, metavar="RUNBOOK")
    args = parser.parse_args()

    if args.print_reference:
        print(render_cli_reference())
        return 0
    if args.check is not None:
        errors = check_cli_reference_file(args.check)
        if errors:
            for error in errors:
                print(error, file=sys.stderr)
            return 1
        print("CLI reference is current")
        return 0
    document = args.write.read_text(encoding="utf-8")
    args.write.write_text(replace_cli_reference(document), encoding="utf-8")
    print(f"updated {args.write}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
