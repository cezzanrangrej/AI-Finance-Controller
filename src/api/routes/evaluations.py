import json
import os
import queue
import re
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

# Active event queues for live streaming evaluations.
# Bounded: a client that never connects to its stream would otherwise leave its
# queue (and every event the worker produced) resident forever.
_ACTIVE_STREAMS: Dict[str, queue.Queue] = {}
_MAX_TRACKED_STREAMS = 32

#: group_id is interpolated into a filesystem path, so it is restricted to the
#: shape this module generates. Without this, "../../.env" would be readable.
_GROUP_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _as_ratio(percent: Optional[float]) -> Optional[float]:
    """
    Converts a stored percentage to a 0-1 ratio, preserving "not measured".

    None means the rate had a zero denominator. It must stay None so the UI
    renders N/A; defaulting precision/recall to 100% would report a perfect
    score for a run that measured nothing.
    """
    if percent is None:
        return None
    try:
        return float(percent) / 100.0
    except (TypeError, ValueError):
        return None


def _evaluation_report_path(group_id: str) -> str:
    """Resolves the on-disk report path for a validated group_id."""
    if not _GROUP_ID_RE.match(group_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid evaluation group id.",
        )
    return os.path.join(_project_root, "data", "evaluations", f"{group_id}.json")


#: How long an SSE generator waits for the next event before emitting a
#: keep-alive comment.
_STREAM_POLL_TIMEOUT_SEC = 30.0

#: Consecutive keep-alives tolerated before the stream gives up (20 minutes).
_STREAM_MAX_IDLE_HEARTBEATS = 40


def _register_stream(registry: Dict[str, queue.Queue], key: str) -> queue.Queue:
    """
    Registers an SSE event queue, evicting the oldest entries beyond the cap.

    Streams are normally removed when the client consumes the terminal event,
    but a client that never connects would otherwise leak its queue. dicts keep
    insertion order, so the first key is the oldest registration.
    """
    while len(registry) >= _MAX_TRACKED_STREAMS:
        registry.pop(next(iter(registry)), None)
    event_q: queue.Queue = queue.Queue()
    registry[key] = event_q
    return event_q


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
    event_q = _register_stream(_ACTIVE_STREAMS, group_id)

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
    # Validated up front so an invalid id fails with 400 before the generator
    # starts streaming, when the status code can still be set.
    eval_file = _evaluation_report_path(group_id)

    def event_generator():
        # If no live queue exists, check if file is already on disk
        if not event_q:
            if os.path.exists(eval_file):
                with open(eval_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                yield f"event: run_completed\ndata: {json.dumps(data)}\n\n"
            else:
                yield f"event: run_error\ndata: {json.dumps({'error': f'Evaluation group {group_id} not found'})}\n\n"
            return

        idle_heartbeats = 0
        while True:
            try:
                event_data = event_q.get(timeout=_STREAM_POLL_TIMEOUT_SEC)
                idle_heartbeats = 0
                if event_data.get("event") == "_stream_closed":
                    _ACTIVE_STREAMS.pop(group_id, None)
                    break
                event_name = event_data.get("event", "message")
                yield f"event: {event_name}\ndata: {json.dumps(event_data)}\n\n"
                if event_name in ("run_completed", "run_error"):
                    _ACTIVE_STREAMS.pop(group_id, None)
                    break
            except queue.Empty:
                idle_heartbeats += 1
                if idle_heartbeats > _STREAM_MAX_IDLE_HEARTBEATS:
                    # Bounded so a worker killed without unwinding its finally
                    # block cannot leave the client heartbeating forever.
                    _ACTIVE_STREAMS.pop(group_id, None)
                    yield "event: run_error\ndata: " + json.dumps({
                        "error": (
                            f"No progress from evaluation group {group_id} for "
                            f"{_STREAM_MAX_IDLE_HEARTBEATS * _STREAM_POLL_TIMEOUT_SEC / 60:.0f} minutes; "
                            "the stream was closed."
                        )
                    }) + "\n\n"
                    break
                # Keep-alive heartbeat comment
                yield ": heartbeat\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/{group_id}/status")
def get_evaluation_status(group_id: str) -> Dict[str, Any]:
    """
    Returns the current execution status of an evaluation group.
    """
    eval_file = _evaluation_report_path(group_id)
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
    eval_file = _evaluation_report_path(group_id)
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
            "aggregate_accuracy": _as_ratio(agg.get("decision_accuracy")),
            "aggregate_precision": _as_ratio(agg.get("auto_resolution_precision")),
            "aggregate_recall": _as_ratio(agg.get("auto_resolution_recall")),
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

