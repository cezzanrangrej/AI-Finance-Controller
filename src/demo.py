"""
End-to-end demo runner for AI Finance Controller - Phase 3.1.

Executes a complete batch run via the API across 4 data sources, measures phase-separated
processing timing and throughput, verifies ground truth accuracy, auto-resolution precision,
and recall, and outputs the final Phase 3.1 summary report and breakdown.
"""

import os
import sys
import time

# Ensure project root on path
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.abspath(os.path.join(_current_dir, ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import src.config  # Loads .env variables

# UTF-8 stdout
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)


def _rate(metrics: dict, key: str) -> str:
    """
    Renders a percentage metric, or "N/A (not measured)" when it is absent or
    None.

    ``metrics.get(key, 100.0)`` was used here, which was wrong twice over: the
    default only fires when the key is *missing*, whereas the API always sends
    the key and sets it to None when there was no ground truth to measure
    against -- so an unmeasured run either crashed on ``f"{None:.2f}"`` or, for
    the keys that do default, printed a fabricated 100%. An empty denominator is
    unmeasured, not perfect.
    """
    value = metrics.get(key)
    if value is None:
        return "N/A (not measured)"
    try:
        return f"{float(value):.2f}%"
    except (TypeError, ValueError):
        return "N/A (not measured)"


def _seconds(metrics: dict, key: str, digits: int = 4) -> str:
    """Renders a timing metric, or N/A when the API did not report it."""
    value = metrics.get(key)
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "N/A"


def run_e2e_demo():
    os.environ["LLM_PROVIDER"] = "demo"
    print("Initiating Phase 3.1 End-to-End Reconciliation & AI Investigation Pipeline...\n")
    response = client.post("/api/runs")

    if response.status_code != 201:
        print(f"Error: API returned status {response.status_code}")
        print(response.text)
        sys.exit(1)

    data = response.json()
    run_id = data["run_id"]

    metrics_resp = client.get(f"/api/runs/{run_id}/metrics")
    metrics = metrics_resp.json()

    exceptions_resp = client.get(f"/api/runs/{run_id}/exceptions")
    exceptions = exceptions_resp.json()

    provider_label = str(metrics.get("llm_provider", "demo")).upper()
    mode_label = str(metrics.get("llm_mode", "DEMO"))
    model_name = str(metrics.get("llm_model", "demo"))

    print("========================================")
    print("AI FINANCE CONTROLLER")
    print("PHASE 3.1 BATCH RECONCILIATION")
    print("========================================\n")

    print(f"LLM Provider:               {provider_label}")
    print(f"Mode:                       {mode_label}")
    print(f"Model:                      {model_name}\n")

    print(f"Records processed:          {metrics['total_records']}\n")

    print(f"Initial reconciled:          {metrics['initial_reconciled']}")
    print(f"Initial exceptions:          {metrics['initial_exceptions']}\n")

    print(f"AI auto-resolved:            {metrics['ai_auto_resolved']}")
    print(f"Human review:                {metrics['human_review']}\n")

    print(f"Initial match rate:          {_rate(metrics, 'initial_match_rate')}")
    print(f"AI resolution rate:          {_rate(metrics, 'agent_resolution_rate')}")
    print(f"Final resolution rate:       {_rate(metrics, 'final_resolution_rate')}\n")

    # phase2_accuracy and ground_truth_accuracy are the same measurement; the
    # former was previously read with `or`, so a genuine 0.00% accuracy fell
    # through to the fallback and was reported as a pass.
    p2_key = "phase2_accuracy" if metrics.get("phase2_accuracy") is not None else "ground_truth_accuracy"

    print(f"Phase 1 accuracy:             {_rate(metrics, 'phase1_accuracy')}")
    print(f"Phase 2 decision accuracy:   {_rate(metrics, p2_key)}")
    print(f"Auto-resolution precision:  {_rate(metrics, 'auto_resolution_precision')}")
    print(f"Auto-resolution recall:     {_rate(metrics, 'auto_resolution_recall')}\n")

    e2e_key = (
        "end_to_end_time_sec"
        if metrics.get("end_to_end_time_sec") is not None
        else "total_processing_time_sec"
    )

    print(f"Phase 1 processing time:     {_seconds(metrics, 'phase1_time_sec')} sec")
    print(f"Phase 2 processing time:     {_seconds(metrics, 'phase2_time_sec')} sec")
    print(f"End-to-end processing time:  {_seconds(metrics, e2e_key)} sec\n")

    # Previously defaulted to a hardcoded 20000.0 records/sec, which printed an
    # invented benchmark figure whenever the API had not measured throughput.
    print(f"Phase 1 throughput:          {_seconds(metrics, 'records_per_second', 2)} records/sec")
    print("========================================\n")

    # Exception Breakdown Detail
    print("----------------------------------------")
    print("PHASE 2 EXCEPTION RESOLUTION BREAKDOWN")
    print("----------------------------------------\n")

    auto_resolved_items = [e for e in exceptions if e["decision"] == "AUTO_RESOLVED"]
    human_review_items = [e for e in exceptions if e["decision"] == "HUMAN_REVIEW"]

    print(f">>> AUTO-RESOLVED CASES ({len(auto_resolved_items)} total):")
    for item in auto_resolved_items:
        print(f"  [{item['transaction_id']}] {item['exception_type']}")
        print(f"      Reason: {item['reason']}")
        print(f"      Resolution Type: {item.get('resolution_type', 'ADJUSTMENT_EXPLAINED')}")
        print()

    print(f">>> HUMAN REVIEW CASES ({len(human_review_items)} total):")
    for item in human_review_items[:5]:  # Print first 5 human review cases
        print(f"  [{item['transaction_id']}] {item['exception_type']}")
        print(f"      Reason: {item['reason']}")
        print()
    if len(human_review_items) > 5:
        print(f"  ... and {len(human_review_items) - 5} more cases requiring human review.\n")


if __name__ == "__main__":
    run_e2e_demo()
