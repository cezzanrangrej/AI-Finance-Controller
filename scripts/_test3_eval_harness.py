"""
Throwaway harness: run the finance_test_dataset_03 (TEST3_*) dataset through
Phase 1 deterministic reconciliation and (optionally) Phase 2 batch multi-agent
investigation, then report finish_reason per batch, decision accuracy/precision/
recall vs ground_truth.csv, and app-measured token totals.

Usage:
  python scripts/_test3_eval_harness.py --phase1-only
  python scripts/_test3_eval_harness.py --provider openrouter   # needs real creds
  python scripts/_test3_eval_harness.py --provider demo         # offline plumbing check
"""
import argparse
import csv
import logging
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import src.config  # noqa: F401  (loads .env)

from src.reconciliation import ReconciliationEngine
from src.agent.batch_partitioner import partition_exceptions_balanced
from src.agent.pre_filter import (
    prefilter_proven_exceptions,
    print_pre_filter_header,
    print_pre_filter_summary,
)
from src.agent.tools import FinancialToolkit

DATA_DIR = r"C:\Users\cezza\OneDrive\Desktop\finance data\finance_test_dataset_03"
BATCH_SIZE = 5


def load_csv(name):
    with open(os.path.join(DATA_DIR, name), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _pct(value):
    """Formats an Optional rate. Every rate in EvaluationMetrics may be None
    ("not measured"); ``f"{None:.2f}"`` raises TypeError, so the unmeasured
    case is rendered as N/A rather than crashing the harness."""
    return "N/A" if value is None else f"{value:.2f}%"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase1-only", action="store_true")
    ap.add_argument("--provider", default=None, help="openrouter | gemini | demo")
    args = ap.parse_args()

    if args.provider:
        # Point both roles at the requested provider, clearing role-scoped key and
        # model overrides so the provider's own shared credentials apply. Only the
        # in-process environment is touched; .env is left alone.
        os.environ["INVESTIGATOR_PROVIDER"] = args.provider
        os.environ["VERIFIER_PROVIDER"] = args.provider
        for _k in ("INVESTIGATOR_API_KEY", "VERIFIER_API_KEY",
                   "INVESTIGATOR_MODEL", "VERIFIER_MODEL"):
            os.environ.pop(_k, None)

    payments = load_csv("payments.csv")
    ledger = load_csv("ledger.csv")
    bank = load_csv("bank.csv")
    adjustments = load_csv("adjustments.csv")
    gt_rows = load_csv("ground_truth.csv")

    print(f"Loaded: payments={len(payments)} ledger={len(ledger)} bank={len(bank)} "
          f"adjustments={len(adjustments)} ground_truth={len(gt_rows)}")

    # ---- Phase 1 ----
    results, metrics = ReconciliationEngine.reconcile_records(payments, ledger, bank)
    exceptions = [r for r in results if r.get("status") == "EXCEPTION"]
    print("\n=== PHASE 1 RECONCILIATION ===")
    print(f"Total records:     {len(results)}")
    print(f"Reconciled:        {metrics.get('reconciled_records')}")
    print(f"Exceptions:        {metrics.get('exception_records')}  ({len(exceptions)} EXCEPTION rows)")

    by_reason = {}
    for e in exceptions:
        by_reason[e.get("reason")] = by_reason.get(e.get("reason"), 0) + 1
    print("Exception breakdown:")
    for k, v in sorted(by_reason.items()):
        print(f"  {k:<26} {v}")

    print("\nException transaction IDs (in order):")
    exc_ids = [e.get("transaction_id") for e in exceptions]
    print("  " + ", ".join(exc_ids))

    # Cross-check vs ground truth labels
    gt_index = {r["transaction_id"]: r for r in gt_rows}
    gt_auto = sum(1 for e in exceptions
                  if gt_index.get(e["transaction_id"], {}).get("expected_phase2_decision") == "AUTO_RESOLVED")
    gt_hr = sum(1 for e in exceptions
                if gt_index.get(e["transaction_id"], {}).get("expected_phase2_decision") == "HUMAN_REVIEW")
    gt_na = len(exceptions) - gt_auto - gt_hr
    print(f"\nGround-truth labels over detected exceptions: "
          f"AUTO_RESOLVED={gt_auto}  HUMAN_REVIEW={gt_hr}  N/A-or-missing={gt_na}")

    # Flag mismatches between engine-detected exceptions and GT's is_phase1_exception flag
    gt_flagged = {r["transaction_id"] for r in gt_rows if str(r.get("is_phase1_exception", "")).strip().upper() == "TRUE"}
    detected = set(exc_ids)
    only_detected = detected - gt_flagged
    only_flagged = gt_flagged - detected
    if only_detected:
        print(f"  [!] Detected by engine but NOT flagged in ground_truth: {sorted(only_detected)}")
    if only_flagged:
        print(f"  [!] Flagged in ground_truth but NOT detected by engine: {sorted(only_flagged)}")

    # ---- Deterministic pre-filter ----
    # Runs before batching and before any LLM call. The batch controller no
    # longer re-checks the arithmetic proof after the Verifier, so anything
    # provable has to be claimed here or it is not claimed at all.
    toolkit = FinancialToolkit(payments, ledger, bank, adjustments)
    print_pre_filter_header()
    pre_filter = prefilter_proven_exceptions(exceptions, toolkit)
    print_pre_filter_summary(pre_filter)
    ambiguous = pre_filter.ambiguous_exceptions

    if pre_filter.pre_resolved_count:
        print("Pre-resolved transaction IDs (Decimal proof, 0 tokens):")
        print("  " + ", ".join(d.transaction_id for d in pre_filter.proven_decisions))

    # ---- Batching ----
    batches = partition_exceptions_balanced(ambiguous, batch_size=BATCH_SIZE) if ambiguous else []
    print(f"\n=== BATCHING (batch_size={BATCH_SIZE}) -> {len(batches)} batches ===")
    for i, b in enumerate(batches, 1):
        ids = [c.get("transaction_id") for c in b]
        print(f"  Batch {i}: {len(b)} cases -> {', '.join(ids)}")

    if args.phase1_only:
        print("\n[phase1-only] Stopping before any LLM calls.")
        return

    # ---- Phase 2 (paid / live) ----
    print("\n=== PHASE 2 BATCH MULTI-AGENT ===")
    from src.agent.multi_agent.batch_multi_agent_controller import BatchMultiAgentController
    from src.agent.evaluator import evaluate_agent_decisions

    if not batches:
        print("Every Phase 1 exception was closed by deterministic proof — no LLM invocation required.")

    controller = BatchMultiAgentController(toolkit=toolkit, provider=args.provider)
    print(f"Investigator: provider={getattr(controller.investigator_llm, 'provider_name', '?')} "
          f"model={getattr(controller.investigator_llm, 'model', '?')}")
    print(f"Verifier:     provider={getattr(controller.verifier_llm, 'provider_name', '?')} "
          f"model={getattr(controller.verifier_llm, 'model', '?')}")

    # Capture finish_reason per LLM call by wrapping the instance chat methods.
    finish_reasons = {"investigator": [], "verifier": []}

    def wrap(client, role):
        orig = client.chat

        def wrapped(*a, **k):
            resp = orig(*a, **k)
            fr = None
            try:
                fr = resp.choices[0].finish_reason
            except Exception:
                fr = "<no-finish_reason>"
            finish_reasons[role].append(fr)
            return resp
        client.chat = wrapped

    wrap(controller.investigator_llm, "investigator")
    wrap(controller.verifier_llm, "verifier")

    # Capture parse-failure WARNINGs emitted by the controller.
    warn_records = []

    class _Collector(logging.Handler):
        def emit(self, record):
            warn_records.append(record.getMessage())

    ctrl_logger = logging.getLogger("src.agent.multi_agent.batch_multi_agent_controller")
    ctrl_logger.setLevel(logging.WARNING)
    ctrl_logger.addHandler(_Collector())

    controller.investigator_llm.reset_cumulative_tokens()
    controller.verifier_llm.reset_cumulative_tokens()

    all_decisions = list(pre_filter.proven_decisions)
    for i, b in enumerate(batches, 1):
        inv_before = len(finish_reasons["investigator"])
        ver_before = len(finish_reasons["verifier"])
        decs, log = controller.investigate_batch(b)
        all_decisions.extend(decs)
        inv_fr = finish_reasons["investigator"][inv_before:]
        ver_fr = finish_reasons["verifier"][ver_before:]
        print(f"  Batch {i}: fallback_count={log.fallback_count} "
              f"inv_finish_reason={inv_fr} ver_finish_reason={ver_fr} "
              f"cum_total_tokens={log.total_tokens}")
        for d in decs:
            print(f"      {d.transaction_id}: {d.decision} ({d.resolution_type})")

    # ---- Metrics ----
    gt = [{"transaction_id": r["transaction_id"],
           "expected_phase2_decision": r["expected_phase2_decision"]} for r in gt_rows]
    m = evaluate_agent_decisions(all_decisions, gt, is_subset=True, total_selected=len(all_decisions))

    inv_tot = controller.investigator_llm.cumulative_total_tokens
    ver_tot = controller.verifier_llm.cumulative_total_tokens

    print("\n=== RESULTS ===")
    print(f"Cases evaluated:            {len(all_decisions)}")
    print(f"  via Decimal proof:        {pre_filter.pre_resolved_count} (0 LLM tokens)")
    print(f"  via AI multi-agent:       {len(ambiguous)}")
    print(f"Parse-failure warnings:     {len(warn_records)}")
    for w in warn_records:
        print(f"    WARN: {w}")
    all_fr = finish_reasons["investigator"] + finish_reasons["verifier"]
    print(f"All finish_reasons:         {all_fr}")
    print(f"All == 'stop':              {all(fr == 'stop' for fr in all_fr) if all_fr else 'N/A'}")
    print(f"Decision accuracy:          {_pct(m.phase2_decision_accuracy)}")
    print(f"Auto-resolution precision:  {_pct(m.auto_resolution_precision)}")
    print(f"Auto-resolution recall:     {_pct(m.auto_resolution_recall)}")
    print(f"Labelled / unlabelled:      {m.phase2_labelled_cases} / {m.phase2_unlabelled_cases}")
    print(f"Auto-resolved (correct):    {m.auto_resolved_total} ({m.auto_resolved_correct})")
    print(f"Human-review total:         {m.human_review_total}")
    print(f"App-measured tokens:        investigator={inv_tot} verifier={ver_tot} total={inv_tot + ver_tot}")


if __name__ == "__main__":
    main()
