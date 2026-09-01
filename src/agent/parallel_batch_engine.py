"""
Bounded Parallel Batch Execution Engine for AI Finance Controller.

Executes multiple exception batches concurrently using asyncio and a Semaphore.
Preserves batch isolation, audit trails, progressive SSE updates, partial persistence,
and resilient exception handling.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.agent.batch_controller import BatchAgentController
from src.agent.evaluator import evaluate_agent_decisions
from src.agent.schemas import AgentDecision, BatchInvestigationLog, BatchStatus


@dataclass
class BatchExecutionResult:
    batch_number: int
    batch_id: str
    transaction_ids: List[str]
    decisions: List[AgentDecision]
    log: Optional[BatchInvestigationLog]
    status: BatchStatus
    duration_sec: float
    error: Optional[str] = None


@dataclass
class ParallelEngineResult:
    decisions: List[AgentDecision] = field(default_factory=list)
    investigation_logs: List[Dict[str, Any]] = field(default_factory=list)
    batch_statuses: List[BatchStatus] = field(default_factory=list)
    total_batch_llm_interactions: int = 0
    total_individual_fallbacks: int = 0
    time_to_first_batch_sec: float = 0.0
    parallel_wall_clock_time_sec: float = 0.0
    sequential_estimated_time_sec: float = 0.0
    batch_latencies: List[float] = field(default_factory=list)
    average_batch_latency_sec: float = 0.0
    min_batch_latency_sec: float = 0.0
    max_batch_latency_sec: float = 0.0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0


async def run_parallel_batches(
    batches: List[List[Dict[str, Any]]],
    batch_agent: BatchAgentController,
    max_parallel_batches: int,
    ground_truth: List[Dict[str, Any]],
    evaluation_group_id: str,
    run_id: str,
    run_num: int,
    total_runs: int,
    cases_per_run: int,
    batch_size: int,
    selected_provider: str,
    client_model: str,
    phase1_results: List[Dict[str, Any]],
    exception_count: int,
    resume_file: str,
    event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    tracer: Optional[Any] = None,
    completed_batch_numbers: Optional[set] = None,
    existing_decisions: Optional[List[AgentDecision]] = None,
) -> ParallelEngineResult:
    """
    Executes a list of exception batches using bounded concurrency (asyncio.Semaphore).

    Guarantees:
    - Parallelism is bounded at batch level (Semaphore <= max_parallel_batches).
    - Batch result isolation: results per task, merged safely after completion.
    - Progressive SSE events emitted immediately upon each batch completion.
    - Partial persistence after each batch completes.
    - Failed batches produce NOT_EVALUATED decisions; overall execution continues.
    """
    completed_batch_numbers = completed_batch_numbers or set()
    semaphore = asyncio.Semaphore(max_parallel_batches)
    file_lock = threading.Lock()
    first_batch_lock = threading.Lock()

    t_eval_start = time.time()
    time_to_first_batch_holder: List[float] = []

    # Store decisions & logs per batch index (1-based) for strict order recovery
    results_by_batch: Dict[int, BatchExecutionResult] = {}
    aggregated_decisions: List[AgentDecision] = list(existing_decisions or [])

    total_batches = len(batches)

    def safe_print_trace(msg: str):
        if tracer and getattr(tracer, "enabled", False):
            if hasattr(tracer, "_print"):
                tracer._print(msg)
            else:
                print(msg, flush=True)
        else:
            print(msg, flush=True)

    async def execute_single_batch(b_idx: int, chunk: List[Dict[str, Any]]) -> BatchExecutionResult:
        async with semaphore:
            chunk_tids = [c.get("transaction_id", "UNKNOWN") for c in chunk]
            b_id = f"batch_{b_idx}_{run_num}"

            safe_print_trace(f"[Batch {b_idx}]\n-> STARTED ({len(chunk)} cases: {', '.join(chunk_tids)})")

            type_counts: Dict[str, int] = {}
            for c in chunk:
                etype = c.get("reason") or c.get("exception_type") or c.get("initial_exception") or "UNKNOWN"
                type_counts[etype] = type_counts.get(etype, 0) + 1

            if event_callback:
                event_callback({
                    "event": "batch_started",
                    "evaluation_group_id": evaluation_group_id,
                    "run_id": run_id,
                    "run_number": run_num,
                    "total_runs": total_runs,
                    "batch_number": b_idx,
                    "total_batches": total_batches,
                    "cases_in_batch": len(chunk),
                    "transaction_ids": chunk_tids,
                    "type_counts": type_counts,
                    "timestamp": time.time(),
                })

            start_utc = datetime.now(timezone.utc)
            t_start = time.time()

            decisions: List[AgentDecision] = []
            log: Optional[BatchInvestigationLog] = None
            error_msg: Optional[str] = None
            status_str = "COMPLETED"

            loop = asyncio.get_running_loop()

            try:
                # Run synchronous batch investigation in executor to avoid blocking event loop
                decisions, log = await loop.run_in_executor(
                    None, batch_agent.investigate_batch, chunk
                )
            except Exception as exc:
                error_msg = str(exc)
                status_str = "FAILED"
                safe_print_trace(f"[Batch {b_idx}]\n✗ FAILED: {error_msg}")

                # Produce NOT_EVALUATED decisions for all cases in failed batch
                for exc_obj in chunk:
                    tid = exc_obj.get("transaction_id", "UNKNOWN")
                    decisions.append(
                        AgentDecision(
                            transaction_id=tid,
                            decision="NOT_EVALUATED",
                            exception_type=exc_obj.get("reason", "UNKNOWN"),
                            resolution_type="NONE",
                            reason=f"Batch evaluation failed due to provider/system error: {error_msg}",
                            evidence=["Batch execution failed."],
                            confidence=0.0,
                            recommended_action="Retry evaluation or manual review.",
                        )
                    )

            t_end = time.time()
            end_utc = datetime.now(timezone.utc)
            duration = max(t_end - t_start, 0.001)

            with first_batch_lock:
                if not time_to_first_batch_holder:
                    time_to_first_batch_holder.append(round(time.time() - t_eval_start, 4))

            if status_str == "COMPLETED":
                safe_print_trace(f"[Batch {b_idx}]\n✓ COMPLETED ({len(decisions)} cases in {duration:.2f}s)")

            # Extract token usage if log available
            p_toks = log.prompt_tokens if log else None
            c_toks = log.completion_tokens if log else None
            t_toks = log.total_tokens if log else None

            status_obj = BatchStatus(
                batch_id=log.batch_id if log else b_id,
                batch_number=b_idx,
                transaction_ids=chunk_tids,
                status=status_str,
                batch_started_at=start_utc,
                batch_completed_at=end_utc,
                batch_latency_sec=round(duration, 4),
                batch_error=error_msg,
                provider=selected_provider,
                model=client_model,
                prompt_tokens=p_toks,
                completion_tokens=c_toks,
                total_tokens=t_toks,
            )

            res = BatchExecutionResult(
                batch_number=b_idx,
                batch_id=log.batch_id if log else b_id,
                transaction_ids=chunk_tids,
                decisions=decisions,
                log=log,
                status=status_obj,
                duration_sec=duration,
                error=error_msg,
            )

            # Emit case-level & batch-level SSE updates immediately
            if event_callback:
                now_iso = datetime.now(timezone.utc).isoformat()
                for d in decisions:
                    event_callback({
                        "event": "case_completed",
                        "evaluation_group_id": evaluation_group_id,
                        "run_id": run_id,
                        "transaction_id": d.transaction_id,
                        "decision": d.decision,
                        "resolution_type": d.resolution_type or "NONE",
                        "confidence": d.confidence,
                        "reason": d.reason,
                        "timestamp": now_iso,
                    })

                event_callback({
                    "event": "batch_completed",
                    "evaluation_group_id": evaluation_group_id,
                    "run_id": run_id,
                    "run_number": run_num,
                    "total_runs": total_runs,
                    "batch_number": b_idx,
                    "total_batches": total_batches,
                    "cases_completed": len(decisions),
                    "total_cases": cases_per_run,
                    "batch_time_sec": round(duration, 4),
                    "results": [d.model_dump(mode="json") for d in decisions],
                    "timestamp": now_iso,
                })

            # Thread-safe write for partial persistence after each batch completes
            with file_lock:
                results_by_batch[b_idx] = res
                current_all_decisions = list(aggregated_decisions)
                for b_k in sorted(results_by_batch.keys()):
                    current_all_decisions.extend(results_by_batch[b_k].decisions)

                if event_callback:
                    batch_eval_res = evaluate_agent_decisions(
                        agent_decisions=current_all_decisions,
                        ground_truth=ground_truth,
                        is_subset=True,
                        total_selected=len(current_all_decisions),
                    )
                    event_callback({
                        "event": "metrics_updated",
                        "evaluation_group_id": evaluation_group_id,
                        "run_id": run_id,
                        "cases_completed": len(current_all_decisions),
                        "total_cases": cases_per_run,
                        "auto_resolved": batch_eval_res.auto_resolved_total,
                        "human_review": batch_eval_res.human_review_total,
                        "accuracy": batch_eval_res.phase2_decision_accuracy,
                        "precision": batch_eval_res.auto_resolution_precision,
                        "recall": batch_eval_res.auto_resolution_recall,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })

                partial_report = {
                    "evaluation_group_id": evaluation_group_id,
                    "status": "RUNNING",
                    "mode": "batch",
                    "provider": selected_provider,
                    "model": client_model,
                    "dataset_size": len(phase1_results),
                    "phase1_exception_count": exception_count,
                    "runs": total_runs,
                    "cases_per_run": cases_per_run,
                    "batch_size": batch_size,
                    "current_run_number": run_num,
                    "completed_batches": list(results_by_batch.keys()),
                    "cases_completed_so_far": len(current_all_decisions),
                    "partial_results": [d.model_dump(mode="json") for d in current_all_decisions],
                }
                try:
                    with open(resume_file, "w", encoding="utf-8") as f:
                        json.dump(partial_report, f, indent=2)
                except Exception:
                    pass

            return res

    # Create tasks for non-completed batches
    tasks = []
    for b_idx, chunk in enumerate(batches, 1):
        if b_idx in completed_batch_numbers:
            safe_print_trace(f"[Batch {b_idx}] → SKIPPED (Already completed in resume)")
            continue
        tasks.append(execute_single_batch(b_idx, chunk))

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

    t_eval_end = time.time()
    wall_clock_time = max(t_eval_end - t_eval_start, 0.001)

    # Collect and combine results in deterministic batch order
    final_decisions: List[AgentDecision] = []
    final_investigation_logs: List[Dict[str, Any]] = []
    batch_statuses: List[BatchStatus] = []
    total_interactions = 0
    total_fallbacks = 0
    latencies: List[float] = []

    total_p_tokens = 0
    total_c_tokens = 0
    total_t_tokens = 0

    existing_map = {d.transaction_id: d for d in (existing_decisions or [])}

    for b_idx in range(1, total_batches + 1):
        if b_idx in completed_batch_numbers:
            # Skip execution and merge from existing_decisions
            chunk = batches[b_idx - 1]
            for exc_obj in chunk:
                tid = exc_obj.get("transaction_id", "UNKNOWN")
                if tid in existing_map:
                    d = existing_map[tid]
                    final_decisions.append(d)
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
                        "batch_id": f"batch_{b_idx}_{run_num}",
                        "batch_number": b_idx,
                    }
                    final_investigation_logs.append(t_log)
        else:
            if b_idx in results_by_batch:
                b_res = results_by_batch[b_idx]
                batch_statuses.append(b_res.status)
                latencies.append(b_res.duration_sec)

                for d in b_res.decisions:
                    final_decisions.append(d)
                    exc_chunk = batches[b_idx - 1]
                    exc_obj = next((c for c in exc_chunk if c.get("transaction_id") == d.transaction_id), {})

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
                        "batch_id": b_res.batch_id,
                        "batch_number": b_idx,
                    }
                    final_investigation_logs.append(t_log)

                if b_res.log:
                    total_interactions += b_res.log.llm_interactions
                    total_fallbacks += b_res.log.fallback_count
                    if b_res.log.prompt_tokens:
                        total_p_tokens += b_res.log.prompt_tokens
                    if b_res.log.completion_tokens:
                        total_c_tokens += b_res.log.completion_tokens
                    if b_res.log.total_tokens:
                        total_t_tokens += b_res.log.total_tokens

    avg_latency = (sum(latencies) / len(latencies)) if latencies else 0.0
    min_latency = min(latencies) if latencies else 0.0
    max_latency = max(latencies) if latencies else 0.0
    seq_est = sum(latencies)

    time_to_first = time_to_first_batch_holder[0] if time_to_first_batch_holder else wall_clock_time

    return ParallelEngineResult(
        decisions=final_decisions,
        investigation_logs=final_investigation_logs,
        batch_statuses=batch_statuses,
        total_batch_llm_interactions=total_interactions,
        total_individual_fallbacks=total_fallbacks,
        time_to_first_batch_sec=time_to_first,
        parallel_wall_clock_time_sec=round(wall_clock_time, 4),
        sequential_estimated_time_sec=round(seq_est, 4),
        batch_latencies=latencies,
        average_batch_latency_sec=round(avg_latency, 4),
        min_batch_latency_sec=round(min_latency, 4),
        max_batch_latency_sec=round(max_latency, 4),
        total_prompt_tokens=total_p_tokens,
        total_completion_tokens=total_c_tokens,
        total_tokens=total_t_tokens,
    )
