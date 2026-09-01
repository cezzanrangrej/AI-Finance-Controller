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
from datetime import datetime, timezone
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
from typing import Any, Callable, Dict, List, Optional, Tuple


def run_evaluation(
    provider: Optional[str] = None,
    cases: Optional[int] = None,
    runs: int = 1,
    batch_size: int = 5,
    parallel_batches: Optional[int] = None,
    mode: str = "batch",
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    resume_group_id: Optional[str] = None,
    event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    trace: Optional[bool] = None,
    parallel_benchmark: bool = False,
) -> Dict[str, Any]:
    """
    Executes single or multi-run subset evaluation for the specified LLM provider,
    supporting INDIVIDUAL, BATCH, COMPARE, and MULTI-AGENT investigation modes, with streaming event callbacks.
    """
    if cases is not None and cases < 0:
        raise ValueError(f"cases must be >= 0 (or None for all exceptions), got {cases}")
    if runs < 1:
        raise ValueError(f"runs must be >= 1, got {runs}")
    if batch_size < 1 or batch_size > 10:
        raise ValueError(f"batch_size must be between 1 and 10, got {batch_size}")
    if parallel_batches is not None:
        if parallel_batches < 1 or parallel_batches > 5:
            raise ValueError(f"parallel_batches must be between 1 and 5, got {parallel_batches}")
    if mode not in ("individual", "batch", "compare", "multi-agent"):
        raise ValueError(f"mode must be 'individual', 'batch', 'compare', or 'multi-agent', got '{mode}'")


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
    if event_callback:
        event_callback({
            "event": "phase1_started",
            "evaluation_group_id": resume_group_id or "",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    t_p1_start = time.time()
    phase1_results, phase1_metrics = ReconciliationEngine.reconcile_batch(p_path, l_path, b_path)
    t_p1_end = time.time()
    phase1_time_sec = max(t_p1_end - t_p1_start, 0.001)

    t_exc_start = time.time()
    all_exceptions = [r for r in phase1_results if r["status"] == "EXCEPTION"]
    reconciled_count = phase1_metrics["reconciled_records"]
    exception_count = phase1_metrics["exception_records"]
    t_exc_end = time.time()

    if event_callback:
        event_callback({
            "event": "phase1_completed",
            "evaluation_group_id": resume_group_id or "",
            "total_records": len(phase1_results),
            "reconciled_records": reconciled_count,
            "exception_records": exception_count,
            "phase1_time_sec": phase1_time_sec,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    # Step 2: Strict Total-Case Safety Validation & Deterministic Partitioning
    if cases is None or cases <= 0:
        cases = len(all_exceptions) // max(runs, 1)
        if cases == 0 and len(all_exceptions) > 0:
            cases = len(all_exceptions)

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

    t_eval_start = time.time()
    time_to_first_batch_sec: Optional[float] = None
    all_batch_latencies: List[float] = []

    if event_callback:
        event_callback({
            "event": "run_started",
            "evaluation_group_id": evaluation_group_id,
            "provider": selected_provider,
            "model": client_model,
            "mode": mode,
            "total_runs": runs,
            "cases_per_run": cases,
            "total_cases": total_requested_cases,
            "batch_size": batch_size if mode in ("batch", "compare") else 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    from src.agent.trace import AgentTracer, parse_bool_env
    trace_enabled = trace if trace is not None else parse_bool_env("SHOW_AGENT_TRACE", False)
    tracer = AgentTracer(enabled=trace_enabled)

    if tracer.enabled:
        tracer.header("AI FINANCE CONTROLLER — MULTI-AGENT TRACE" if mode == "multi-agent" else "AI FINANCE CONTROLLER — LIVE TRACE")

    # Helper to execute a set of cases under a given mode
    def execute_eval_mode(eval_mode: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any], int, int, int, Optional[float]]:
        nonlocal time_to_first_batch_sec, all_batch_latencies
        llm_client = LLMClient(provider=selected_provider, api_key=api_key, model=client_model)
        toolkit = FinancialToolkit(payments, ledger, bank, adjustments)
        agent = AgentController(toolkit=toolkit, llm_client=llm_client, tracer=tracer)
        
        from src.agent.multi_agent.batch_multi_agent_controller import BatchMultiAgentController
        batch_agent = BatchMultiAgentController(
            toolkit=toolkit,
            provider=selected_provider,
            api_key=api_key,
            investigator_model=client_model,
            verifier_model=client_model,
            tracer=tracer,
        )
        
        from src.agent.multi_agent.orchestrator import MultiAgentOrchestrator
        multi_agent = MultiAgentOrchestrator(toolkit=toolkit, provider=selected_provider, api_key=api_key, tracer=tracer)


        completed_run_numbers = set()
        existing_results = []
        partial_decisions_map = {}
        file_suffix = f"_{eval_mode}" if mode == "compare" else ""
        resume_file = os.path.join(eval_dir, f"{evaluation_group_id}{file_suffix}.json")
        if resume_group_id and os.path.exists(resume_file):
            try:
                with open(resume_file, "r", encoding="utf-8") as f:
                    saved_data = json.load(f)
                    existing_results = saved_data.get("results", [])
                    completed_run_numbers = {r["run_number"] for r in existing_results}
                    print(f"[Resume] Found {len(completed_run_numbers)} previously completed runs in group '{evaluation_group_id}{file_suffix}'.\n")
                    if saved_data.get("status") == "RUNNING" and "partial_results" in saved_data:
                        partial_run_num = saved_data.get("current_run_number")
                        if partial_run_num:
                            raw_decisions = saved_data.get("partial_results", [])
                            parsed_decs = []
                            for d_dict in raw_decisions:
                                try:
                                    parsed_decs.append(AgentDecision.model_validate(d_dict))
                                except Exception:
                                    pass
                            partial_decisions_map[partial_run_num] = parsed_decs
                            print(f"[Resume] Found {len(parsed_decs)} partial decisions for Run {partial_run_num}.\n")
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
                from src.agent.batch_partitioner import partition_exceptions_balanced
                chunks = partition_exceptions_balanced(run_cases, batch_size=batch_size)
                total_batches_in_run = len(chunks)
                concurrency_limit = src.config.get_max_parallel_batches()
                if parallel_batches is not None:
                    actual_parallel_batches = parallel_batches
                else:
                    actual_parallel_batches = min(total_batches_in_run, concurrency_limit)

                # Determine completed batches from resume partial results
                completed_batch_numbers = set()
                resumed_decisions = partial_decisions_map.get(run_num, [])
                resumed_decisions_by_tid = {d.transaction_id: d for d in resumed_decisions}
                for b_idx, chunk in enumerate(chunks, 1):
                    chunk_tids = [c.get("transaction_id", "UNKNOWN") for c in chunk]
                    if all(tid in resumed_decisions_by_tid for tid in chunk_tids):
                        completed_batch_numbers.add(b_idx)
                        # Add those decisions to agent_decisions & investigation_logs only for sequential mode
                        if actual_parallel_batches == 1:
                            for tid in chunk_tids:
                                d = resumed_decisions_by_tid[tid]
                                agent_decisions.append(d)
                                exc_obj = next((c for c in chunk if c.get("transaction_id") == tid), {})
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
                                else:
                                    cases_completed += 1

                if actual_parallel_batches == 1:
                    # Sequential mode!
                    for b_idx, chunk in enumerate(chunks, 1):
                        if b_idx in completed_batch_numbers:
                            print(f"  [Batch {b_idx}] Skipping (Already completed in resume)")
                            total_batches_processed += 1
                            continue
                        
                        chunk_tids = [c.get("transaction_id") for c in chunk]
                        total_batches_processed += 1
                        t_batch_start = time.time()

                        print(f"  [Batch {b_idx}] Investigating {len(chunk)} cases ({', '.join(chunk_tids)})...")

                        if event_callback:
                            event_callback({
                                "event": "batch_started",
                                "evaluation_group_id": evaluation_group_id,
                                "run_id": run_id,
                                "run_number": run_num,
                                "total_runs": runs,
                                "batch_number": b_idx,
                                "total_batches": total_batches_in_run,
                                "cases_in_batch": len(chunk),
                                "transaction_ids": chunk_tids,
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            })

                        chunk_decisions, batch_log = batch_agent.investigate_batch(chunk)
                        b_duration = max(time.time() - t_batch_start, 0.001)
                        all_batch_latencies.append(b_duration)

                        if time_to_first_batch_sec is None:
                            time_to_first_batch_sec = round(time.time() - t_eval_start, 4)

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

                            if event_callback:
                                event_callback({
                                    "event": "case_completed",
                                    "evaluation_group_id": evaluation_group_id,
                                    "run_id": run_id,
                                    "transaction_id": d.transaction_id,
                                    "decision": d.decision,
                                    "resolution_type": d.resolution_type or "NONE",
                                    "confidence": d.confidence,
                                    "reason": d.reason,
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                })

                        # Intermediate batch metrics
                        batch_eval_res = evaluate_agent_decisions(
                            agent_decisions=agent_decisions,
                            ground_truth=ground_truth,
                            is_subset=True,
                            total_selected=len(agent_decisions),
                        )

                        if event_callback:
                            now_iso = datetime.now(timezone.utc).isoformat()
                            event_callback({
                                "event": "batch_completed",
                                "evaluation_group_id": evaluation_group_id,
                                "run_id": run_id,
                                "run_number": run_num,
                                "total_runs": runs,
                                "batch_number": b_idx,
                                "total_batches": total_batches_in_run,
                                "cases_completed": len(agent_decisions),
                                "total_cases": cases_selected,
                                "batch_time_sec": round(b_duration, 4),
                                "results": [d.model_dump(mode="json") for d in chunk_decisions],
                                "timestamp": now_iso,
                            })
                            event_callback({
                                "event": "metrics_updated",
                                "evaluation_group_id": evaluation_group_id,
                                "run_id": run_id,
                                "cases_completed": len(agent_decisions),
                                "total_cases": cases_selected,
                                "auto_resolved": batch_eval_res.auto_resolved_total,
                                "human_review": batch_eval_res.human_review_total,
                                "accuracy": batch_eval_res.phase2_decision_accuracy,
                                "precision": batch_eval_res.auto_resolution_precision,
                                "recall": batch_eval_res.auto_resolution_recall,
                                "timestamp": now_iso,
                            })

                        # Immediate partial persistence to disk
                        partial_report = {
                            "evaluation_group_id": evaluation_group_id,
                            "status": "RUNNING",
                            "mode": eval_mode,
                            "provider": selected_provider,
                            "model": getattr(llm_client, "model", client_model),
                            "dataset_size": len(phase1_results),
                            "phase1_exception_count": exception_count,
                            "runs": runs,
                            "cases_per_run": cases,
                            "batch_size": batch_size,
                            "current_run_number": run_num,
                            "current_batch_number": b_idx,
                            "cases_completed_so_far": len(agent_decisions),
                            "partial_results": [d.model_dump(mode="json") for d in agent_decisions],
                        }
                        try:
                            with open(resume_file, "w", encoding="utf-8") as f:
                                json.dump(partial_report, f, indent=2)
                        except Exception:
                            pass
                else:
                    # Parallel batches mode!
                    import asyncio
                    from src.agent.parallel_batch_engine import run_parallel_batches

                    # Print Plan
                    print("\n========================================")
                    print("BALANCED PARALLEL BATCH PLAN")
                    print("========================================\n")
                    print(f"Cases selected:          {len(run_cases)}")
                    print(f"Batch size:               {batch_size}")
                    print(f"Total batches:            {total_batches_in_run}")
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

                    # We run it
                    parallel_res = asyncio.run(
                        run_parallel_batches(
                            batches=chunks,
                            batch_agent=batch_agent,
                            max_parallel_batches=actual_parallel_batches,
                            ground_truth=ground_truth,
                            evaluation_group_id=evaluation_group_id,
                            run_id=run_id,
                            run_num=run_num,
                            total_runs=runs,
                            cases_per_run=cases_selected,
                            batch_size=batch_size,
                            selected_provider=selected_provider,
                            client_model=client_model,
                            phase1_results=phase1_results,
                            exception_count=exception_count,
                            resume_file=resume_file,
                            event_callback=event_callback,
                            tracer=tracer,
                            completed_batch_numbers=completed_batch_numbers,
                            existing_decisions=agent_decisions,
                        )
                    )

                    # Accumulate latencies
                    all_batch_latencies.extend(parallel_res.batch_latencies)

                    # Merge results
                    agent_decisions.extend(parallel_res.decisions)
                    investigation_logs.extend(parallel_res.investigation_logs)

                    total_batches_processed += len(chunks) - len(completed_batch_numbers)
                    total_batch_llm_interactions += parallel_res.total_batch_llm_interactions
                    total_individual_fallbacks += parallel_res.total_individual_fallbacks

                    if time_to_first_batch_sec is None:
                        time_to_first_batch_sec = parallel_res.time_to_first_batch_sec

                    # Update case statuses/metrics
                    for d in parallel_res.decisions:
                        if d.decision == "NOT_EVALUATED":
                            cases_not_evaluated += 1
                        else:
                            cases_completed += 1

            else:
                # Individual or Multi-Agent mode
                for idx, exc in enumerate(run_cases, 1):
                    txn_id = exc.get("transaction_id", "UNKNOWN")
                    reason = exc.get("reason", "UNKNOWN")
                    t_case_start = time.time()
                    mode_label = "Multi-Agent" if eval_mode == "multi-agent" else "Individual"
                    print(f"  [{idx}/{cases_selected}] Investigating {txn_id} ({reason}) [{mode_label}]...")

                    if eval_mode == "multi-agent":
                        decision, log = multi_agent.investigate_exception(exc)
                    else:
                        decision, log = agent.investigate_exception(exc)

                    c_duration = max(time.time() - t_case_start, 0.001)

                    if time_to_first_batch_sec is None:
                        time_to_first_batch_sec = round(time.time() - t_eval_start, 4)

                    agent_decisions.append(decision)
                    investigation_logs.append(log.model_dump())

                    if decision.decision == "NOT_EVALUATED":
                        cases_not_evaluated += 1
                        print(f"    -> Decision: NOT_EVALUATED | Reason: {decision.reason}")
                    else:
                        cases_completed += 1
                        if eval_mode == "multi-agent":
                            print(f"    -> Decision: {decision.decision} ({decision.resolution_type}) | Inv calls: {log.investigator_calls}, Ver calls: {log.verifier_calls}")
                        else:
                            print(f"    -> Decision: {decision.decision} ({decision.resolution_type}) | Tools used: {log.tool_call_count}")

                    if event_callback:
                        event_callback({
                            "event": "case_completed",
                            "evaluation_group_id": evaluation_group_id,
                            "run_id": run_id,
                            "transaction_id": decision.transaction_id,
                            "decision": decision.decision,
                            "resolution_type": decision.resolution_type or "NONE",
                            "confidence": decision.confidence,
                            "reason": decision.reason,
                            "case_time_sec": round(c_duration, 4),
                            "timestamp": time.time(),
                        })

                        ind_eval_res = evaluate_agent_decisions(
                            agent_decisions=agent_decisions,
                            ground_truth=ground_truth,
                            is_subset=True,
                            total_selected=len(agent_decisions),
                        )
                        event_callback({
                            "event": "metrics_updated",
                            "evaluation_group_id": evaluation_group_id,
                            "run_id": run_id,
                            "cases_completed": len(agent_decisions),
                            "total_cases": cases_selected,
                            "auto_resolved": ind_eval_res.auto_resolved_total,
                            "human_review": ind_eval_res.human_review_total,
                            "accuracy": ind_eval_res.phase2_decision_accuracy,
                            "precision": ind_eval_res.auto_resolution_precision,
                            "recall": ind_eval_res.auto_resolution_recall,
                            "timestamp": time.time(),
                        })

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
                        "investigator_calls": 0,
                        "verifier_calls": 0,
                        "model_interactions": 0,
                    }
                    investigation_logs.append(unselected_log)

            if eval_mode == "multi-agent":
                run_prompt_tokens = (getattr(multi_agent.investigator_llm, "cumulative_prompt_tokens", 0) or 0) + (getattr(multi_agent.verifier_llm, "cumulative_prompt_tokens", 0) or 0)
                run_completion_tokens = (getattr(multi_agent.investigator_llm, "cumulative_completion_tokens", 0) or 0) + (getattr(multi_agent.verifier_llm, "cumulative_completion_tokens", 0) or 0)
                run_total_tokens = (getattr(multi_agent.investigator_llm, "cumulative_total_tokens", 0) or 0) + (getattr(multi_agent.verifier_llm, "cumulative_total_tokens", 0) or 0)
                total_inv_calls = sum(log.get("investigator_calls", 0) for log in investigation_logs)
                total_ver_calls = sum(log.get("verifier_calls", 0) for log in investigation_logs)
                total_interactions = sum(log.get("model_interactions", 0) for log in investigation_logs)
            else:
                run_prompt_tokens = getattr(llm_client, "cumulative_prompt_tokens", 0)
                run_completion_tokens = getattr(llm_client, "cumulative_completion_tokens", 0)
                run_total_tokens = getattr(llm_client, "cumulative_total_tokens", 0)
                total_inv_calls = 0
                total_ver_calls = 0
                total_interactions = cases_completed

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
                "investigator_calls": total_inv_calls,
                "verifier_calls": total_ver_calls,
                "total_model_interactions": total_interactions,
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
        eval_sums, agg, batches_done, batch_interactions, batch_fallbacks = execute_eval_mode(mode)
        total_eval_duration = max(time.time() - t_eval_start, 0.001)
        performance_metrics = {
            "time_to_first_batch_sec": time_to_first_batch_sec or total_eval_duration,
            "total_processing_time_sec": round(total_eval_duration, 4),
            "average_batch_latency_sec": round(sum(all_batch_latencies) / len(all_batch_latencies), 4) if all_batch_latencies else 0.0,
            "min_batch_latency_sec": round(min(all_batch_latencies), 4) if all_batch_latencies else 0.0,
            "max_batch_latency_sec": round(max(all_batch_latencies), 4) if all_batch_latencies else 0.0,
            "batches_processed": batches_done,
        }
        effective_parallel_batches = parallel_batches if parallel_batches is not None else min((agg['total_selected'] + batch_size - 1) // batch_size, src.config.get_max_parallel_batches())
        concurrency_limit = src.config.get_max_parallel_batches()

        if effective_parallel_batches > 1 and all_batch_latencies:
            performance_metrics["sequential_estimated_time_sec"] = round(sum(all_batch_latencies), 4)

        total_tokens_val = agg["total_tokens"]
        tok_str = f"{total_tokens_val:,}" if total_tokens_val > 0 else "unknown"

        if mode == "batch":
            if effective_parallel_batches > 1:
                print("\n========================================")
                print("PARALLEL LLM EVALUATION")
                print("========================================\n")
                print(f"Cases selected:           {agg['total_selected']}")
                print(f"Batch size:               {batch_size}")
                print(f"Total batches:            {batches_done}")
                print(f"Concurrency limit:        {concurrency_limit}")
                print(f"Actual concurrent batches: {effective_parallel_batches}\n")
                print(f"Batches completed:         {batches_done}")
                print(f"Cases completed:           {agg['total_completed']}")
                print(f"Not evaluated:             {agg['total_not_evaluated']}\n")
                print(f"Time to first batch:       {performance_metrics['time_to_first_batch_sec']:.4f} sec")
                print(f"Total processing time:     {performance_metrics['total_processing_time_sec']:.4f} sec")
                print(f"Average batch latency:     {performance_metrics['average_batch_latency_sec']:.4f} sec")
                print(f"Min batch latency:         {performance_metrics['min_batch_latency_sec']:.4f} sec")
                print(f"Max batch latency:         {performance_metrics['max_batch_latency_sec']:.4f} sec\n")
                print(f"Total tokens:              {tok_str}")
                print(f"Average tokens/case:       {agg['average_tokens_per_case']:,}\n")
                print(f"Decision accuracy:         {agg['decision_accuracy']:.2f}%")
                print(f"Auto-resolution precision: {agg['auto_resolution_precision']:.2f}%")
                print(f"Auto-resolution recall:    {agg['auto_resolution_recall']:.2f}%")
                print("========================================\n")
            else:
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
        elif mode == "multi-agent":
            total_inv_all = sum(r.get("investigator_calls", 0) for r in eval_sums)
            total_ver_all = sum(r.get("verifier_calls", 0) for r in eval_sums)
            total_ints_all = sum(r.get("total_model_interactions", 0) for r in eval_sums)
            avg_ints_case = (total_ints_all / agg['total_completed']) if agg['total_completed'] > 0 else 0.0

            print("\n========================================")
            print("CONTROLLED MULTI-AGENT EVALUATION")
            print("========================================\n")
            print("Mode: MULTI-AGENT\n")
            print(f"Provider: {provider_display_name}")
            print(f"Model: {client_model}\n")
            print(f"Cases evaluated:            {agg['total_completed']}")
            print(f"Decision accuracy:           {agg['decision_accuracy']:.2f}%")
            print(f"Auto-resolution precision:   {agg['auto_resolution_precision']:.2f}%")
            print(f"Auto-resolution recall:      {agg['auto_resolution_recall']:.2f}%")
            print(f"Human-review rate:           {agg['human_review_rate']:.2f}%\n")
            print("----------------------------------------")
            print("MULTI-AGENT COORDINATION & COST METRICS")
            print("----------------------------------------\n")
            print(f"Investigator calls:          {total_inv_all}")
            print(f"Verifier calls:              {total_ver_all}")
            print(f"Total model interactions:    {total_ints_all}")
            print(f"Average interactions/case:   {avg_ints_case:.2f}\n")
            print(f"Total processing time:       {agg['total_processing_time_sec']:.4f} sec")
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

        # Save final completed report
        final_report_data = {
            "evaluation_group_id": evaluation_group_id,
            "status": "COMPLETED",
            "mode": mode,
            "provider": selected_provider,
            "model": client_model,
            "dataset_size": len(phase1_results),
            "phase1_exception_count": exception_count,
            "runs": runs,
            "cases_per_run": cases,
            "batch_size": batch_size if mode == "batch" else 1,
            "results": eval_sums,
            "aggregate_metrics": agg,
            "performance": performance_metrics,
        }
        final_report_file = os.path.join(eval_dir, f"{evaluation_group_id}.json")
        with open(final_report_file, "w", encoding="utf-8") as f:
            json.dump(final_report_data, f, indent=2)

        if event_callback:
            event_callback({
                "event": "run_completed",
                "evaluation_group_id": evaluation_group_id,
                "status": "COMPLETED",
                "aggregate_metrics": agg,
                "performance": performance_metrics,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

        return {
            "evaluation_group_id": evaluation_group_id,
            "provider": selected_provider,
            "model": client_model,
            "mode": mode,
            "status": "COMPLETED",
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
            "performance": performance_metrics,
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
        "--parallel-batches",
        type=int,
        default=None,
        help="Optional max parallel batches override (1-5, default: auto = min(total_batches, 5))",
    )
    parser.add_argument(
        "--parallel-benchmark",
        action="store_true",
        help="Run benchmark comparing sequential (1) and parallel (5) batch runs",
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="batch",
        choices=["batch", "individual", "compare", "multi-agent"],
        help="Investigation mode: batch, individual, compare, or multi-agent (default: batch)",
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
    parser.add_argument(
        "--trace",
        dest="trace",
        action="store_true",
        default=None,
        help="Enable live real-time agent trace in terminal (overrides SHOW_AGENT_TRACE)",
    )
    parser.add_argument(
        "--no-trace",
        dest="trace",
        action="store_false",
        help="Disable live agent trace in terminal",
    )
    args = parser.parse_args()

    if args.parallel_benchmark:
        print("\n==================================================")
        print("RUNNING BENCHMARK: SEQUENTIAL VS PARALLEL BATCHES")
        print("==================================================\n")
        print("-> Running Sequential Evaluation (parallel_batches=1)...")
        seq_res = run_evaluation(
            provider=args.provider,
            cases=args.cases,
            runs=args.runs,
            batch_size=args.batch_size,
            parallel_batches=1,
            mode=args.mode,
            model=args.model,
            resume_group_id=args.resume,
            trace=False,
        )
        print("-> Running Parallel Evaluation (parallel_batches=5)...")
        p_res = run_evaluation(
            provider=args.provider,
            cases=args.cases,
            runs=args.runs,
            batch_size=args.batch_size,
            parallel_batches=5,
            mode=args.mode,
            model=args.model,
            resume_group_id=args.resume,
            trace=False,
        )
        
        # Compare!
        print("\n========================================")
        print("PARALLEL BENCHMARK COMPARISON")
        print("========================================")
        print(f"Cases: {args.cases}\n")
        print(f"{'Metric':<25} {'Sequential':<16} {'Parallel':<16} {'Reduction'}")
        print("-" * 72)
        seq_time = seq_res["performance"]["total_processing_time_sec"]
        p_time = p_res["performance"]["total_processing_time_sec"]
        time_red = ((seq_time - p_time) / seq_time * 100) if seq_time > 0 else 0.0
        
        seq_toks = seq_res["total_tokens"]
        p_toks = p_res["total_tokens"]
        tok_red = ((seq_toks - p_toks) / seq_toks * 100) if seq_toks > 0 else 0.0
        
        print(f"{'Total Latency':<25} {seq_time:>10.4f}s      {p_time:>10.4f}s       {time_red:>7.1f}%")
        print(f"{'Total Tokens':<25} {seq_toks:>10,d}        {p_toks:>10,d}         {tok_red:>7.1f}%")
        print(f"{'Decision Accuracy':<25} {seq_res['aggregate_metrics']['decision_accuracy']:>9.2f}%      {p_res['aggregate_metrics']['decision_accuracy']:>9.2f}%")
        print("========================================\n")
    else:
        run_evaluation(
            provider=args.provider,
            cases=args.cases,
            runs=args.runs,
            batch_size=args.batch_size,
            parallel_batches=args.parallel_batches,
            mode=args.mode,
            model=args.model,
            resume_group_id=args.resume,
            trace=args.trace,
        )


if __name__ == "__main__":
    main()

