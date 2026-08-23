"""
Provider-neutral Real LLM Multi-Run Evaluation script for AI Finance Controller.

Processes the full 100-record synthetic dataset through deterministic Phase 1 reconciliation,
deterministically partitions Phase 1 exceptions across multiple runs, investigates
each subset sequentially with the configured LLM provider, saves JSON reports,
and calculates per-run and aggregate evaluation metrics.
"""

import argparse
import json
import os
import sys
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

# Ensure project root on path
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.abspath(os.path.join(_current_dir, ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import src.config  # Loads .env variables

# Configure UTF-8 encoding for standard output
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

from src.agent.batch_controller import BatchAgentController
from src.agent.controller import AgentController, LLMClient
from src.agent.evaluator import (
    compute_aggregate_metrics,
    evaluate_agent_decisions,
    partition_evaluation_runs,
)
from src.agent.schemas import AgentDecision
from src.agent.tools import FinancialToolkit
from src.db.database import SessionLocal, init_db
from src.db.repository import FinanceRepository
from src.generator import SyntheticDataGenerator
from src.reconciliation import ReconciliationEngine


def run_evaluation(
    provider: Optional[str] = None,
    cases: int = 5,
    runs: int = 1,
    batch_size: int = 5,
    mode: str = "batch",
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    resume_group_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Executes single or multi-run subset evaluation for the specified LLM provider,
    supporting INDIVIDUAL, BATCH, and COMPARE investigation modes.

    Args:
        provider: 'openrouter', 'gemini', or 'demo'. Defaults to LLM_PROVIDER or 'openrouter'.
        cases: Number of Phase 1 exceptions to evaluate per run (default: 5).
        runs: Number of evaluation runs to execute (default: 1).
        batch_size: Number of cases per batch in BATCH mode (default: 5, range: 1-10).
        mode: 'individual', 'batch', or 'compare' (default: 'batch').
        model: Optional model override.
        api_key: Optional API key override.
        resume_group_id: Optional group ID to resume unfinished runs.

    Returns:
        Dictionary containing aggregate evaluation summary metrics and per-run results.
    """
    if cases < 1:
        raise ValueError(f"cases must be >= 1, got {cases}")
    if runs < 1:
        raise ValueError(f"runs must be >= 1, got {runs}")
    if batch_size < 1 or batch_size > 10:
        raise ValueError(f"batch_size must be between 1 and 10, got {batch_size}")
    if mode not in ("individual", "batch", "compare"):
        raise ValueError(f"mode must be 'individual', 'batch', or 'compare', got '{mode}'")


    selected_provider = (
        provider or os.getenv("LLM_PROVIDER") or "openrouter"
    ).strip().lower()

    # Validate provider credentials before starting
    if selected_provider == "openrouter":
        or_key = (api_key or os.getenv("OPENROUTER_API_KEY") or "").strip()
        if not or_key:
            print("\n========================================")
            print("AI FINANCE CONTROLLER")
            print("REAL LLM EVALUATION")
            print("========================================\n")
            print("Status: Pending OpenRouter API Credentials.")
            print("Reason: OPENROUTER_API_KEY environment variable is not set.\n")
            print("To run the real OpenRouter evaluation:")
            print("  1. Set OPENROUTER_API_KEY=your_key in .env")
            print("  2. Set OPENROUTER_MODEL=your_model (e.g. meta-llama/llama-3.3-70b-instruct) in .env")
            print(f"  3. Re-run: python src/run_llm_eval.py --provider openrouter --cases {cases} --runs {runs}\n")
            print(f"Offline Demo Mode remains fully functional: python src/run_llm_eval.py --provider demo --cases {cases} --runs {runs}\n")
            return {"status": "SKIPPED", "reason": "Missing OPENROUTER_API_KEY"}

        or_model = (model or os.getenv("OPENROUTER_MODEL") or "").strip()
        if not or_model:
            print("\n========================================")
            print("AI FINANCE CONTROLLER")
            print("REAL LLM EVALUATION")
            print("========================================\n")
            print("Status: Pending OpenRouter Model Configuration.")
            print("Reason: OPENROUTER_MODEL environment variable is not set.\n")
            print("Please set OPENROUTER_MODEL in .env (e.g. OPENROUTER_MODEL=meta-llama/llama-3.3-70b-instruct).\n")
            return {"status": "SKIPPED", "reason": "Missing OPENROUTER_MODEL"}

    elif selected_provider == "gemini":
        gem_key = (api_key or os.getenv("GEMINI_API_KEY") or "").strip()
        if not gem_key:
            print("\n========================================")
            print("AI FINANCE CONTROLLER")
            print("REAL LLM EVALUATION")
            print("========================================\n")
            print("Status: Pending Gemini API Credentials.")
            print("Reason: GEMINI_API_KEY environment variable is not set.\n")
            print("To run the real Gemini evaluation:")
            print("  1. Set GEMINI_API_KEY=your_key in .env")
            print(f"  2. Re-run: python src/run_llm_eval.py --provider gemini --cases {cases} --runs {runs}\n")
            return {"status": "SKIPPED", "reason": "Missing GEMINI_API_KEY"}

    elif selected_provider != "demo":
        raise ValueError(
            f"Unsupported LLM_PROVIDER '{selected_provider}'. Valid options are 'openrouter', 'gemini', or 'demo'."
        )

    init_db()
    data_dir = os.path.join(_project_root, "data")
    eval_dir = os.path.join(data_dir, "evaluations")
    os.makedirs(eval_dir, exist_ok=True)

    generator = SyntheticDataGenerator(seed=42, total_transactions=100)
    p_path, l_path, b_path, a_path = generator.save_to_csv(data_dir)
    payments, ledger, bank, adjustments, ground_truth = generator.generate()

    # Step 1: Phase 1 Deterministic Reconciliation over ALL 100 records
    t_p1_start = time.time()
    phase1_results, phase1_metrics = ReconciliationEngine.reconcile_batch(p_path, l_path, b_path)
    t_p1_end = time.time()
    phase1_time_sec = max(t_p1_end - t_p1_start, 0.001)

    all_exceptions = [r for r in phase1_results if r["status"] == "EXCEPTION"]
    reconciled_count = phase1_metrics["reconciled_records"]
    exception_count = phase1_metrics["exception_records"]

    # Step 2: Strict Total-Case Safety Validation & Deterministic Partitioning
    total_requested_cases = cases * runs
    if total_requested_cases > len(all_exceptions):
        raise ValueError(
            f"Requested total cases ({total_requested_cases} = {runs} runs x {cases} cases) "
            f"exceeds available Phase 1 exceptions ({len(all_exceptions)}). "
            f"Maximum possible runs with {cases} cases/run is {len(all_exceptions) // cases}."
        )

    partitioned_runs = partition_evaluation_runs(
        exceptions=all_exceptions,
        ground_truth=ground_truth,
        cases_per_run=cases,
        runs=runs,
    )

    provider_display_name = {
        "openrouter": "OpenRouter",
        "gemini": "Gemini",
        "demo": "Demo",
    }.get(selected_provider, selected_provider.capitalize())

    client_model = model or (
        os.getenv("OPENROUTER_MODEL") if selected_provider == "openrouter"
        else os.getenv("GEMINI_MODEL") if selected_provider == "gemini"
        else "demo"
    )

    evaluation_group_id = resume_group_id or f"eval_group_{uuid.uuid4().hex[:10]}"

    # Step 3: Print Pre-Execution Evaluation Plan
    print("\n========================================")
    print("REAL LLM EVALUATION PLAN" if selected_provider != "demo" else "DEMO EVALUATION PLAN")
    print("========================================\n")
    print(f"Provider: {provider_display_name}")
    print(f"Model: {client_model}")
    print(f"Mode:  {mode.upper()}" + (f" (batch_size={batch_size})" if mode in ("batch", "compare") else "") + "\n")
    print(f"Full dataset:              {len(phase1_results)}")
    print(f"Phase 1 exceptions:         {exception_count}\n")
    print(f"Runs:                         {runs}")
    print(f"Cases per run:                {cases}")
    print(f"Total LLM cases:             {total_requested_cases}\n")

    for r_idx, run_cases in enumerate(partitioned_runs, 1):
        print(f"Run {r_idx}:")
        for c in run_cases:
            print(f"  {c.get('transaction_id')}")
        print()
    print("========================================\n")

    # Helper to execute a set of cases under a given mode
    def execute_eval_mode(eval_mode: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any], int, int, int]:
        llm_client = LLMClient(provider=selected_provider, api_key=api_key, model=client_model)
        toolkit = FinancialToolkit(payments, ledger, bank, adjustments)
        agent = AgentController(toolkit=toolkit, llm_client=llm_client)
        batch_agent = BatchAgentController(toolkit=toolkit, llm_client=llm_client)

        completed_run_numbers = set()
        existing_results = []
        file_suffix = f"_{eval_mode}" if mode == "compare" else ""
        resume_file = os.path.join(eval_dir, f"{evaluation_group_id}{file_suffix}.json")
        if resume_group_id and os.path.exists(resume_file):
            try:
                with open(resume_file, "r", encoding="utf-8") as f:
                    saved_data = json.load(f)
                    existing_results = saved_data.get("results", [])
                    completed_run_numbers = {r["run_number"] for r in existing_results}
                    print(f"[Resume] Found {len(completed_run_numbers)} previously completed runs in group '{evaluation_group_id}{file_suffix}'.\n")
            except Exception as e:
                print(f"[Resume] Warning: Could not parse {resume_file}: {e}")


        per_run_sums: List[Dict[str, Any]] = list(existing_results)
        total_batches_processed = 0
        total_batch_llm_interactions = 0
        total_individual_fallbacks = 0

        for run_num, run_cases in enumerate(partitioned_runs, 1):
            if run_num in completed_run_numbers:
                print(f"--- Skipping Run {run_num}/{runs} (Already completed in resume group) ---")
                continue

            run_id = f"run_{selected_provider}_{eval_mode}_{uuid.uuid4().hex[:8]}"
            t_run_start = time.time()

            if hasattr(llm_client, "reset_cumulative_tokens"):
                llm_client.reset_cumulative_tokens()

            print(f"--- Starting Run {run_num}/{runs} ({len(run_cases)} cases | Mode: {eval_mode.upper()}) ---")
            agent_decisions: List[AgentDecision] = []
            investigation_logs: List[Dict[str, Any]] = []

            cases_selected = len(run_cases)
            cases_completed = 0
            cases_not_evaluated = 0

            if eval_mode == "batch":
                # Split run_cases into chunks of batch_size
                for b_start in range(0, len(run_cases), batch_size):
                    chunk = run_cases[b_start : b_start + batch_size]
                    chunk_tids = [c.get("transaction_id") for c in chunk]
                    total_batches_processed += 1
                    print(f"  [Batch {total_batches_processed}] Investigating {len(chunk)} cases ({', '.join(chunk_tids)})...")

                    chunk_decisions, batch_log = batch_agent.investigate_batch(chunk)
                    total_batch_llm_interactions += batch_log.llm_interactions
                    total_individual_fallbacks += batch_log.fallback_count

                    for d in chunk_decisions:
                        agent_decisions.append(d)
                        exc_obj = next((c for c in chunk if c.get("transaction_id") == d.transaction_id), {})
                        t_log = {
                            "transaction_id": d.transaction_id,
                            "initial_exception": d.exception_type or exc_obj.get("reason", "UNKNOWN"),
                            "tools_used": ["batch_prefetch"],
                            "evidence": d.evidence or [],
                            "decision": d.decision,
                            "resolution_type": d.resolution_type or "NONE",
                            "resolved_difference": d.resolved_difference,
                            "reason": d.reason,
                            "confidence": d.confidence,
                            "recommended_action": d.recommended_action,
                            "tool_call_count": 0,
                            "tool_traces": [],
                        }
                        investigation_logs.append(t_log)

                        if d.decision == "NOT_EVALUATED":
                            cases_not_evaluated += 1
                            print(f"    -> {d.transaction_id}: NOT_EVALUATED | Reason: {d.reason}")
                        else:
                            cases_completed += 1
                            print(f"    -> {d.transaction_id}: {d.decision} ({d.resolution_type})")
            else:

                # Individual mode
                for idx, exc in enumerate(run_cases, 1):
                    txn_id = exc.get("transaction_id", "UNKNOWN")
                    reason = exc.get("reason", "UNKNOWN")
                    print(f"  [{idx}/{cases_selected}] Investigating {txn_id} ({reason})...")

                    decision, log = agent.investigate_exception(exc)
                    agent_decisions.append(decision)
                    investigation_logs.append(log.model_dump())

                    if decision.decision == "NOT_EVALUATED":
                        cases_not_evaluated += 1
                        print(f"    -> Decision: NOT_EVALUATED | Reason: {decision.reason}")
                    else:
                        cases_completed += 1
                        print(f"    -> Decision: {decision.decision} ({decision.resolution_type}) | Tools used: {log.tool_call_count}")

            t_run_end = time.time()
            phase2_time_sec = max(t_run_end - t_run_start, 0.001)

            # Record unselected exceptions as NOT_EVALUATED for database integrity
            selected_txn_ids = {c["transaction_id"] for c in run_cases}
            for unselected in all_exceptions:
                if unselected["transaction_id"] not in selected_txn_ids:
                    unselected_log = {
                        "transaction_id": unselected["transaction_id"],
                        "initial_exception": unselected.get("reason", "UNKNOWN"),
                        "tools_used": [],
                        "evidence": [f"Unselected in Run {run_num} (budget={cases})"],
                        "decision": "NOT_EVALUATED",
                        "resolution_type": "NONE",
                        "resolved_difference": None,
                        "reason": f"Case not evaluated in Run {run_num}.",
                        "confidence": 0.0,
                        "recommended_action": "Refer to target evaluation run.",
                        "tool_call_count": 0,
                        "tool_traces": [],
                    }
                    investigation_logs.append(unselected_log)

            run_prompt_tokens = getattr(llm_client, "cumulative_prompt_tokens", 0)
            run_completion_tokens = getattr(llm_client, "cumulative_completion_tokens", 0)
            run_total_tokens = getattr(llm_client, "cumulative_total_tokens", 0)

            # Compute per-run metrics
            eval_results = evaluate_agent_decisions(
                agent_decisions=agent_decisions,
                ground_truth=ground_truth,
                is_subset=True,
                total_selected=cases_selected,
            )

            auto_resolved = eval_results.auto_resolved_total
            human_review = eval_results.human_review_total
            decision_accuracy = eval_results.phase2_decision_accuracy
            precision = eval_results.auto_resolution_precision
            recall = eval_results.auto_resolution_recall

            llm_mode = f"{eval_mode.upper()}_{selected_provider.upper()}"
            total_records = len(phase1_results)
            initial_reconciled = phase1_metrics["reconciled_records"]
            initial_exceptions = phase1_metrics["exception_records"]
            final_resolved = initial_reconciled + auto_resolved
            final_unresolved = human_review

            # Save run to database
            run_data = {
                "id": run_id,
                "total_records": total_records,
                "initial_reconciled": initial_reconciled,
                "initial_exceptions": initial_exceptions,
                "ai_auto_resolved": auto_resolved,
                "human_review": human_review,
                "final_resolved": final_resolved,
                "final_unresolved": final_unresolved,
                "initial_match_rate": phase1_metrics["match_rate"],
                "agent_resolution_rate": (auto_resolved / initial_exceptions * 100) if initial_exceptions > 0 else 0.0,
                "final_resolution_rate": (final_resolved / total_records * 100) if total_records > 0 else 0.0,
                "llm_provider": selected_provider,
                "llm_mode": llm_mode,
                "llm_model": getattr(llm_client, "model", client_model),
                "prompt_tokens": run_prompt_tokens if run_prompt_tokens > 0 else None,
                "completion_tokens": run_completion_tokens if run_completion_tokens > 0 else None,
                "total_tokens": run_total_tokens if run_total_tokens > 0 else None,
                "llm_cases_selected": cases_selected,
                "llm_cases_completed": cases_completed,
                "llm_cases_not_evaluated": cases_not_evaluated,
                "evaluation_group_id": evaluation_group_id,
                "evaluation_run_number": run_num,
                "evaluation_runs_total": runs,
                "phase1_accuracy": eval_results.phase1_accuracy,
                "phase2_accuracy": decision_accuracy,
                "auto_resolution_precision": precision,
                "auto_resolution_recall": recall,
                "ground_truth_accuracy": decision_accuracy,
                "phase1_time_sec": round(phase1_time_sec, 4),
                "phase2_time_sec": round(phase2_time_sec, 4),
                "end_to_end_time_sec": round(phase1_time_sec + phase2_time_sec, 4),
                "total_processing_time_sec": round(phase1_time_sec + phase2_time_sec, 4),
                "records_per_second": round(total_records / phase1_time_sec, 2),
                "average_time_per_record_sec": round((phase1_time_sec + phase2_time_sec) / total_records, 6),
            }

            db = SessionLocal()
            try:
                FinanceRepository.create_run(db, run_data)
                FinanceRepository.save_transaction_results(db, run_id, phase1_results)
                FinanceRepository.save_adjustments(db, run_id, adjustments)
                FinanceRepository.save_agent_investigations(db, run_id, investigation_logs)
            finally:
                db.close()

            per_run_summary = {
                "run_number": run_num,
                "run_id": run_id,
                "cases_selected": cases_selected,
                "cases_completed": cases_completed,
                "cases_not_evaluated": cases_not_evaluated,
                "correct_decisions": eval_results.agent_correct_decisions,
                "auto_resolved": auto_resolved,
                "auto_resolved_correct": eval_results.auto_resolved_correct,
                "human_review": human_review,
                "human_review_correct": eval_results.human_review_correct,
                "ground_truth_auto_resolvable": eval_results.ground_truth_auto_resolvable,
                "decision_accuracy": round(decision_accuracy, 2),
                "auto_resolution_precision": round(precision, 2),
                "auto_resolution_recall": round(recall, 2),
                "phase2_time_sec": round(phase2_time_sec, 4),
                "total_tokens": run_total_tokens if run_total_tokens > 0 else None,
                "investigated_cases": [d.model_dump(mode="json") for d in agent_decisions],
            }
            per_run_sums.append(per_run_summary)

            # Update JSON report on disk
            curr_agg = compute_aggregate_metrics(per_run_sums)
            report_data = {
                "evaluation_group_id": evaluation_group_id,
                "mode": eval_mode,
                "provider": selected_provider,
                "model": getattr(llm_client, "model", client_model),
                "dataset_size": len(phase1_results),
                "phase1_exception_count": exception_count,
                "runs": runs,
                "cases_per_run": cases,
                "batch_size": batch_size if eval_mode == "batch" else 1,
                "results": per_run_sums,
                "aggregate_metrics": curr_agg,
            }
            with open(resume_file, "w", encoding="utf-8") as f:
                json.dump(report_data, f, indent=2)

        agg = compute_aggregate_metrics(per_run_sums)
        return per_run_sums, agg, total_batches_processed, total_batch_llm_interactions, total_individual_fallbacks

    # Execute based on requested mode
    if mode == "compare":
        print("\n" + "=" * 50)
        print("RUNNING PHASE 1: INDIVIDUAL MODE EVALUATION")
        print("=" * 50)
        ind_sums, ind_agg, _, _, _ = execute_eval_mode("individual")

        print("\n" + "=" * 50)
        print("RUNNING PHASE 2: BATCH MODE EVALUATION")
        print("=" * 50)
        batch_sums, batch_agg, batches_done, batch_interactions, batch_fallbacks = execute_eval_mode("batch")

        ind_time = ind_agg["total_processing_time_sec"]
        batch_time = batch_agg["total_processing_time_sec"]
        lat_red = ((ind_time - batch_time) / ind_time * 100) if ind_time > 0 else 0.0

        ind_toks = ind_agg["total_tokens"]
        batch_toks = batch_agg["total_tokens"]
        tok_red = ((ind_toks - batch_toks) / ind_toks * 100) if ind_toks > 0 else 0.0

        print("\n========================================")
        print("INVESTIGATION MODE COMPARISON")
        print("========================================")
        print(f"Provider: {provider_display_name}")
        print(f"Model:    {client_model}")
        print(f"Cases:    {ind_agg['total_completed']}\n")
        print(f"{'Metric':<25} {'Individual':<16} {f'Batch (size {batch_size})':<18} {'Reduction'}")
        print("-" * 72)
        print(f"{'Total Latency':<25} {ind_time:>10.4f}s      {batch_time:>12.4f}s       {lat_red:>7.1f}%")
        print(f"{'Avg Latency / Case':<25} {ind_agg['average_case_latency_sec']:>10.4f}s      {batch_agg['average_case_latency_sec']:>12.4f}s       {lat_red:>7.1f}%")
        print(f"{'Total Tokens':<25} {ind_toks:>10,d}        {batch_toks:>12,d}         {tok_red:>7.1f}%")
        print(f"{'Avg Tokens / Case':<25} {ind_agg['average_tokens_per_case']:>10,d}        {batch_agg['average_tokens_per_case']:>12,d}         {tok_red:>7.1f}%")
        print(f"{'Decision Accuracy':<25} {ind_agg['decision_accuracy']:>9.2f}%      {batch_agg['decision_accuracy']:>11.2f}%")
        print(f"{'Auto-Res Precision':<25} {ind_agg['auto_resolution_precision']:>9.2f}%      {batch_agg['auto_resolution_precision']:>11.2f}%")
        print(f"{'Auto-Res Recall':<25} {ind_agg['auto_resolution_recall']:>9.2f}%      {batch_agg['auto_resolution_recall']:>11.2f}%")
        print("========================================\n")

        return {
            "evaluation_group_id": evaluation_group_id,
            "provider": selected_provider,
            "model": client_model,
            "mode": "compare",
            "individual_aggregate": ind_agg,
            "batch_aggregate": batch_agg,
            "latency_reduction_percent": round(lat_red, 2),
            "token_reduction_percent": round(tok_red, 2),
        }

    else:
        # Run single mode (batch or individual)
        eval_sums, agg, batches_done, batch_interactions, batch_fallbacks = execute_eval_mode(mode)

        total_tokens_val = agg["total_tokens"]
        tok_str = f"{total_tokens_val:,}" if total_tokens_val > 0 else "unknown"

        if mode == "batch":
            print("\n========================================")
            print("LLM INVESTIGATION PERFORMANCE")
            print("========================================\n")
            print("Mode: BATCH\n")
            print(f"Provider: {provider_display_name}")
            print(f"Model: {client_model}\n")
            print(f"Cases evaluated:            {agg['total_completed']}")
            print(f"Batch size:                  {batch_size}")
            print(f"Batches processed:           {batches_done}\n")
            print(f"Batch LLM interactions:      {batch_interactions}")
            print(f"Individual fallbacks:        {batch_fallbacks}\n")
            print(f"Decision accuracy:           {agg['decision_accuracy']:.2f}%")
            print(f"Auto-resolution precision:   {agg['auto_resolution_precision']:.2f}%")
            print(f"Auto-resolution recall:      {agg['auto_resolution_recall']:.2f}%\n")
            print(f"Processing time:             {agg['total_processing_time_sec']:.4f} sec")
            print(f"Average case latency:        {agg['average_case_latency_sec']:.4f} sec\n")
            print(f"Total tokens:                {tok_str}")
            print(f"Average tokens/case:         {agg['average_tokens_per_case']:,}")
            print("========================================\n")
        else:
            print("\n========================================")
            print("AI FINANCE CONTROLLER")
            print(f"{selected_provider.upper()} EVALUATION (INDIVIDUAL MODE)")
            print("========================================\n")
            print(f"Provider: {provider_display_name}")
            print(f"Model: {client_model}\n")
            print(f"Full dataset:              {len(phase1_results)}")
            print(f"Phase 1 exceptions:         {exception_count}\n")
            print(f"Evaluation runs:             {runs}")
            print(f"Cases per run:               {cases}")
            print(f"Total selected cases:       {agg['total_selected']}")
            print(f"Completed cases:             {agg['total_completed']}")
            print(f"Not evaluated:               {agg['total_not_evaluated']}\n")
            print("----------------------------------------")
            print("AGGREGATE RESULTS")
            print("----------------------------------------\n")
            print(f"Auto-resolved:               {agg['auto_resolved']}")
            print(f"Human review:                {agg['human_review']}")
            print(f"Not evaluated:                {agg['total_not_evaluated']}\n")
            print(f"Decision accuracy:           {agg['decision_accuracy']:.2f}%")
            print(f"Auto-resolution precision:   {agg['auto_resolution_precision']:.2f}%")
            print(f"Auto-resolution recall:      {agg['auto_resolution_recall']:.2f}%")
            print(f"Human-review rate:           {agg['human_review_rate']:.2f}%\n")
            print(f"Total processing time:       {agg['total_processing_time_sec']:.4f} sec")
            print(f"Average case latency:        {agg['average_case_latency_sec']:.4f} sec\n")
            print(f"Total tokens:                {tok_str}")
            print(f"Average tokens/case:         {agg['average_tokens_per_case']:,}")
            print("========================================\n")

        return {
            "evaluation_group_id": evaluation_group_id,
            "provider": selected_provider,
            "model": client_model,
            "mode": mode,
            "runs": runs,
            "cases_per_run": cases,
            "batch_size": batch_size if mode == "batch" else 1,
            "total_selected": agg["total_selected"],
            "completed": agg["total_completed"],
            "not_evaluated": agg["total_not_evaluated"],
            "auto_resolved": agg["auto_resolved"],
            "human_review": agg["human_review"],
            "aggregate_accuracy": agg["decision_accuracy"] / 100.0,
            "aggregate_precision": agg["auto_resolution_precision"] / 100.0,
            "aggregate_recall": agg["auto_resolution_recall"] / 100.0,
            "human_review_rate": agg["human_review_rate"],
            "not_evaluated_rate": agg["not_evaluated_rate"],
            "total_processing_time_sec": agg["total_processing_time_sec"],
            "average_case_latency_sec": agg["average_case_latency_sec"],
            "total_tokens": agg["total_tokens"],
            "average_tokens_per_case": agg["average_tokens_per_case"],
            "aggregate_metrics": agg,
            "per_run_summaries": eval_sums,
        }


def main():
    parser = argparse.ArgumentParser(
        description="Run LLM evaluation for AI Finance Controller."
    )
    parser.add_argument(
        "--provider",
        type=str,
        default=os.getenv("LLM_PROVIDER", "openrouter"),
        choices=["openrouter", "gemini", "demo"],
        help="LLM provider: openrouter, gemini, or demo (default: openrouter or LLM_PROVIDER)",
    )
    parser.add_argument(
        "--cases",
        type=int,
        default=5,
        help="Number of Phase 1 exceptions to evaluate per run (default: 5)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help="Number of sequential evaluation runs (default: 1)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=5,
        help="Batch size in batch mode (default: 5, range: 1-10)",
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="batch",
        choices=["batch", "individual", "compare"],
        help="Investigation mode: batch, individual, or compare (default: batch)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Model override (e.g. meta-llama/llama-3.3-70b-instruct or gemini-3.5-flash)",
    )
    parser.add_argument(
        "--resume",
        type=str,
        default=None,
        help="Evaluation group ID to resume unfinished runs",
    )
    args = parser.parse_args()

    run_evaluation(
        provider=args.provider,
        cases=args.cases,
        runs=args.runs,
        batch_size=args.batch_size,
        mode=args.mode,
        model=args.model,
        resume_group_id=args.resume,
    )


if __name__ == "__main__":
    main()

