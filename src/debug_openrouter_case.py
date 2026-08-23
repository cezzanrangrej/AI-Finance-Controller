"""
OpenRouter targeted case debug script for AI Finance Controller.
"""

import os
import sys

_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.abspath(os.path.join(_current_dir, ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.debug_case import debug_case

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python src/debug_openrouter_case.py <transaction_id>")
        print("Example: python src/debug_openrouter_case.py TXN003")
        sys.exit(1)

    target_id = sys.argv[1].strip()
    model = sys.argv[2].strip() if len(sys.argv) > 2 else os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct")
    debug_case(target_id, provider="openrouter", model=model)
