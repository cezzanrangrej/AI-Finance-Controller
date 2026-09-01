#!/usr/bin/env python
"""
CLI: generate the exception report for a given run.

Usage:
    python scripts/generate_report.py --run-id run_abc12345
    python scripts/generate_report.py --run-id run_abc12345 --format json
    python scripts/generate_report.py --run-id run_abc12345 --out report.md

Prints to stdout by default; use --out to write to a file instead.
Exits non-zero with a clear message if the run doesn't exist.
"""

import argparse
import json
import os
import sys

# Ensure repository root is on sys.path
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.abspath(os.path.join(_current_dir, ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.db.database import SessionLocal
from src.reporting.exception_report import build_exception_report, format_as_markdown


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the reconciliation exception report.")
    parser.add_argument("--run-id", required=True, help="Run ID to report on (e.g. run_abc12345)")
    parser.add_argument(
        "--format", choices=["markdown", "json"], default="markdown", help="Output format (default: markdown)"
    )
    parser.add_argument("--out", help="Write to this file instead of stdout")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        report = build_exception_report(db, args.run_id)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        db.close()

    if args.format == "json":
        output = json.dumps(report.as_dict(), indent=2)
    else:
        output = format_as_markdown(report)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Report written to {args.out}")
    else:
        print(output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
