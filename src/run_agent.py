"""
Phase 2 Entry Point: AI Finance Controller Agent Runner.

Workflow:
    1. Generate / load CSV data (Phase 1)
    2. Run Phase 1 batch reconciliation
    3. Filter EXCEPTION records only
    4. Send each exception to the AI agent
    5. Collect structured AgentDecision records
    6. Evaluate against ground truth
    7. Print combined Phase 1 + Phase 2 report
"""

import os
import sys
from typing import Any, Dict, List

# Ensure project root on sys.path
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.abspath(os.path.join(_current_dir, ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# Set stdout to UTF-8 on Windows
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

import src.config  # Loads .env variables

from src.generator import SyntheticDataGenerator
from src.reconciliation import ReconciliationEngine
from src.agent.controller import AgentController, LLMClient
from src.agent.tools import FinancialToolkit
from src.agent.schemas import AgentDecision
from src.agent.evaluator import evaluate_agent_decisions, compute_phase2_metrics


def fmt_currency(val: Any) -> str:
    """Format a numeric value as Indian Rupee string."""
    if val is None:
        return "N/A"
    try:
        return f"\u20b9{int(val):,}"
    except (ValueError, TypeError):
        return str(val)


def fmt_pct(val: float) -> str:
    return f"{val:.2f}%"


def print_phase1_summary(metrics: Dict[str, Any]) -> None:
    print("=" * 44)
    print("         AI FINANCE CONTROLLER")
    print("    PHASE 1: DETERMINISTIC RECONCILIATION")
    print("=" * 44)
    print(f"\nRecords processed : {metrics['total_records']}")
    print(f"Reconciled        : {metrics['reconciled_records']}")
    print(f"Exceptions        : {metrics['exception_records']}")
    print(f"Match rate        : {fmt_pct(metrics['match_rate'])}")
    print()
    print("-" * 44)
    print("PHASE 1 EXCEPTION BREAKDOWN")
    print("-" * 44)
    sorted_bd = sorted(metrics["breakdown"].items(), key=lambda x: x[1], reverse=True)
    for reason, count in sorted_bd:
        print(f"  {reason:<32} {count:>3}")
    print()


def print_phase2_summary(combined: Dict[str, Any]) -> None:
    print("=" * 44)
    print("         AI FINANCE CONTROLLER")
    print("       PHASE 2: AI INVESTIGATION")
    print("=" * 44)
    print()
    print(f"Total transactions       : {combined['total_records']}")
    print(f"Initially reconciled     : {combined['phase1_reconciled']}")
    print(f"Initial exceptions       : {combined['phase1_exceptions']}")
    print(f"Initial match rate       : {fmt_pct(combined['initial_match_rate'])}")
    print()
    print(f"AI auto-resolved         : {combined['auto_resolved']}")
    print(f"Human review required    : {combined['human_review_required']}")
    print(f"Agent resolution rate    : {fmt_pct(combined['agent_resolution_rate'])}")
    print()
    print(f"Final resolved           : {combined['final_resolved']}")
    print(f"Final unresolved         : {combined['final_unresolved']}")
    print(f"Final resolution rate    : {fmt_pct(combined['final_resolution_rate'])}")
    print()


def print_evaluation(eval_metrics) -> None:
    print("-" * 44)
    print("AGENT ACCURACY vs GROUND TRUTH")
    print("-" * 44)
    print(f"  Total decisions   : {eval_metrics.agent_total_decisions}")
    print(f"  Correct decisions : {eval_metrics.agent_correct_decisions}")
    print(f"  Accuracy          : {fmt_pct(eval_metrics.agent_accuracy)}")
    print()
    print(f"  AUTO_RESOLVED  correct: {eval_metrics.auto_resolved_correct}/{eval_metrics.auto_resolved_total}")
    print(f"  HUMAN_REVIEW   correct: {eval_metrics.human_review_correct}/{eval_metrics.human_review_total}")
    print()
    print("  Per-category accuracy:")
    for cat, stats in sorted(eval_metrics.category_accuracy.items()):
        c = stats["correct"]
        t = stats["total"]
        pct = (c / t * 100) if t > 0 else 0.0
        print(f"    {cat:<32} {c}/{t}  ({pct:.0f}%)")
    print()


def print_exception_report(
    decisions: List[AgentDecision],
    phase1_exceptions: List[Dict[str, Any]],
) -> None:
    # Build quick lookup for Phase 1 data
    p1_index = {r["transaction_id"]: r for r in phase1_exceptions}

    print("-" * 44)
    print("DETAILED EXCEPTION REPORT")
    print("-" * 44)
    print()

    auto_resolved = [d for d in decisions if d.decision == "AUTO_RESOLVED"]
    human_review = [d for d in decisions if d.decision == "HUMAN_REVIEW"]

    # --- Sample AUTO_RESOLVED cases (show up to 3) ---
    if auto_resolved:
        print(">>> SAMPLE AUTO-RESOLVED CASES")
        print()
        for d in auto_resolved[:3]:
            p1 = p1_index.get(d.transaction_id, {})
            _print_single_exception(d, p1)

    # --- Sample HUMAN_REVIEW cases (show up to 5) ---
    if human_review:
        print(">>> SAMPLE HUMAN REVIEW CASES")
        print()
        for d in human_review[:5]:
            p1 = p1_index.get(d.transaction_id, {})
            _print_single_exception(d, p1)


def _print_single_exception(d: AgentDecision, p1: Dict[str, Any]) -> None:
    print(f"{d.transaction_id}")
    print("-" * 40)
    print(f"Initial exception : {d.exception_type}")
    print(f"Payment amount    : {fmt_currency(p1.get('payment_amount'))}")
    print(f"Expected settlement: {fmt_currency(p1.get('expected_net_amount'))}")
    print(f"Bank amount       : {fmt_currency(p1.get('bank_amount'))}")
    print()
    print(f"Agent decision    : {d.decision}")
    print(f"Reason            : {d.reason}")
    print(f"Recommended action: {d.recommended_action}")
    print(f"Confidence        : {d.confidence * 100:.0f}%")
    print()
    if d.evidence:
        print("Evidence:")
        for ev in d.evidence:
            print(f"  - {ev}")
    print()


def verify_no_source_records_modified(
    original_payments: List[Dict[str, Any]],
    original_ledger: List[Dict[str, Any]],
    original_bank: List[Dict[str, Any]],
    current_payments_path: str,
    current_ledger_path: str,
    current_bank_path: str,
) -> bool:
    """
    Verifies that Phase 2 did not modify any source financial records.

    Compares the in-memory state used by the agent against the files on disk.
    Returns True if no records were modified.
    """
    from src.reconciliation import ReconciliationEngine
    reloaded_payments = ReconciliationEngine.load_csv(current_payments_path)
    reloaded_ledger = ReconciliationEngine.load_csv(current_ledger_path)
    reloaded_bank = ReconciliationEngine.load_csv(current_bank_path)

    def to_str_list(records):
        return [str(sorted(r.items())) for r in records]

    orig_p = set(to_str_list(original_payments))
    curr_p = set(to_str_list(reloaded_payments))
    orig_l = set(to_str_list(original_ledger))
    curr_l = set(to_str_list(reloaded_ledger))
    orig_b = set(to_str_list(original_bank))
    curr_b = set(to_str_list(reloaded_bank))

    return orig_p == curr_p and orig_l == curr_l and orig_b == curr_b


def main() -> None:
    """Full Phase 1 + Phase 2 pipeline execution."""

    data_dir = os.path.join(_project_root, "data")
    payments_path = os.path.join(data_dir, "payments.csv")
    ledger_path = os.path.join(data_dir, "ledger.csv")
    bank_path = os.path.join(data_dir, "bank.csv")

    # ----------------------------------------------------------------
    # Step 1: Generate / ensure fresh data
    # ----------------------------------------------------------------
    print("Generating synthetic data...")
    generator = SyntheticDataGenerator(seed=42, total_transactions=100)
    generator.save_to_csv(data_dir)
    payments_raw, ledger_raw, bank_raw, ground_truth = generator.generate()

    # Save snapshots of original records for integrity verification
    original_payments = list(payments_raw)
    original_ledger = list(ledger_raw)
    original_bank = list(bank_raw)

    # ----------------------------------------------------------------
    # Step 2: Phase 1 batch reconciliation
    # ----------------------------------------------------------------
    print("Running Phase 1 reconciliation...\n")
    phase1_results, phase1_metrics = ReconciliationEngine.reconcile_batch(
        payments_path=payments_path,
        ledger_path=ledger_path,
        bank_path=bank_path,
    )
    print_phase1_summary(phase1_metrics)

    # ----------------------------------------------------------------
    # Step 3: Filter exceptions only
    # ----------------------------------------------------------------
    exceptions = [r for r in phase1_results if r["status"] == "EXCEPTION"]
    reconciled_count = sum(1 for r in phase1_results if r["status"] == "RECONCILED")
    print(f"Sending {len(exceptions)} exception(s) to AI agent (skipping {reconciled_count} reconciled)...\n")

    # ----------------------------------------------------------------
    # Step 4: Build agent (requires OPENAI_API_KEY in environment)
    # ----------------------------------------------------------------
    try:
        toolkit = FinancialToolkit(payments_raw, ledger_raw, bank_raw)
        llm_client = LLMClient()
        agent = AgentController(toolkit=toolkit, llm_client=llm_client)
    except EnvironmentError as e:
        print(f"[ERROR] {e}")
        print("Set OPENAI_API_KEY in your .env file and re-run.")
        sys.exit(1)

    # ----------------------------------------------------------------
    # Step 5: Investigate all exceptions
    # ----------------------------------------------------------------
    agent_decisions: List[AgentDecision] = []
    logs = []

    for i, exc in enumerate(exceptions, 1):
        txn_id = exc.get("transaction_id", "UNKNOWN")
        exc_type = exc.get("reason", "UNKNOWN")
        print(f"  [{i:02d}/{len(exceptions)}] Investigating {txn_id} ({exc_type})...")
        try:
            decision, log = agent.investigate_exception(exc)
            agent_decisions.append(decision)
            logs.append(log)
            print(f"         → {decision.decision} (confidence={decision.confidence:.2f})")
        except Exception as e:
            print(f"         → ERROR: {e}")
            # Safe fallback
            fallback = AgentDecision(
                transaction_id=txn_id,
                decision="HUMAN_REVIEW",
                exception_type=exc_type,
                reason=f"Agent investigation failed with error: {str(e)[:200]}",
                evidence=[f"Phase 1 exception: {exc_type}"],
                confidence=0.0,
                recommended_action="Manual review required.",
            )
            agent_decisions.append(fallback)

    print()

    # ----------------------------------------------------------------
    # Step 6: Combined metrics
    # ----------------------------------------------------------------
    combined = compute_phase2_metrics(phase1_results, agent_decisions, len(phase1_results))
    print_phase2_summary(combined)

    # ----------------------------------------------------------------
    # Step 7: Ground truth evaluation
    # ----------------------------------------------------------------
    eval_metrics = evaluate_agent_decisions(agent_decisions, ground_truth)
    print_evaluation(eval_metrics)

    # ----------------------------------------------------------------
    # Step 8: Exception report (sample cases)
    # ----------------------------------------------------------------
    print_exception_report(agent_decisions, exceptions)

    # ----------------------------------------------------------------
    # Step 9: Source record integrity check
    # ----------------------------------------------------------------
    print("-" * 44)
    print("SOURCE RECORD INTEGRITY CHECK")
    print("-" * 44)
    intact = verify_no_source_records_modified(
        original_payments, original_ledger, original_bank,
        payments_path, ledger_path, bank_path,
    )
    status_icon = "PASS" if intact else "FAIL"
    print(f"  Records unmodified by Phase 2: {status_icon}")
    print(f"  Payment records verified : {len(original_payments)}")
    print(f"  Ledger records verified  : {len(original_ledger)}")
    print(f"  Bank records verified    : {len(original_bank)}")
    print()

    print("=" * 44)
    print("  Phase 1 = deterministic financial truth")
    print("  Phase 2 = AI investigation + escalation")
    print("=" * 44)


if __name__ == "__main__":
    main()
