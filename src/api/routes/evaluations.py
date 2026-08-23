"""
API routes for multi-run evaluations and aggregate metrics.
"""

import json
import os
from typing import Any, Dict
from fastapi import APIRouter, HTTPException, status

from src.api.schemas import EvaluationGroupSummaryResponse, EvaluationRunRequest
from src.run_llm_eval import run_evaluation

_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.abspath(os.path.join(_current_dir, "..", "..", ".."))

router = APIRouter(prefix="/api/evaluations", tags=["Evaluations"])


@router.post("", response_model=EvaluationGroupSummaryResponse, status_code=status.HTTP_201_CREATED)
def trigger_evaluation(request: EvaluationRunRequest) -> Dict[str, Any]:
    """
    Triggers a multi-run deterministic evaluation and returns aggregate metrics.
    """
    try:
        result = run_evaluation(
            provider=request.provider,
            cases=request.cases_per_run or 5,
            runs=request.runs or 1,
            model=request.model,
        )
        if result.get("status") == "SKIPPED":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("reason", "Evaluation skipped due to missing configuration."),
            )
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Evaluation failed: {str(e)}",
        )


@router.get("/{group_id}", response_model=EvaluationGroupSummaryResponse)
def get_evaluation_group(group_id: str) -> Dict[str, Any]:
    """
    Retrieves stored multi-run evaluation report by evaluation_group_id.
    """
    eval_file = os.path.join(_project_root, "data", "evaluations", f"{group_id}.json")
    if not os.path.exists(eval_file):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evaluation group '{group_id}' not found.",
        )

    try:
        with open(eval_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        agg = data.get("aggregate_metrics", {})
        return {
            "evaluation_group_id": group_id,
            "provider": data.get("provider", "demo"),
            "model": data.get("model", "demo"),
            "runs": data.get("runs", len(data.get("results", []))),
            "cases_per_run": data.get("cases_per_run", 5),
            "total_selected": agg.get("total_selected", 0),
            "completed": agg.get("total_completed", 0),
            "not_evaluated": agg.get("total_not_evaluated", 0),
            "auto_resolved": agg.get("auto_resolved", 0),
            "human_review": agg.get("human_review", 0),
            "aggregate_accuracy": agg.get("decision_accuracy", 0.0) / 100.0,
            "aggregate_precision": agg.get("auto_resolution_precision", 100.0) / 100.0,
            "aggregate_recall": agg.get("auto_resolution_recall", 100.0) / 100.0,
            "human_review_rate": agg.get("human_review_rate", 0.0),
            "not_evaluated_rate": agg.get("not_evaluated_rate", 0.0),
            "total_processing_time_sec": agg.get("total_processing_time_sec", 0.0),
            "average_case_latency_sec": agg.get("average_case_latency_sec", 0.0),
            "total_tokens": agg.get("total_tokens", 0),
            "average_tokens_per_case": agg.get("average_tokens_per_case", 0),
            "per_run_summaries": data.get("results", []),
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read evaluation group report: {str(e)}",
        )
