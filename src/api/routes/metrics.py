"""
API routes for run metrics and throughput analytics.
"""

from collections import Counter
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.api.schemas import MetricsResponse
from src.db.database import get_db
from src.db.repository import FinanceRepository

router = APIRouter(prefix="/api/runs", tags=["metrics"])


@router.get("/{run_id}/metrics", response_model=MetricsResponse)
def get_run_metrics(run_id: str, db: Session = Depends(get_db)):
    """
    Returns metrics, ground truth accuracy, precision, recall, exception breakdown,
    and phase-separated processing timing for a specific run.
    """
    run = FinanceRepository.get_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    transactions = FinanceRepository.get_transactions_by_run(db, run_id)
    exception_reasons = [t.exception_type for t in transactions if t.status == "EXCEPTION" and t.exception_type]
    breakdown = dict(Counter(exception_reasons))

    return MetricsResponse(
        run_id=run.id,
        total_records=run.total_records,
        initial_reconciled=run.initial_reconciled,
        initial_exceptions=run.initial_exceptions,
        ai_auto_resolved=run.ai_auto_resolved,
        human_review=run.human_review,
        final_resolved=run.final_resolved,
        final_unresolved=run.final_unresolved,
        initial_match_rate=run.initial_match_rate,
        agent_resolution_rate=run.agent_resolution_rate,
        final_resolution_rate=run.final_resolution_rate,
        llm_provider=getattr(run, "llm_provider", "demo") or "demo",
        llm_mode=getattr(run, "llm_mode", "DEMO") or "DEMO",
        llm_model=getattr(run, "llm_model", "demo") or "demo",
        llm_degraded=bool(getattr(run, "llm_degraded", False)),
        llm_degraded_reason=getattr(run, "llm_degraded_reason", None),
        prompt_tokens=getattr(run, "prompt_tokens", None),
        completion_tokens=getattr(run, "completion_tokens", None),
        total_tokens=getattr(run, "total_tokens", None),
        # Passed through verbatim. These were previously `x or 100.0`, which
        # turned both an unmeasured NULL *and* a genuine 0.0 into a perfect
        # score. None here means "not measured" and renders as N/A.
        phase1_accuracy=run.phase1_accuracy,
        phase2_accuracy=run.phase2_accuracy if run.phase2_accuracy is not None else run.ground_truth_accuracy,
        auto_resolution_precision=run.auto_resolution_precision,
        auto_resolution_recall=run.auto_resolution_recall,
        ground_truth_accuracy=run.ground_truth_accuracy,
        has_ground_truth=bool(getattr(run, "has_ground_truth", False)),
        phase1_detection_precision=getattr(run, "phase1_detection_precision", None),
        phase1_detection_recall=getattr(run, "phase1_detection_recall", None),
        phase1_false_positives=getattr(run, "phase1_false_positives", None),
        phase1_false_negatives=getattr(run, "phase1_false_negatives", None),
        not_evaluated=getattr(run, "not_evaluated", 0) or 0,
        degraded_cases=getattr(run, "degraded_cases", 0) or 0,
        phase1_time_sec=run.phase1_time_sec,
        phase2_time_sec=run.phase2_time_sec,
        end_to_end_time_sec=run.end_to_end_time_sec,
        total_processing_time_sec=run.total_processing_time_sec,
        records_per_second=run.records_per_second,
        phase1_records_per_second=getattr(run, "phase1_records_per_second", None),
        phase2_cases_per_second=getattr(run, "phase2_cases_per_second", None),
        average_time_per_record_sec=run.average_time_per_record_sec,
        average_case_latency_sec=getattr(run, "average_case_latency_sec", None),
        tokens_per_case=getattr(run, "tokens_per_case", None),
        exception_breakdown=breakdown,
    )
