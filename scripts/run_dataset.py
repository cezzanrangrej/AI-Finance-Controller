"""
AI Finance Controller — Dataset Reconciliation CLI.

Runs the existing deterministic Phase 1 reconciliation engine and optional
LLM investigation modes against an explicit four-file dataset directory.

Does NOT modify:
- data/payments.csv, data/ledger.csv, data/bank.csv, data/adjustments.csv
- Ground truth records
- Any source CSVs supplied by the caller

Usage:
    python src/run_dataset.py --data-dir "<path>" [--mode phase1|batch|individual|multi-agent]
    python src/run_dataset.py --data-dir "<path>" --mode batch --provider demo --cases 10
"""

import argparse
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

# Ensure project root on path
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.abspath(os.path.join(_current_dir, ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import src.config  # Loads .env variables

# Configure UTF-8 output
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

from src.reconciliation import ReconciliationEngine
from src.agent.tools import FinancialToolkit
from src.agent.controller import AgentController, LLMClient
from src.agent.batch_controller import BatchAgentController
from src.agent.evaluator import partition_evaluation_runs
from src.agent.schemas import AgentDecision
from src.agent.trace import AgentTracer, parse_bool_env

# ---------------------------------------------------------------------------
# Required dataset files
# ---------------------------------------------------------------------------
REQUIRED_FILES = ["payments.csv", "ledger.csv", "bank.csv", "adjustments.csv"]

# Canonical data directory — used for isolation checks
_CANONICAL_DATA_DIR = os.path.join(_project_root, "data")

# Exception breakdown columns (ordered for output)
EXCEPTION_BREAKDOWN_ORDER = [
    "GROSS_AMOUNT_MISMATCH",
    "MISSING_LEDGER_RECORD",
    "MISSING_BANK_RECORD",
    "BANK_AMOUNT_MISMATCH",
    "DUPLICATE_BANK_RECORD",
    "LEDGER_CALCULATION_ERROR",
]


# ---------------------------------------------------------------------------
# Dataset validation
# ---------------------------------------------------------------------------

def validate_dataset_dir(data_dir: str) -> Dict[str, str]:
    """
    Validates that all required CSV files exist in data_dir.

    Returns:
        Mapping of file basename to absolute path.

    Raises:
        FileNotFoundError: If any required file is missing.
        NotADirectoryError: If data_dir is not a directory.
    """
    abs_dir = os.path.abspath(data_dir)
    if not os.path.isdir(abs_dir):
        raise NotADirectoryError(
            f"Dataset directory does not exist or is not a directory: {abs_dir}"
        )

    paths: Dict[str, str] = {}
    missing: List[str] = []
    for fname in REQUIRED_FILES:
        fpath = os.path.join(abs_dir, fname)
        if not os.path.exists(fpath):
            missing.append(fname)
        else:
            paths[fname] = fpath

    if missing:
        raise FileNotFoundError(
            f"Missing required file(s) in '{abs_dir}': {', '.join(missing)}"
        )

    return paths


# ---------------------------------------------------------------------------
# Dataset loading
# ---------------------------------------------------------------------------

def load_dataset(
    data_dir: str,
) -> Tuple[List[Dict], List[Dict], List[Dict], List[Dict], Optional[List[Dict]], Dict[str, str]]:
    """
    Loads payments, ledger, bank, adjustments CSVs from data_dir.
    Also loads ground_truth.csv if present.

    Returns:
        Tuple of (payments, ledger_rows, bank_rows, adjustments, ground_truth, file_paths)
    """
    file_paths = validate_dataset_dir(data_dir)

    payments = ReconciliationEngine.load_csv(file_paths["payments.csv"])
    ledger_rows = ReconciliationEngine.load_csv(file_paths["ledger.csv"])
    bank_rows = ReconciliationEngine.load_csv(file_paths["bank.csv"])
    adjustments = ReconciliationEngine.load_csv(file_paths["adjustments.csv"])

    gt_path = os.path.join(os.path.abspath(data_dir), "ground_truth.csv")
    ground_truth = (
        ReconciliationEngine.load_csv(gt_path) if os.path.exists(gt_path) else None
    )

    return payments, ledger_rows, bank_rows, adjustments, ground_truth, file_paths


# ---------------------------------------------------------------------------
# Source type detection
# ---------------------------------------------------------------------------

def detect_source_type(data_dir: str) -> str:
    """
    Classifies the dataset directory as 'test_dataset' if it matches the
    canonical project data/ directory, or 'user_uploaded_dataset' otherwise.
    """
    abs_dir = os.path.abspath(data_dir)
    canonical = os.path.abspath(_CANONICAL_DATA_DIR)
    return "test_dataset" if abs_dir == canonical else "user_uploaded_dataset"


# ---------------------------------------------------------------------------
# Phase 1 output
# ---------------------------------------------------------------------------

def print_phase1_report(
    data_dir: str,
    metrics: Dict[str, Any],
    source_type: str,
) -> None:
    """Prints the standard Phase 1 reconciliation report to stdout."""
    abs_dir = os.path.abspath(data_dir)
    dir_name = os.path.basename(abs_dir)

    total = metrics["total_records"]
    reconciled = metrics["reconciled_records"]
    exceptions = metrics["exception_records"]
    match_rate = metrics["match_rate"]
    breakdown: Dict[str, int] = metrics.get("breakdown", {})

    print("\n========================================")
    print("AI FINANCE CONTROLLER")
    print("DATASET RECONCILIATION")
    print("========================================\n")
    print(f"Dataset source:    {dir_name}")
    print(f"Source type:       {source_type}")
    print(f"Dataset:           {abs_dir}\n")
    print(f"Records processed: {total}")
    print(f"Reconciled:        {reconciled}")
    print(f"Exceptions:        {exceptions}")
    print(f"Match rate:        {match_rate:.2f}%\n")
    print("----------------------------------------")
    print("EXCEPTION BREAKDOWN")
    print("----------------------------------------\n")

    printed = set()
    for exc_type in EXCEPTION_BREAKDOWN_ORDER:
        count = breakdown.get(exc_type, 0)
        print(f"  {exc_type:<30} {count}")
        printed.add(exc_type)

    for exc_type, count in sorted(breakdown.items()):
        if exc_type not in printed:
            print(f"  {exc_type:<30} {count}")

    print("\n========================================\n")


# ---------------------------------------------------------------------------
# LLM mode helpers
# ---------------------------------------------------------------------------

def _build_llm_client(provider: str, api_key: Optional[str], model: Optional[str]) -> LLMClient:
    """Constructs an LLMClient for the given provider."""
    return LLMClient(provider=provider, api_key=api_key, model=model)


def _select_exceptions(
    all_exceptions: List[Dict[str, Any]],
    cases: int,
    ground_truth: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Uses the existing deterministic partition logic to select cases exceptions.
    """
    if cases <= 0:
        return all_exceptions

    available = len(all_exceptions)
    if cases > available:
        raise ValueError(
            f"Requested --cases {cases} exceeds available Phase 1 exceptions ({available})."
        )

    runs = partition_evaluation_runs(
        exceptions=all_exceptions,
        ground_truth=ground_truth or [],
        cases_per_run=cases,
        runs=1,
    )
    return runs[0]


def run_llm_mode(
    data_dir: str,
    mode: str,
    all_exceptions: List[Dict[str, Any]],
    payments: List[Dict],
    ledger_rows: List[Dict],
    bank_rows: List[Dict],
    adjustments: List[Dict],
    provider: str,
    cases: int,
    batch_size: int,
    parallel_batches: Optional[int] = None,
    ground_truth: Optional[List[Dict[str, Any]]] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    trace: Optional[bool] = None,
) -> None:
    """
    Dispatches selected exceptions through the existing batch / individual /
    multi-agent controllers. Reuses all existing agent logic without duplication.
    Prints transaction-level and summary evaluation output when ground_truth is provided.
    """
    trace_enabled = trace if trace is not None else parse_bool_env("SHOW_AGENT_TRACE", False)
    tracer = AgentTracer(enabled=trace_enabled)
    if tracer.enabled:
        tracer.header("AI FINANCE CONTROLLER — DATASET INVESTIGATION TRACE")

    selected = _select_exceptions(all_exceptions, cases, ground_truth=ground_truth)
    if not selected:
        print("[LLM mode] No Phase 1 exceptions to investigate.")
        return

    llm_client = _build_llm_client(provider, api_key, model)
    toolkit = FinancialToolkit(payments, ledger_rows, bank_rows, adjustments)

    print(f"\n--- Investigating {len(selected)} exception(s) [Mode: {mode.upper()}] ---\n")

    decisions: List[AgentDecision] = []
    t_start = time.time()

    if mode in ("batch", "multi-agent"):
        from src.agent.batch_partitioner import partition_exceptions_balanced
        from src.agent.multi_agent.batch_multi_agent_controller import BatchMultiAgentController

        batch_agent = BatchMultiAgentController(
            toolkit=toolkit, provider=provider, api_key=api_key, tracer=tracer
        )
        chunks = partition_exceptions_balanced(selected, batch_size=batch_size)
        total_batches = len(chunks)
        concurrency_limit = src.config.get_max_parallel_batches()
        if parallel_batches is not None:
            actual_parallel_batches = parallel_batches
        else:
            actual_parallel_batches = min(total_batches, concurrency_limit)

        print("\n========================================")
        print("BALANCED PARALLEL MULTI-AGENT BATCH PLAN")
        print("========================================\n")
        print(f"Cases selected:          {len(selected)}")
        print(f"Batch size:               {batch_size}")
        print(f"Total batches:            {total_batches}")
        print(f"Concurrency limit:        {concurrency_limit}")
        print(f"Actual concurrent batches: {actual_parallel_batches}\n")

        for b_idx, chunk in enumerate(chunks, 1):
            type_counts: Dict[str, int] = {}
            for c in chunk:
                etype = c.get("reason") or c.get("exception_type") or c.get("initial_exception") or "UNKNOWN"
                type_counts[etype] = type_counts.get(etype, 0) + 1

            print(f"Batch {b_idx}: {len(chunk)} cases")
            for etype, count in sorted(type_counts.items(), key=lambda x: (-x[1], x[0])):
                print(f"  {etype:<25} {count}")
            print()
        print("========================================\n")

        if actual_parallel_batches > 1:
            import asyncio
            import uuid
            from src.agent.parallel_batch_engine import run_parallel_batches

            parallel_res = asyncio.run(
                run_parallel_batches(
                    batches=chunks,
                    batch_agent=batch_agent,
                    max_parallel_batches=actual_parallel_batches,
                    ground_truth=ground_truth or [],
                    evaluation_group_id=f"eval_ds_{uuid.uuid4().hex[:8]}",
                    run_id=f"run_ds_{uuid.uuid4().hex[:8]}",
                    run_num=1,
                    total_runs=1,
                    cases_per_run=len(selected),
                    batch_size=batch_size,
                    selected_provider=provider,
                    client_model=model or getattr(llm_client, "model", "demo"),
                    phase1_results=all_exceptions,
                    exception_count=len(all_exceptions),
                    resume_file="",
                    tracer=tracer,
                )
            )
            decisions = parallel_res.decisions
        else:
            for b_idx, chunk in enumerate(chunks, 1):
                chunk_tids = [c.get("transaction_id", "?") for c in chunk]
                print(f"  [Batch {b_idx}] Investigating {len(chunk)} cases ({', '.join(chunk_tids)})...")
                chunk_decisions, _log = batch_agent.investigate_batch(chunk)
                for d in chunk_decisions:
                    decisions.append(d)
                    tag = (
                        "NOT_EVALUATED"
                        if d.decision == "NOT_EVALUATED"
                        else f"{d.decision} ({d.resolution_type})"
                    )
                    print(f"    -> {d.transaction_id}: {tag}")

    elif mode == "individual":
        agent = AgentController(toolkit=toolkit, llm_client=llm_client, tracer=tracer)
        for idx, exc in enumerate(selected, 1):
            txn_id = exc.get("transaction_id", "UNKNOWN")
            reason = exc.get("reason", "UNKNOWN")
            print(f"  [{idx}/{len(selected)}] Investigating {txn_id} ({reason}) [Individual]...")
            decision, _log = agent.investigate_exception(exc)
            decisions.append(decision)
            tag = (
                "NOT_EVALUATED"
                if decision.decision == "NOT_EVALUATED"
                else f"{decision.decision} ({decision.resolution_type})"
            )
            print(f"    -> Decision: {tag}")

    elapsed = max(time.time() - t_start, 0.001)

    if ground_truth is not None and len(ground_truth) > 0:
        gt_index = {row["transaction_id"]: row for row in ground_truth}

        print("\n----------------------------------------")
        print("TRANSACTION EVALUATION RESULTS")
        print("----------------------------------------\n")
        print(f"{'Transaction ID':<18} {'Ground-Truth':<20} {'Actual Decision':<20} {'Status'}")
        print("-" * 72)

        correct_count = 0
        incorrect_count = 0
        gt_auto_count = 0
        gt_human_count = 0
        actual_auto_count = 0
        actual_human_count = 0
        auto_correct_count = 0

        for d in decisions:
            tid = d.transaction_id
            gt_row = gt_index.get(tid, {})
            gt_dec = (
                gt_row.get("expected_phase2_decision")
                or gt_row.get("expected_decision")
                or gt_row.get("decision")
            )
            if not gt_dec or gt_dec == "N/A":
                gt_dec = "HUMAN_REVIEW"

            actual_dec = d.decision

            if actual_dec == "NOT_EVALUATED":
                status_str = "NOT_EVALUATED"
            elif actual_dec == gt_dec:
                status_str = "MATCH"
                correct_count += 1
            else:
                status_str = "MISMATCH"
                incorrect_count += 1

            print(f"{tid:<18} {gt_dec:<20} {actual_dec:<20} {status_str}")

            if actual_dec != "NOT_EVALUATED":
                if gt_dec == "AUTO_RESOLVED":
                    gt_auto_count += 1
                elif gt_dec == "HUMAN_REVIEW":
                    gt_human_count += 1

                if actual_dec == "AUTO_RESOLVED":
                    actual_auto_count += 1
                    if gt_dec == "AUTO_RESOLVED":
                        auto_correct_count += 1
                elif actual_dec == "HUMAN_REVIEW":
                    actual_human_count += 1

        print("-" * 72 + "\n")

        evaluated_count = len([d for d in decisions if d.decision != "NOT_EVALUATED"])
        not_eval_count = len(decisions) - evaluated_count

        accuracy = (correct_count / evaluated_count * 100) if evaluated_count > 0 else 0.0
        precision = (auto_correct_count / actual_auto_count * 100) if actual_auto_count > 0 else 100.0
        recall = (auto_correct_count / gt_auto_count * 100) if gt_auto_count > 0 else 100.0

        print("========================================")
        print("EVALUATION SUMMARY")
        print("========================================\n")
        print(f"Cases evaluated:          {evaluated_count}")
        print(f"Correct:                  {correct_count}")
        print(f"Incorrect:                {incorrect_count}")
        print(f"Decision accuracy:        {accuracy:.2f}%\n")
        print(f"Ground-truth AUTO_RESOLVED: {gt_auto_count}")
        print(f"Actual AUTO_RESOLVED:       {actual_auto_count}")
        print(f"Ground-truth HUMAN_REVIEW:  {gt_human_count}")
        print(f"Actual HUMAN_REVIEW:        {actual_human_count}\n")
        print(f"Auto-resolution precision:  {precision:.2f}%")
        print(f"Auto-resolution recall:     {recall:.2f}%")
        print(f"Not evaluated:            {not_eval_count}")
        print(f"Processing time:          {elapsed:.4f} sec")
        print("\n========================================\n")
    else:
        auto_resolved = sum(1 for d in decisions if d.decision == "AUTO_RESOLVED")
        human_review = sum(1 for d in decisions if d.decision == "HUMAN_REVIEW")
        not_eval = sum(1 for d in decisions if d.decision == "NOT_EVALUATED")

        print("\n========================================")
        print("INVESTIGATION SUMMARY")
        print("========================================\n")
        print(f"Mode:              {mode.upper()}")
        print(f"Cases investigated: {len(decisions)}")
        print(f"Auto-resolved:     {auto_resolved}")
        print(f"Human review:      {human_review}")
        print(f"Not evaluated:     {not_eval}")
        print(f"Processing time:   {elapsed:.4f} sec")
        print("\n(No ground truth available — accuracy metrics omitted for user datasets.)")
        print("\n========================================\n")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point. Returns exit code (0 = success, 1 = error)."""
    parser = argparse.ArgumentParser(
        description=(
            "Run AI Finance Controller reconciliation against an explicit dataset directory."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--data-dir",
        required=True,
        metavar="PATH",
        help="Path to directory containing payments.csv, ledger.csv, bank.csv, adjustments.csv",
    )
    parser.add_argument(
        "--mode",
        choices=["phase1", "batch", "individual", "multi-agent"],
        default="phase1",
        help="Execution mode (default: phase1)",
    )
    parser.add_argument(
        "--provider",
        choices=["openrouter", "gemini", "demo"],
        default=None,
        help="LLM provider (required for batch/individual/multi-agent modes)",
    )
    parser.add_argument(
        "--cases",
        type=int,
        default=0,
        metavar="N",
        help="Number of exceptions to investigate (0 = all exceptions)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=5,
        metavar="N",
        help="Batch size for batch mode (1-10, default: 5)",
    )
    parser.add_argument(
        "--parallel-batches",
        type=int,
        default=None,
        metavar="N",
        help="Optional max concurrent batches override (1-5, default: auto)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Override LLM model name",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="Override LLM provider API key",
    )
    parser.add_argument(
        "--trace",
        action="store_true",
        default=False,
        help="Enable live agent trace output",
    )

    args = parser.parse_args(argv)

    if args.mode != "phase1" and args.provider is None:
        args.provider = os.getenv("LLM_PROVIDER", "demo").strip().lower()

    if args.batch_size < 1 or args.batch_size > 10:
        print(
            f"Error: --batch-size must be between 1 and 10, got {args.batch_size}",
            file=sys.stderr,
        )
        return 1

    if args.parallel_batches is not None:
        if args.parallel_batches < 1 or args.parallel_batches > 5:
            print(
                f"Error: --parallel-batches must be between 1 and 5, got {args.parallel_batches}",
                file=sys.stderr,
            )
            return 1

    # Step 1: Validate & load
    try:
        payments, ledger_rows, bank_rows, adjustments, ground_truth, _file_paths = load_dataset(args.data_dir)
    except (FileNotFoundError, NotADirectoryError) as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        return 1

    source_type = detect_source_type(args.data_dir)

    # Step 2: Phase 1 (in-memory, Decimal-safe)
    phase1_results, metrics = ReconciliationEngine.reconcile_records(
        payments, ledger_rows, bank_rows
    )
    all_exceptions = [r for r in phase1_results if r["status"] == "EXCEPTION"]

    # Step 3: Print Phase 1 report
    print_phase1_report(args.data_dir, metrics, source_type)

    # Step 4: Optional LLM investigation
    if args.mode != "phase1":
        if not all_exceptions:
            print("[LLM mode] No Phase 1 exceptions found — nothing to investigate.\n")
            return 0

        effective_cases = args.cases if args.cases > 0 else len(all_exceptions)
        effective_cases = min(effective_cases, len(all_exceptions))

        try:
            run_llm_mode(
                data_dir=args.data_dir,
                mode=args.mode,
                all_exceptions=all_exceptions,
                payments=payments,
                ledger_rows=ledger_rows,
                bank_rows=bank_rows,
                adjustments=adjustments,
                provider=args.provider,
                cases=effective_cases,
                batch_size=args.batch_size,
                parallel_batches=args.parallel_batches,
                ground_truth=ground_truth,
                model=args.model,
                api_key=args.api_key,
                trace=args.trace if args.trace else None,
            )
        except ValueError as exc:
            print(f"\nError: {exc}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
