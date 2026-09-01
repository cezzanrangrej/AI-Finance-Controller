import asyncio
import json
import os
import queue
import threading
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from src.api.schemas import EvaluationGroupSummaryResponse, EvaluationRunRequest
from scripts.run_llm_eval import run_evaluation

_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.abspath(os.path.join(_current_dir, "..", "..", ".."))

router = APIRouter(prefix="/api/evaluations", tags=["Evaluations"])

# Active event queues for live streaming evaluations
_ACTIVE_STREAMS: Dict[str, queue.Queue] = {}


@router.post("", response_model=EvaluationGroupSummaryResponse, status_code=status.HTTP_201_CREATED)
def trigger_evaluation(request: EvaluationRunRequest) -> Dict[str, Any]:
    """
    Triggers a multi-run deterministic evaluation synchronously and returns aggregate metrics.
    """
    try:
        result = run_evaluation(
            provider=request.provider,
            cases=request.cases_per_run,
            runs=request.runs or 1,
            batch_size=request.batch_size if request.batch_size is not None else 5,
            parallel_batches=request.parallel_batches,
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


@router.post("/start", status_code=status.HTTP_202_ACCEPTED)
def start_streaming_evaluation(request: EvaluationRunRequest) -> Dict[str, Any]:
    """
    Starts an asynchronous multi-run evaluation and creates an SSE stream channel.
    """
    group_id = f"eval_group_{uuid.uuid4().hex[:10]}"
    event_q = queue.Queue()
    _ACTIVE_STREAMS[group_id] = event_q

    def event_callback(event_data: Dict[str, Any]):
        event_q.put(event_data)

    def worker():
        try:
            res = run_evaluation(
                provider=request.provider,
                cases=request.cases_per_run,
                runs=request.runs or 1,
                batch_size=request.batch_size if request.batch_size is not None else 5,
                parallel_batches=request.parallel_batches,
                mode="batch",
                model=request.model,
                resume_group_id=group_id,
                event_callback=event_callback,
            )
            if res.get("status") == "SKIPPED":
                event_q.put({"event": "run_error", "error": res.get("reason", "Evaluation skipped.")})
        except Exception as e:
            event_q.put({"event": "run_error", "error": str(e)})
        finally:
            event_q.put({"event": "_stream_closed"})

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    return {
        "evaluation_group_id": group_id,
        "status": "STARTED",
        "provider": request.provider or "openrouter",
        "stream_url": f"/api/evaluations/{group_id}/stream",
    }


@router.get("/{group_id}/stream")
def stream_evaluation_events(group_id: str):
    """
    SSE stream endpoint for real-time progressive evaluation batch updates.
    """
    event_q = _ACTIVE_STREAMS.get(group_id)

    def event_generator():
        # If no live queue exists, check if file is already on disk
        if not event_q:
            eval_file = os.path.join(_project_root, "data", "evaluations", f"{group_id}.json")
            if os.path.exists(eval_file):
                with open(eval_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                yield f"event: run_completed\ndata: {json.dumps(data)}\n\n"
            else:
                yield f"event: run_error\ndata: {json.dumps({'error': f'Evaluation group {group_id} not found'})}\n\n"
            return

        while True:
            try:
                event_data = event_q.get(timeout=30.0)
                if event_data.get("event") == "_stream_closed":
                    _ACTIVE_STREAMS.pop(group_id, None)
                    break
                event_name = event_data.get("event", "message")
                yield f"event: {event_name}\ndata: {json.dumps(event_data)}\n\n"
                if event_name in ("run_completed", "run_error"):
                    _ACTIVE_STREAMS.pop(group_id, None)
                    break
            except queue.Empty:
                # Keep-alive heartbeat comment
                yield ": heartbeat\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/{group_id}/status")
def get_evaluation_status(group_id: str) -> Dict[str, Any]:
    """
    Returns the current execution status of an evaluation group.
    """
    eval_file = os.path.join(_project_root, "data", "evaluations", f"{group_id}.json")
    if os.path.exists(eval_file):
        try:
            with open(eval_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {
                "evaluation_group_id": group_id,
                "status": data.get("status", "COMPLETED"),
                "cases_completed": data.get("aggregate_metrics", {}).get("total_completed", 0),
                "total_cases": (data.get("runs", 1) * data.get("cases_per_run", 5)),
            }
        except Exception:
            pass

    if group_id in _ACTIVE_STREAMS:
        return {"evaluation_group_id": group_id, "status": "RUNNING"}

    raise HTTPException(status_code=404, detail=f"Evaluation group '{group_id}' not found.")


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

