"""
Targeted real-Gemini debug script for AI Finance Controller.

Allows running the Gemini agent investigation on a single transaction exception,
displaying detailed non-sensitive tool traces, results, final decision, and
comparison with synthetic ground truth.

Usage:
    python src/debug_gemini_case.py <transaction_id>
Example:
    python src/debug_gemini_case.py TXN003
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

# Ensure UTF-8 console output
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

from src.agent.controller import AgentController, LLMClient
from src.agent.tools import FinancialToolkit
from src.generator import SyntheticDataGenerator
from src.reconciliation import ReconciliationEngine


def debug_case(transaction_id: str) -> None:
    """Runs a targeted real-Gemini investigation on a specific transaction ID."""
    print("=" * 50)
    print("AI FINANCE CONTROLLER — GEMINI CASE DEBUG")
    print("=" * 50)

    # 1. Generate / load synthetic data
    data_dir = os.path.join(_project_root, "data")
    generator = SyntheticDataGenerator(seed=42, total_transactions=100)
    p_path, l_path, b_path, a_path = generator.save_to_csv(data_dir)
    payments, ledger_records, bank_records, adjustments, ground_truth = generator.generate()

    gt_map = {row["transaction_id"]: row for row in ground_truth}
    gt_item = gt_map.get(transaction_id)

    if not gt_item:
        print(f"Error: Transaction ID '{transaction_id}' not found in dataset.")
        sys.exit(1)

    # 2. Run Phase 1 reconciliation to get the exception record
    phase1_results, _ = ReconciliationEngine.reconcile_batch(p_path, l_path, b_path)
    phase1_map = {r["transaction_id"]: r for r in phase1_results}
    phase1_item = phase1_map.get(transaction_id)

    if not phase1_item:
        print(f"Error: Transaction ID '{transaction_id}' not found in Phase 1 results.")
        sys.exit(1)

    if phase1_item["status"] != "EXCEPTION":
        print(f"Transaction '{transaction_id}' is not an exception in Phase 1 (Status: {phase1_item['status']}).")
        print(f"Expected Phase 2 Decision: {gt_item.get('expected_phase2_decision', 'N/A')}")
        sys.exit(0)

    print(f"\nTransaction ID:     {transaction_id}")
    print(f"Initial Exception:  {phase1_item.get('reason')}")
    print(f"Payment Amount:     ₹{phase1_item.get('payment_amount', 0):,}" if phase1_item.get("payment_amount") is not None else "Payment Amount:     N/A")
    print(f"Ledger Gross:       ₹{phase1_item.get('gross_amount', 0):,}" if phase1_item.get("gross_amount") is not None else "Ledger Gross:       N/A")
    print(f"Ledger Fee:         ₹{phase1_item.get('fee', 0):,}" if phase1_item.get("fee") is not None else "Ledger Fee:         N/A")
    print(f"Expected Net:       ₹{phase1_item.get('expected_net_amount', 0):,}" if phase1_item.get("expected_net_amount") is not None else "Expected Net:       N/A")
    print(f"Bank Credit:        ₹{phase1_item.get('bank_amount', 0):,}" if phase1_item.get("bank_amount") is not None else "Bank Credit:        N/A")
    print(f"Discrepancy:        ₹{phase1_item.get('difference', 0):,}" if phase1_item.get("difference") is not None else "Discrepancy:        N/A")

    # 3. Instantiate Gemini client and AgentController
    toolkit = FinancialToolkit(payments, ledger_records, bank_records, adjustments)
    try:
        llm_client = LLMClient(provider="gemini")
    except Exception as e:
        print(f"\nError initializing Gemini client: {e}")
        sys.exit(1)

    agent = AgentController(toolkit=toolkit, llm_client=llm_client)

    print("\n" + "-" * 50)
    print("RUNNING GEMINI INVESTIGATION...")
    print("-" * 50)

    start_time = time.perf_counter()
    decision, log = agent.investigate_exception(phase1_item)
    elapsed = time.perf_counter() - start_time

    # 4. Display tool traces
    print("\n--- TOOL EXECUTION TRACE ---")
    if not log.tool_traces:
        print("  (No tools were invoked)")
    else:
        for idx, trace in enumerate(log.tool_traces, 1):
            print(f"\nTool {idx}: {trace.tool_name}")
            print(f"  Args:    {trace.tool_arguments}")
            print(f"  Result:  {trace.tool_result_summary}")

    print(f"\nTool calls used: {log.tool_call_count}")

    # 5. Display Final Decision & Comparison
    expected_decision = gt_item.get("expected_phase2_decision", "HUMAN_REVIEW")
    if not expected_decision or expected_decision == "N/A":
        expected_decision = "HUMAN_REVIEW"

    matches_gt = decision.decision == expected_decision

    print("\n" + "=" * 50)
    print("FINAL INVESTIGATION RESULT")
    print("=" * 50)
    print(f"Decision:            {decision.decision}")
    print(f"Resolution Type:     {decision.resolution_type}")
    print(f"Resolved Difference: ₹{decision.resolved_difference:,}" if decision.resolved_difference is not None else "Resolved Difference: None")
    print(f"Confidence:          {decision.confidence:.2f}")
    print(f"Reason:              {decision.reason}")
    print(f"Recommended Action:  {decision.recommended_action}")
    print(f"Investigation Time:  {elapsed:.2f}s")
    print("-" * 50)
    print(f"Expected GT Decision: {expected_decision}")
    print(f"Ground-Truth Match:   {'YES [MATCH]' if matches_gt else 'NO [MISMATCH]'}")
    print("=" * 50)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python src/debug_gemini_case.py <transaction_id>")
        print("Example: python src/debug_gemini_case.py TXN003")
        sys.exit(1)

    target_id = sys.argv[1].strip()
    debug_case(target_id)
