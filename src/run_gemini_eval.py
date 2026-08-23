"""
Gemini API evaluation entry point for AI Finance Controller.
Provides backward compatibility by wrapping the unified provider evaluation runner.
"""

import argparse
import os
import sys

# Ensure project root on path
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.abspath(os.path.join(_current_dir, ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.run_llm_eval import run_evaluation


def main():
    parser = argparse.ArgumentParser(
        description="Run Gemini evaluation for AI Finance Controller."
    )
    parser.add_argument(
        "--cases",
        type=int,
        default=5,
        help="Number of Phase 1 exceptions to evaluate with Gemini (default: 5)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help="Number of sequential evaluation runs (default: 1)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Gemini model override (e.g. gemini-3.5-flash)",
    )
    args = parser.parse_args()

    run_evaluation(provider="gemini", cases=args.cases, runs=args.runs, model=args.model)



if __name__ == "__main__":
    main()
