import csv
import io
import json
import logging
import os
import queue
import threading
import time
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from decimal import Decimal
from src.agent.evaluator import evaluate_agent_decisions
from src.agent.schemas import AgentDecision
from src.agent.tools import FinancialToolkit
from src.agent.trace import AgentTracer
from src.agent.provider_resolution import ProviderResolution, resolve_providers
from src.api.schemas import DataIntegrityDiagnosticResponse, DataIntegrityRecord, RunSummaryResponse
from src.db.database import SessionLocal, get_db, init_db
from src.db.repository import FinanceRepository
from src.generator import SyntheticDataGenerator
from src.reconciliation import ReconciliationEngine
from src.config import settings
from src.reporting.exception_report import build_exception_report, format_as_markdown
from src.utils.formatters import safe_decimal, safe_numeric

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/runs", tags=["runs"])

# Active event queues for live streaming reconciliation runs
_ACTIVE_RUN_STREAMS: Dict[str, queue.Queue] = {}


def _resolve_investigation_providers(provider: Optional[str] = None) -> ProviderResolution:
    """
    Resolves per-role provider configuration for a multi-agent run.

    Delegates to src.agent.provider_resolution so the API and the controllers
    share one ladder. Previously each maintained its own, with different fallback
    rules, and they could disagree about whether a run was live.

    Roles degrade independently: a missing Verifier key no longer forces the
    Investigator offline too.
    """
    return resolve_providers(provider=provider)


def _multi_agent_token_totals(batch_agent: Any) -> Dict[str, Optional[int]]:
    """Sums cumulative token usage across the Investigator and Verifier clients."""
    totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for client in (getattr(batch_agent, "investigator_llm", None), getattr(batch_agent, "verifier_llm", None)):
        if client is None:
            continue
        totals["prompt_tokens"] += getattr(client, "cumulative_prompt_tokens", 0) or 0
        totals["completion_tokens"] += getattr(client, "cumulative_completion_tokens", 0) or 0
        totals["total_tokens"] += getattr(client, "cumulative_total_tokens", 0) or 0
    return totals


def _multi_agent_run_metadata(batch_agent: Any) -> Dict[str, Any]:
    """
    Extracts provider/mode/model metadata from the constructed agent clients.

    Reads the clients rather than the requested base provider because
    INVESTIGATOR_PROVIDER / VERIFIER_PROVIDER can override it — recording the
    base would misreport which API actually served the run.

    ``llm_degraded`` records whether either role silently fell back to the demo
    engine, so a persisted run carries the evidence that its decisions came from
    the offline emulator rather than a real model.
    """
    inv = getattr(batch_agent, "investigator_llm", None)
    ver = getattr(batch_agent, "verifier_llm", None)

    inv_provider = getattr(inv, "provider", None) or getattr(batch_agent, "provider", "demo")
    ver_provider = getattr(ver, "provider", None) or inv_provider

    provider_name = inv_provider if inv_provider == ver_provider else f"{inv_provider}+{ver_provider}"

    resolution = getattr(batch_agent, "resolution", None)
    degraded = bool(getattr(resolution, "degraded", False))
    degraded_reason = "; ".join(getattr(resolution, "degraded_reasons", ()) or ()) or None

    return {
        "llm_provider": provider_name[:20],  # llm_provider column is String(20)
        "llm_mode": getattr(inv, "mode", "DEMO"),
        "llm_model": getattr(inv, "model", "demo"),
        "llm_degraded": degraded,
        "llm_degraded_reason": degraded_reason,
    }


def _run_summary_from_model(run_model: Any) -> RunSummaryResponse:
    """
    Builds the API summary from a persisted run.

    Single conversion point on purpose: the upload path and the synthetic path
    previously each built this by hand and drifted apart, which is how the
    hardcoded accuracy figures survived on one path only.
    """
    return RunSummaryResponse(
        run_id=run_model.id,
        created_at=run_model.created_at.isoformat(),
        total_records=run_model.total_records,
        initial_reconciled=run_model.initial_reconciled,
        initial_exceptions=run_model.initial_exceptions,
        ai_auto_resolved=run_model.ai_auto_resolved,
        human_review=run_model.human_review,
        final_resolved=run_model.final_resolved,
        final_unresolved=run_model.final_unresolved,
        initial_match_rate=run_model.initial_match_rate,
        agent_resolution_rate=run_model.agent_resolution_rate,
        final_resolution_rate=run_model.final_resolution_rate,
        llm_provider=getattr(run_model, "llm_provider", None) or "demo",
        llm_mode=getattr(run_model, "llm_mode", None) or "DEMO",
        llm_model=getattr(run_model, "llm_model", None) or "demo",
        prompt_tokens=getattr(run_model, "prompt_tokens", None),
        completion_tokens=getattr(run_model, "completion_tokens", None),
        total_tokens=getattr(run_model, "total_tokens", None),
        llm_cases_selected=getattr(run_model, "llm_cases_selected", None),
        llm_cases_completed=getattr(run_model, "llm_cases_completed", None),
        llm_cases_not_evaluated=getattr(run_model, "llm_cases_not_evaluated", None),
        llm_degraded=bool(getattr(run_model, "llm_degraded", False)),
        llm_degraded_reason=getattr(run_model, "llm_degraded_reason", None),
        evaluation_group_id=getattr(run_model, "evaluation_group_id", None),
        evaluation_run_number=getattr(run_model, "evaluation_run_number", None),
        evaluation_runs_total=getattr(run_model, "evaluation_runs_total", None),
        # Accuracy fields stay None when the run had no ground truth.
        phase1_accuracy=run_model.phase1_accuracy,
        phase2_accuracy=run_model.phase2_accuracy,
        auto_resolution_precision=run_model.auto_resolution_precision,
        auto_resolution_recall=run_model.auto_resolution_recall,
        ground_truth_accuracy=run_model.ground_truth_accuracy,
        has_ground_truth=bool(getattr(run_model, "has_ground_truth", False)),
        phase1_detection_precision=getattr(run_model, "phase1_detection_precision", None),
        phase1_detection_recall=getattr(run_model, "phase1_detection_recall", None),
        phase1_false_positives=getattr(run_model, "phase1_false_positives", None),
        phase1_false_negatives=getattr(run_model, "phase1_false_negatives", None),
        not_evaluated=getattr(run_model, "not_evaluated", 0) or 0,
        degraded_cases=getattr(run_model, "degraded_cases", 0) or 0,
        phase1_time_sec=run_model.phase1_time_sec,
        phase2_time_sec=run_model.phase2_time_sec,
        end_to_end_time_sec=run_model.end_to_end_time_sec,
        total_processing_time_sec=run_model.total_processing_time_sec,
        records_per_second=run_model.records_per_second,
        phase1_records_per_second=getattr(run_model, "phase1_records_per_second", None),
        phase2_cases_per_second=getattr(run_model, "phase2_cases_per_second", None),
        average_case_latency_sec=getattr(run_model, "average_case_latency_sec", None),
        tokens_per_case=getattr(run_model, "tokens_per_case", None),
    )


def _parse_uploaded_csv(file_bytes: bytes, filename: str, required_fields: List[str]) -> List[Dict[str, Any]]:
    """Helper to parse and validate uploaded CSV content with strict provenance and data-integrity invariants."""
    try:
        content = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            content = file_bytes.decode("latin-1")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Encoding error reading {filename}: {str(e)}")

    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail=f"{filename} is empty or missing headers.")

    fieldnames = [f.strip().lower().replace(" ", "_") for f in reader.fieldnames if f]
    base_filename = os.path.basename(filename)

    # Flexible header checking (e.g. amount vs credited_amount)
    missing = []
    for req in required_fields:
        if req not in fieldnames:
            # check alternatives
            if req == "credited_amount" and "amount" in fieldnames:
                continue
            if req == "amount" and "payment_amount" in fieldnames:
                continue
            if req == "amount" and "credited_amount" in fieldnames:
                continue
            missing.append(req)

    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"{filename} missing required columns: {', '.join(missing)}. Found: {', '.join(reader.fieldnames)}",
        )

    rows = []
    for i, raw_row in enumerate(reader):
        row_num = i + 1
        clean_row = {}
        for k, v in raw_row.items():
            if k:
                clean_k = k.strip().lower().replace(" ", "_")
                clean_v = v.strip() if v is not None else ""
                clean_row[clean_k] = clean_v

        # Provenance tracking
        clean_row["_source_file"] = base_filename
        clean_row["_source_row"] = row_num

        raw_cred = clean_row.get("credited_amount") or clean_row.get("amount")
        clean_row["_raw_credited_amount"] = raw_cred

        # Normalize keys
        if "amount" in clean_row and "credited_amount" not in clean_row and "payment_amount" not in clean_row:
            clean_row["credited_amount"] = clean_row["amount"]
        if "payment_amount" in clean_row and "amount" not in clean_row:
            clean_row["amount"] = clean_row["payment_amount"]
        if "gross_amount" in clean_row and "fee" in clean_row and "net_amount" not in clean_row:
            g_dec = safe_decimal(clean_row.get("gross_amount"))
            f_dec = safe_decimal(clean_row.get("fee"))
            if g_dec is not None and f_dec is not None:
                clean_row["net_amount"] = str(safe_numeric(g_dec - f_dec))

        # Enforce validation invariants: verify raw string parses accurately to Decimal
        for field in ["amount", "credited_amount", "gross_amount", "fee", "net_amount"]:
            if field in clean_row and clean_row[field] != "":
                raw_val = clean_row[field]
                parsed_dec = safe_decimal(raw_val)
                if parsed_dec is None:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Data validation failed: Invalid numeric value '{raw_val}' in {base_filename} at row {row_num} (field: {field}).",
                    )
                # Verify round-trip conversion without truncation
                expected_norm = Decimal(raw_val.strip().replace("₹", "").replace("$", "").replace(",", ""))
                if parsed_dec != expected_norm:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Data corruption detected: '{raw_val}' parsed as '{parsed_dec}' in {base_filename} at row {row_num} (field: {field}).",
                    )

        rows.append(clean_row)

    if len(rows) == 0:
        raise HTTPException(status_code=400, detail=f"{filename} contains 0 data rows.")

    return rows


@router.post("/validate")
@router.post("/validate/")
async def validate_csv_dataset(
    payments: Optional[UploadFile] = File(None),
    ledger: Optional[UploadFile] = File(None),
    bank: Optional[UploadFile] = File(None),
    adjustments: Optional[UploadFile] = File(None),
):
    """Validates uploaded CSV files without executing reconciliation."""
    status = {"valid": True, "errors": [], "sources": {}}

    if payments:
        try:
            p_bytes = await payments.read()
            p_rows = _parse_uploaded_csv(p_bytes, payments.filename or "payments.csv", ["transaction_id", "amount"])
            status["sources"]["payments"] = {"records": len(p_rows), "valid": True, "filename": payments.filename}
        except Exception as e:
            status["valid"] = False
            status["errors"].append(str(e.detail if isinstance(e, HTTPException) else e))
            status["sources"]["payments"] = {"records": 0, "valid": False, "error": str(e.detail if isinstance(e, HTTPException) else e)}
    else:
        status["sources"]["payments"] = {"records": 0, "valid": False, "error": "Payments file is required"}
        status["valid"] = False

    if ledger:
        try:
            l_bytes = await ledger.read()
            l_rows = _parse_uploaded_csv(l_bytes, ledger.filename or "ledger.csv", ["transaction_id", "gross_amount", "fee"])
            status["sources"]["ledger"] = {"records": len(l_rows), "valid": True, "filename": ledger.filename}
        except Exception as e:
            status["valid"] = False
            status["errors"].append(str(e.detail if isinstance(e, HTTPException) else e))
            status["sources"]["ledger"] = {"records": 0, "valid": False, "error": str(e.detail if isinstance(e, HTTPException) else e)}
    else:
        status["sources"]["ledger"] = {"records": 0, "valid": False, "error": "Ledger file is required"}
        status["valid"] = False

    if bank:
        try:
            b_bytes = await bank.read()
            b_rows = _parse_uploaded_csv(b_bytes, bank.filename or "bank.csv", ["transaction_id"])
            status["sources"]["bank"] = {"records": len(b_rows), "valid": True, "filename": bank.filename}
        except Exception as e:
            status["valid"] = False
            status["errors"].append(str(e.detail if isinstance(e, HTTPException) else e))
            status["sources"]["bank"] = {"records": 0, "valid": False, "error": str(e.detail if isinstance(e, HTTPException) else e)}
    else:
        status["sources"]["bank"] = {"records": 0, "valid": False, "error": "Bank file is required"}
        status["valid"] = False

    if adjustments:
        try:
            a_bytes = await adjustments.read()
            a_rows = _parse_uploaded_csv(a_bytes, adjustments.filename or "adjustments.csv", ["transaction_id", "adjustment_type", "amount"])
            status["sources"]["adjustments"] = {"records": len(a_rows), "valid": True, "filename": adjustments.filename}
        except Exception as e:
            status["sources"]["adjustments"] = {"records": 0, "valid": False, "error": str(e.detail if isinstance(e, HTTPException) else e)}
    else:
        status["sources"]["adjustments"] = {"records": 0, "valid": True, "note": "Optional (None provided)"}

    return status


@router.get("/validate")
@router.get("/validate/")
def get_validate_not_allowed():
    """GET not allowed for validation endpoint."""
    raise HTTPException(status_code=405, detail="Method Not Allowed. Use POST with multipart/form-data.")


def _execute_reconciliation_pipeline(
    run_id: str,
    payments_data: List[Dict[str, Any]],
    ledger_data: List[Dict[str, Any]],
    bank_data: List[Dict[str, Any]],
    adjustments_data: List[Dict[str, Any]],
    provider: Optional[str] = None,
    batch_size: Optional[int] = 5,
    db: Optional[Session] = None,
    event_callback: Optional[Any] = None,
    ground_truth_data: Optional[List[Dict[str, Any]]] = None,
) -> RunSummaryResponse:
    """
    Core reconciliation execution pipeline supporting synchronous and real-time
    streaming invocations.

    Accuracy is reported only when `ground_truth_data` is supplied. Without it
    every accuracy field is persisted as NULL so the UI shows N/A -- an
    unverifiable 100% is worse than an honest blank.
    """
    own_session = False
    if db is None:
        db = SessionLocal()
        own_session = True

    try:
        t_start = time.time()

        # Step 1: Milestone — Phase 1 started
        if event_callback:
            event_callback({"event": "phase1_started", "total_records": len(payments_data)})

        # Step 2: Phase 1 deterministic reconciliation
        t_p1_start = time.time()
        phase1_results, phase1_metrics = ReconciliationEngine.reconcile_records(payments_data, ledger_data, bank_data)
        t_p1_end = time.time()
        phase1_time_sec = max(t_p1_end - t_p1_start, 0.001)

        # Step 3: Milestone — Phase 1 completed
        if event_callback:
            event_callback({
                "event": "phase1_completed",
                "reconciled": phase1_metrics["reconciled_records"],
                "exceptions": phase1_metrics["exception_records"],
                "total": len(phase1_results),
            })

        exceptions = [r for r in phase1_results if r["status"] == "EXCEPTION"]

        # Step 4: Phase 2 AI agent investigation via BatchMultiAgentController
        t_p2_start = time.time()
        toolkit = FinancialToolkit(payments_data, ledger_data, bank_data, adjustments_data)

        # Resolve both roles once, then hand the resolution to the controller so
        # it cannot re-derive a different answer from the environment.
        resolution = _resolve_investigation_providers(provider)

        from src.agent.multi_agent.batch_multi_agent_controller import BatchMultiAgentController
        from src.agent.batch_partitioner import partition_exceptions_balanced

        # The tracer's event sink forwards each agent-workflow step to the SSE
        # stream, so the browser sees the same trace the terminal does. Terminal
        # output stays governed by SHOW_AGENT_TRACE; the sink is independent of it.
        agent_tracer = AgentTracer(
            event_sink=(lambda ev: event_callback({"event": "agent_trace", **ev})) if event_callback else None,
        )
        batch_agent = BatchMultiAgentController(
            toolkit=toolkit, resolution=resolution, tracer=agent_tracer
        )
        effective_batch_size = max(1, min(int(batch_size or 5), 10))
        chunks = partition_exceptions_balanced(exceptions, batch_size=effective_batch_size) if exceptions else []

        # Step 5: Milestone — Phase 2 started
        if event_callback:
            event_callback({
                "event": "phase2_started",
                "exception_count": len(exceptions),
                "batch_count": len(chunks),
                "batch_size": effective_batch_size,
            })

        agent_decisions = []
        investigation_logs = []
        cumulative_resolved = 0
        cumulative_human_review = 0
        cumulative_not_evaluated = 0
        degraded_cases = 0
        degraded_transaction_ids: List[str] = []

        for i, chunk in enumerate(chunks):
            batch_log = None
            try:
                chunk_decisions, batch_log = batch_agent.investigate_batch(chunk)
            except Exception as batch_err:
                # The whole batch failed (provider outage, auth error, timeout).
                # These cases were never assessed, so they are NOT_EVALUATED --
                # not HUMAN_REVIEW. Labelling a system failure as a considered
                # escalation would overstate what the agent actually did, and
                # one decision per exception keeps the accounting invariant.
                logger.warning(
                    "Batch %d/%d failed entirely (%s); marking %d case(s) NOT_EVALUATED",
                    i + 1, len(chunks), batch_err, len(chunk),
                )
                chunk_decisions = [
                    AgentDecision(
                        transaction_id=exc.get("transaction_id", "UNKNOWN"),
                        decision="NOT_EVALUATED",
                        exception_type=exc.get("reason", "UNKNOWN"),
                        resolution_type="NONE",
                        reason=(
                            "Agent could not evaluate this case: batch investigation failed "
                            f"({type(batch_err).__name__}). This is a system failure, not an "
                            "assessment of the case."
                        ),
                        evidence=[f"Phase 1 exception: {exc.get('reason', 'UNKNOWN')}"],
                        confidence=0.0,
                        recommended_action="Re-run investigation; case has not been assessed.",
                        resolution_source="INFRASTRUCTURE_FAILURE",
                    )
                    for exc in chunk
                ]

            # Cases the agents genuinely could not assess, from either the
            # whole-batch failure above or a per-case failure inside the batch.
            batch_degraded = (
                getattr(batch_log, "not_evaluated_count", 0) if batch_log is not None else len(chunk)
            )
            degraded_cases += batch_degraded
            if batch_log is not None:
                degraded_transaction_ids.extend(getattr(batch_log, "not_evaluated_transaction_ids", []))
            else:
                degraded_transaction_ids.extend(d.transaction_id for d in chunk_decisions)

            tool_provenance = getattr(batch_log, "tool_provenance", {}) if batch_log is not None else {}

            for d in chunk_decisions:
                agent_decisions.append(d)
                if d.decision == "AUTO_RESOLVED":
                    cumulative_resolved += 1
                elif d.decision == "HUMAN_REVIEW":
                    cumulative_human_review += 1
                else:
                    cumulative_not_evaluated += 1

                exc_obj = next((c for c in chunk if c.get("transaction_id") == d.transaction_id), {})
                # Real provenance: the toolkit methods the prefetch actually
                # invoked for this case, and the real LLM interaction count
                # (0 for cases settled by deterministic Decimal proof).
                tools_used = list(tool_provenance.get(d.transaction_id, []))
                t_log = {
                    "transaction_id": d.transaction_id,
                    "initial_exception": d.exception_type or exc_obj.get("reason", "UNKNOWN"),
                    "tools_used": tools_used,
                    "evidence": d.evidence or [],
                    "decision": d.decision,
                    "resolution_type": d.resolution_type or "NONE",
                    "resolved_difference": d.resolved_difference,
                    "reason": d.reason,
                    "confidence": d.confidence,
                    "recommended_action": d.recommended_action,
                    "tool_call_count": len(tools_used),
                    "tool_traces": [],
                    "resolution_source": d.resolution_source,
                    "model_interactions": d.model_interactions,
                }
                investigation_logs.append(t_log)

            # Step 6: Milestone — Phase 2 batch progress
            if event_callback:
                event_callback({
                    "event": "phase2_batch_progress",
                    "batch_index": i + 1,
                    "batch_total": len(chunks),
                    "cases_in_batch": len(chunk),
                    "cumulative_resolved": cumulative_resolved,
                    "cumulative_human_review": cumulative_human_review,
                    "cumulative_not_evaluated": cumulative_not_evaluated,
                })

        t_p2_end = time.time()
        phase2_time_sec = max(t_p2_end - t_p2_start, 0.001)
        end_to_end_time_sec = max(time.time() - t_start, 0.001)

        # Step 7: Metrics computation
        total_records = len(phase1_results)
        initial_reconciled = phase1_metrics["reconciled_records"]
        initial_exceptions = phase1_metrics["exception_records"]

        auto_resolved = sum(1 for d in agent_decisions if d.decision == "AUTO_RESOLVED")
        human_review = sum(1 for d in agent_decisions if d.decision == "HUMAN_REVIEW")
        not_evaluated = sum(1 for d in agent_decisions if d.decision == "NOT_EVALUATED")

        final_resolved = initial_reconciled + auto_resolved
        final_unresolved = len(agent_decisions) - auto_resolved
        assert final_resolved + final_unresolved == total_records, "Accounting invariant violated: final_resolved + final_unresolved != total_records"

        initial_match_rate = phase1_metrics["match_rate"]
        agent_resolution_rate = (auto_resolved / initial_exceptions * 100) if initial_exceptions > 0 else 0.0
        final_resolution_rate = (final_resolved / total_records * 100) if total_records > 0 else 0.0

        # Throughput, reported per phase so neither rate can be mistaken for the
        # other. Phase 1 is CPU-bound rule evaluation over every record; Phase 2
        # is LLM-bound investigation over exceptions only. The headline
        # records_per_second is the end-to-end rate, which is the only one that
        # describes the pipeline as a whole.
        phase1_records_per_second = total_records / phase1_time_sec
        phase2_cases_per_second = (len(agent_decisions) / phase2_time_sec) if agent_decisions else None
        end_to_end_records_per_second = total_records / end_to_end_time_sec
        avg_time_per_record = end_to_end_time_sec / total_records
        avg_case_latency = (phase2_time_sec / len(agent_decisions)) if agent_decisions else None

        run_meta = _multi_agent_run_metadata(batch_agent)
        provider_name = run_meta["llm_provider"]
        mode_name = run_meta["llm_mode"]
        model_name = run_meta["llm_model"]
        token_totals = _multi_agent_token_totals(batch_agent)
        tokens_per_case = (
            (token_totals["total_tokens"] or 0) / len(agent_decisions) if agent_decisions else None
        )

        # Accuracy is measured, never assumed. With no ground truth every
        # accuracy field stays None and surfaces as N/A.
        has_ground_truth = bool(ground_truth_data)
        if has_ground_truth:
            eval_results = evaluate_agent_decisions(
                agent_decisions,
                ground_truth_data,
                phase1_results=phase1_results,
            )
            phase1_accuracy = eval_results.phase1_accuracy
            phase2_accuracy = eval_results.phase2_decision_accuracy
            precision = eval_results.auto_resolution_precision
            recall = eval_results.auto_resolution_recall
            p1_det_precision = eval_results.phase1_detection_precision
            p1_det_recall = eval_results.phase1_detection_recall
            p1_false_positives = eval_results.phase1_false_positives
            p1_false_negatives = eval_results.phase1_false_negatives
        else:
            phase1_accuracy = None
            phase2_accuracy = None
            precision = None
            recall = None
            p1_det_precision = None
            p1_det_recall = None
            p1_false_positives = None
            p1_false_negatives = None

        run_data = {
            "id": run_id,
            "total_records": total_records,
            "initial_reconciled": initial_reconciled,
            "initial_exceptions": initial_exceptions,
            "ai_auto_resolved": auto_resolved,
            "human_review": human_review,
            "final_resolved": final_resolved,
            "final_unresolved": final_unresolved,
            "initial_match_rate": initial_match_rate,
            "agent_resolution_rate": agent_resolution_rate,
            "final_resolution_rate": final_resolution_rate,
            "llm_provider": provider_name,
            "llm_mode": mode_name,
            "llm_model": model_name,
            "llm_degraded": run_meta["llm_degraded"],
            "llm_degraded_reason": run_meta["llm_degraded_reason"],
            "prompt_tokens": token_totals["prompt_tokens"],
            "completion_tokens": token_totals["completion_tokens"],
            "total_tokens": token_totals["total_tokens"],
            "phase1_accuracy": phase1_accuracy,
            "phase2_accuracy": phase2_accuracy,
            "auto_resolution_precision": precision,
            "auto_resolution_recall": recall,
            "ground_truth_accuracy": phase2_accuracy,
            "has_ground_truth": has_ground_truth,
            "phase1_detection_precision": p1_det_precision,
            "phase1_detection_recall": p1_det_recall,
            "phase1_false_positives": p1_false_positives,
            "phase1_false_negatives": p1_false_negatives,
            "not_evaluated": not_evaluated,
            "degraded_cases": degraded_cases,
            "llm_cases_selected": len(exceptions),
            "llm_cases_completed": auto_resolved + human_review,
            "llm_cases_not_evaluated": not_evaluated,
            "phase1_time_sec": round(phase1_time_sec, 4),
            "phase2_time_sec": round(phase2_time_sec, 4),
            "end_to_end_time_sec": round(end_to_end_time_sec, 4),
            "total_processing_time_sec": round(end_to_end_time_sec, 4),
            "records_per_second": round(end_to_end_records_per_second, 2),
            "phase1_records_per_second": round(phase1_records_per_second, 2),
            "phase2_cases_per_second": round(phase2_cases_per_second, 4) if phase2_cases_per_second is not None else None,
            "average_time_per_record_sec": round(avg_time_per_record, 6),
            "average_case_latency_sec": round(avg_case_latency, 4) if avg_case_latency is not None else None,
            "tokens_per_case": round(tokens_per_case, 1) if tokens_per_case is not None else None,
        }

        # Step 8: Persist in Database
        bank_provenance_map = {}
        for r in bank_data:
            t_id = str(r.get("transaction_id", "")).strip()
            if t_id and t_id not in bank_provenance_map:
                raw_b = r.get("_raw_credited_amount") or r.get("credited_amount")
                parsed_b = safe_numeric(safe_decimal(raw_b))
                bank_provenance_map[t_id] = {
                    "source_file": r.get("_source_file", "bank.csv"),
                    "source_row": r.get("_source_row", 1),
                    "raw_credited_amount": str(raw_b) if raw_b is not None else None,
                    "parsed_credited_amount": parsed_b,
                }

        for r in phase1_results:
            t_id = str(r.get("transaction_id", "")).strip()
            prov = bank_provenance_map.get(t_id)
            if prov:
                r["source_provenance"] = prov

        run_model = FinanceRepository.create_run(db, run_data)
        FinanceRepository.save_transaction_results(db, run_id, phase1_results)
        FinanceRepository.save_adjustments(db, run_id, adjustments_data)
        FinanceRepository.save_agent_investigations(db, run_id, investigation_logs)

        # Step 9: Milestone — Run completed
        if event_callback:
            event_callback({
                "event": "run_completed",
                "run_id": run_id,
                "final_resolution_rate": final_resolution_rate,
                "total_records": total_records,
                "initial_reconciled": initial_reconciled,
                "ai_auto_resolved": auto_resolved,
                "human_review": human_review,
                "not_evaluated": not_evaluated,
                "degraded_cases": degraded_cases,
                "has_ground_truth": has_ground_truth,
            })

        return _run_summary_from_model(run_model)
    finally:
        if own_session and db is not None:
            db.close()


@router.post("/upload/start", status_code=status.HTTP_202_ACCEPTED)
@router.post("/upload/start/", status_code=status.HTTP_202_ACCEPTED)
async def start_upload_reconciliation(
    payments: UploadFile = File(...),
    ledger: UploadFile = File(...),
    bank: UploadFile = File(...),
    adjustments: Optional[UploadFile] = File(None),
    ground_truth: Optional[UploadFile] = File(None),
    provider: Optional[str] = Form(None),
    batch_size: Optional[int] = Form(5),
):
    """
    Initiates asynchronous reconciliation with real-time SSE progress streaming.
    Returns HTTP 202 immediately with run_id and stream_url.

    Supply `ground_truth` (transaction_id, expected_phase2_decision, and
    optionally is_phase1_exception) to have the run scored. Without it the run
    still executes and reports throughput and its exception list, but every
    accuracy figure comes back null rather than fabricated.
    """
    init_db()
    run_id = f"upload_{uuid.uuid4().hex[:8]}"

    # Step 1: Parse and validate uploaded CSV files synchronously
    p_bytes = await payments.read()
    l_bytes = await ledger.read()
    b_bytes = await bank.read()
    a_bytes = await adjustments.read() if adjustments else None
    gt_bytes = await ground_truth.read() if ground_truth else None

    payments_data = _parse_uploaded_csv(p_bytes, payments.filename or "payments.csv", ["transaction_id", "amount"])
    ledger_data = _parse_uploaded_csv(l_bytes, ledger.filename or "ledger.csv", ["transaction_id", "gross_amount", "fee"])
    bank_data = _parse_uploaded_csv(b_bytes, bank.filename or "bank.csv", ["transaction_id"])
    adjustments_data = (
        _parse_uploaded_csv(a_bytes, adjustments.filename or "adjustments.csv", ["transaction_id", "adjustment_type", "amount"])
        if a_bytes
        else []
    )
    ground_truth_data = (
        _parse_uploaded_csv(
            gt_bytes,
            ground_truth.filename or "ground_truth.csv",
            ["transaction_id", "expected_phase2_decision"],
        )
        if gt_bytes
        else None
    )

    event_q = queue.Queue()
    _ACTIVE_RUN_STREAMS[run_id] = event_q

    def event_callback(event_data: Dict[str, Any]):
        event_q.put(event_data)

    def worker():
        try:
            _execute_reconciliation_pipeline(
                run_id=run_id,
                payments_data=payments_data,
                ledger_data=ledger_data,
                bank_data=bank_data,
                adjustments_data=adjustments_data,
                provider=provider,
                batch_size=batch_size,
                event_callback=event_callback,
                ground_truth_data=ground_truth_data,
            )
        except Exception as e:
            event_q.put({"event": "run_error", "error": str(e)})
        finally:
            event_q.put({"event": "_stream_closed"})

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    return {
        "run_id": run_id,
        "status": "STARTED",
        "stream_url": f"/api/runs/{run_id}/stream",
    }


@router.get("/{run_id}/stream")
def stream_run_events(run_id: str, db: Session = Depends(get_db)):
    """SSE stream endpoint for real-time progressive reconciliation updates."""
    event_q = _ACTIVE_RUN_STREAMS.get(run_id)

    def event_generator():
        if not event_q:
            run = FinanceRepository.get_run_by_id(db, run_id)
            if run:
                yield f"event: run_completed\ndata: {json.dumps({'run_id': run.id, 'final_resolution_rate': run.final_resolution_rate})}\n\n"
            else:
                yield f"event: run_error\ndata: {json.dumps({'error': f'Reconciliation run {run_id} not found or stream expired.'})}\n\n"
            return

        while True:
            try:
                event_data = event_q.get(timeout=30.0)
                if event_data.get("event") == "_stream_closed":
                    _ACTIVE_RUN_STREAMS.pop(run_id, None)
                    break
                event_name = event_data.get("event", "message")
                yield f"event: {event_name}\ndata: {json.dumps(event_data)}\n\n"
                if event_name in ("run_completed", "run_error"):
                    _ACTIVE_RUN_STREAMS.pop(run_id, None)
                    break
            except queue.Empty:
                yield ": heartbeat\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/upload", response_model=RunSummaryResponse, status_code=201)
@router.post("/upload/", response_model=RunSummaryResponse, status_code=201)
async def create_run_from_upload(
    payments: UploadFile = File(...),
    ledger: UploadFile = File(...),
    bank: UploadFile = File(...),
    adjustments: Optional[UploadFile] = File(None),
    ground_truth: Optional[UploadFile] = File(None),
    provider: Optional[str] = Form(None),
    batch_size: Optional[int] = Form(5),
    db: Session = Depends(get_db),
):
    """
    Executes the reconciliation pipeline synchronously with user-uploaded CSV source files.

    Supply `ground_truth` to have the run scored. Without it, accuracy fields
    are returned as null rather than assumed.
    """
    init_db()
    run_id = f"upload_{uuid.uuid4().hex[:8]}"

    p_bytes = await payments.read()
    l_bytes = await ledger.read()
    b_bytes = await bank.read()
    a_bytes = await adjustments.read() if adjustments else None
    gt_bytes = await ground_truth.read() if ground_truth else None

    payments_data = _parse_uploaded_csv(p_bytes, payments.filename or "payments.csv", ["transaction_id", "amount"])
    ledger_data = _parse_uploaded_csv(l_bytes, ledger.filename or "ledger.csv", ["transaction_id", "gross_amount", "fee"])
    bank_data = _parse_uploaded_csv(b_bytes, bank.filename or "bank.csv", ["transaction_id"])
    adjustments_data = (
        _parse_uploaded_csv(a_bytes, adjustments.filename or "adjustments.csv", ["transaction_id", "adjustment_type", "amount"])
        if a_bytes
        else []
    )
    ground_truth_data = (
        _parse_uploaded_csv(
            gt_bytes,
            ground_truth.filename or "ground_truth.csv",
            ["transaction_id", "expected_phase2_decision"],
        )
        if gt_bytes
        else None
    )

    return _execute_reconciliation_pipeline(
        run_id=run_id,
        payments_data=payments_data,
        ledger_data=ledger_data,
        bank_data=bank_data,
        adjustments_data=adjustments_data,
        provider=provider,
        batch_size=batch_size,
        db=db,
        ground_truth_data=ground_truth_data,
    )


@router.get("/upload")
@router.get("/upload/")
def get_upload_not_allowed():
    """GET not allowed for upload endpoint."""
    raise HTTPException(status_code=405, detail="Method Not Allowed. Use POST with multipart/form-data.")


@router.post("", response_model=RunSummaryResponse, status_code=201)
def create_run(db: Session = Depends(get_db)):
    """
    Triggers an end-to-end reconciliation and AI investigation batch run with demo synthetic data.

    Phase 1: Deterministic reconciliation across payments, ledger, and bank.
    Phase 2: AI agent investigation across payments, ledger, bank, and adjustments.
    """
    init_db()
    t_start = time.time()
    run_id = f"run_{uuid.uuid4().hex[:8]}"

    # Project root directory for data CSVs
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, "..", "..", ".."))
    data_dir = os.path.join(project_root, "data")

    # Step 1: Generate synthetic data across 4 sources
    generator = SyntheticDataGenerator(seed=42, total_transactions=100)
    p_path, l_path, b_path, a_path = generator.save_to_csv(data_dir)
    payments, ledger, bank, adjustments, ground_truth = generator.generate()

    # Step 2: Phase 1 deterministic reconciliation
    t_p1_start = time.time()
    phase1_results, phase1_metrics = ReconciliationEngine.reconcile_batch(p_path, l_path, b_path)
    t_p1_end = time.time()
    phase1_time_sec = max(t_p1_end - t_p1_start, 0.001)

    # Step 3: Filter exceptions
    exceptions = [r for r in phase1_results if r["status"] == "EXCEPTION"]

    # Step 4: Phase 2 AI agent investigation (unified batch multi-agent)
    t_p2_start = time.time()
    toolkit = FinancialToolkit(payments, ledger, bank, adjustments)

    from src.agent.multi_agent.batch_multi_agent_controller import BatchMultiAgentController
    from src.agent.batch_partitioner import partition_exceptions_balanced

    resolution = _resolve_investigation_providers()
    batch_agent = BatchMultiAgentController(toolkit=toolkit, resolution=resolution)
    chunks = partition_exceptions_balanced(exceptions, batch_size=5) if exceptions else []

    agent_decisions = []
    investigation_logs = []
    degraded_cases = 0

    for chunk in chunks:
        batch_log = None
        try:
            chunk_decisions, batch_log = batch_agent.investigate_batch(chunk)
        except Exception as e:
            # Whole-batch failure. These cases were never assessed, so they are
            # NOT_EVALUATED rather than HUMAN_REVIEW -- a system failure is not
            # a considered escalation. One decision per exception still holds,
            # so the accounting invariant is preserved.
            logger.warning("Batch failed entirely (%s); marking %d case(s) NOT_EVALUATED", e, len(chunk))
            chunk_decisions = [
                AgentDecision(
                    transaction_id=exc["transaction_id"],
                    decision="NOT_EVALUATED",
                    exception_type=exc.get("reason", "UNKNOWN"),
                    resolution_type="NONE",
                    resolved_difference=None,
                    reason=(
                        f"Agent could not evaluate this case: batch investigation failed "
                        f"({type(e).__name__}). This is a system failure, not an assessment "
                        f"of the case."
                    ),
                    evidence=[f"Error: {str(e)}"],
                    confidence=0.0,
                    recommended_action="Re-run investigation; case has not been assessed.",
                    resolution_source="INFRASTRUCTURE_FAILURE",
                )
                for exc in chunk
            ]

        degraded_cases += (
            getattr(batch_log, "not_evaluated_count", 0) if batch_log is not None else len(chunk)
        )
        tool_provenance = getattr(batch_log, "tool_provenance", {}) if batch_log is not None else {}

        for d in chunk_decisions:
            agent_decisions.append(d)
            exc_obj = next((c for c in chunk if c.get("transaction_id") == d.transaction_id), {})
            # Real provenance: the toolkit methods actually invoked for this case.
            tools_used = list(tool_provenance.get(d.transaction_id, []))
            investigation_logs.append({
                "transaction_id": d.transaction_id,
                "initial_exception": d.exception_type or exc_obj.get("reason", "UNKNOWN"),
                "tools_used": tools_used,
                "evidence": d.evidence or [],
                "decision": d.decision,
                "resolution_type": d.resolution_type or "NONE",
                "resolved_difference": d.resolved_difference,
                "reason": d.reason,
                "confidence": d.confidence,
                "recommended_action": d.recommended_action,
                "tool_call_count": len(tools_used),
                "tool_traces": [],
                "resolution_source": d.resolution_source,
                "model_interactions": d.model_interactions,
            })

    t_p2_end = time.time()
    phase2_time_sec = max(t_p2_end - t_p2_start, 0.001)
    end_to_end_time_sec = max(time.time() - t_start, 0.001)

    # Step 5: Metrics & Ground Truth Evaluation
    total_records = len(phase1_results)
    initial_reconciled = phase1_metrics["reconciled_records"]
    initial_exceptions = phase1_metrics["exception_records"]

    auto_resolved = sum(1 for d in agent_decisions if d.decision == "AUTO_RESOLVED")
    human_review = sum(1 for d in agent_decisions if d.decision == "HUMAN_REVIEW")
    not_evaluated = sum(1 for d in agent_decisions if d.decision == "NOT_EVALUATED")

    final_resolved = initial_reconciled + auto_resolved
    final_unresolved = len(agent_decisions) - auto_resolved
    assert final_resolved + final_unresolved == total_records, "Accounting invariant violated: final_resolved + final_unresolved != total_records"

    initial_match_rate = phase1_metrics["match_rate"]
    agent_resolution_rate = (auto_resolved / initial_exceptions * 100) if initial_exceptions > 0 else 0.0
    final_resolution_rate = (final_resolved / total_records * 100) if total_records > 0 else 0.0

    # Synthetic data ships with ground truth, so this path is always scored --
    # including Phase 1 detection, which is measured rather than assumed.
    eval_results = evaluate_agent_decisions(
        agent_decisions,
        ground_truth,
        phase1_results=phase1_results,
    )

    # Throughput reported per phase; the headline rate is end-to-end.
    phase1_records_per_second = total_records / phase1_time_sec
    phase2_cases_per_second = (len(agent_decisions) / phase2_time_sec) if agent_decisions else None
    end_to_end_records_per_second = total_records / end_to_end_time_sec
    avg_time_per_record = end_to_end_time_sec / total_records
    avg_case_latency = (phase2_time_sec / len(agent_decisions)) if agent_decisions else None

    run_meta = _multi_agent_run_metadata(batch_agent)
    provider_name = run_meta["llm_provider"]
    mode_name = run_meta["llm_mode"]
    model_name = run_meta["llm_model"]
    token_totals = _multi_agent_token_totals(batch_agent)
    tokens_per_case = (
        (token_totals["total_tokens"] or 0) / len(agent_decisions) if agent_decisions else None
    )

    run_data = {
        "id": run_id,
        "total_records": total_records,
        "initial_reconciled": initial_reconciled,
        "initial_exceptions": initial_exceptions,
        "ai_auto_resolved": auto_resolved,
        "human_review": human_review,
        "final_resolved": final_resolved,
        "final_unresolved": final_unresolved,
        "initial_match_rate": initial_match_rate,
        "agent_resolution_rate": agent_resolution_rate,
        "final_resolution_rate": final_resolution_rate,
        "llm_provider": provider_name,
        "llm_mode": mode_name,
        "llm_model": model_name,
        "llm_degraded": run_meta["llm_degraded"],
        "llm_degraded_reason": run_meta["llm_degraded_reason"],
        "prompt_tokens": token_totals["prompt_tokens"],
        "completion_tokens": token_totals["completion_tokens"],
        "total_tokens": token_totals["total_tokens"],
        "phase1_accuracy": eval_results.phase1_accuracy,
        "phase2_accuracy": eval_results.phase2_decision_accuracy,
        "auto_resolution_precision": eval_results.auto_resolution_precision,
        "auto_resolution_recall": eval_results.auto_resolution_recall,
        "ground_truth_accuracy": eval_results.phase2_decision_accuracy,
        "has_ground_truth": True,
        "phase1_detection_precision": eval_results.phase1_detection_precision,
        "phase1_detection_recall": eval_results.phase1_detection_recall,
        "phase1_false_positives": eval_results.phase1_false_positives,
        "phase1_false_negatives": eval_results.phase1_false_negatives,
        "not_evaluated": not_evaluated,
        "degraded_cases": degraded_cases,
        "llm_cases_selected": len(exceptions),
        "llm_cases_completed": auto_resolved + human_review,
        "llm_cases_not_evaluated": not_evaluated,
        "phase1_time_sec": round(phase1_time_sec, 4),
        "phase2_time_sec": round(phase2_time_sec, 4),
        "end_to_end_time_sec": round(end_to_end_time_sec, 4),
        "total_processing_time_sec": round(end_to_end_time_sec, 4),
        "records_per_second": round(end_to_end_records_per_second, 2),
        "phase1_records_per_second": round(phase1_records_per_second, 2),
        "phase2_cases_per_second": round(phase2_cases_per_second, 4) if phase2_cases_per_second is not None else None,
        "average_time_per_record_sec": round(avg_time_per_record, 6),
        "average_case_latency_sec": round(avg_case_latency, 4) if avg_case_latency is not None else None,
        "tokens_per_case": round(tokens_per_case, 1) if tokens_per_case is not None else None,
    }

    # Step 6: Persist in Database
    bank_provenance_map = {}
    for idx, r in enumerate(bank):
        t_id = str(r.get("transaction_id", "")).strip()
        if t_id and t_id not in bank_provenance_map:
            raw_b = r.get("credited_amount")
            parsed_b = safe_numeric(safe_decimal(raw_b))
            bank_provenance_map[t_id] = {
                "source_file": "bank.csv",
                "source_row": idx + 2,
                "raw_credited_amount": str(raw_b) if raw_b is not None else None,
                "parsed_credited_amount": parsed_b,
            }

    for r in phase1_results:
        t_id = str(r.get("transaction_id", "")).strip()
        prov = bank_provenance_map.get(t_id)
        if prov:
            r["source_provenance"] = prov

    run_model = FinanceRepository.create_run(db, run_data)
    FinanceRepository.save_transaction_results(db, run_id, phase1_results)
    FinanceRepository.save_adjustments(db, run_id, adjustments)
    FinanceRepository.save_agent_investigations(db, run_id, investigation_logs)

    return _run_summary_from_model(run_model)


@router.get("", response_model=List[RunSummaryResponse])
def list_runs(limit: int = 20, db: Session = Depends(get_db)):
    """Lists recent execution runs."""
    runs = FinanceRepository.list_runs(db, limit=limit)
    return [_run_summary_from_model(r) for r in runs]


@router.get("/{run_id}/diagnostics/data-integrity", response_model=DataIntegrityDiagnosticResponse)
def get_data_integrity_diagnostics(run_id: str, db: Session = Depends(get_db)):
    """
    Development-only diagnostic reporting per-transaction source, normalized, reconciliation, and API amounts.
    Protected against production exposure.
    """
    env = settings.env.strip().lower()
    if env in ["production", "prod"]:
        raise HTTPException(status_code=403, detail="Diagnostics endpoint is disabled in production mode.")

    run = FinanceRepository.get_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    transactions = FinanceRepository.get_transactions_by_run(db=db, run_id=run_id)
    records = []
    discrepancy_count = 0

    for t in transactions:
        detail = FinanceRepository.get_transaction_detail(db, run_id, t.transaction_id)
        prov = detail.get("source_provenance") if detail else None

        raw_val = prov.get("raw_credited_amount") if prov else None
        parsed_val = prov.get("parsed_credited_amount") if prov else None
        norm_val = safe_numeric(safe_decimal(raw_val)) if raw_val is not None else parsed_val
        rec_val = t.bank_amount
        api_val = detail.get("bank_amount") if detail else None

        passed = True
        details_msg = "Integrity verified: Source == Normalized == Reconciliation == API"
        if raw_val is not None and rec_val is not None:
            if safe_decimal(raw_val) != safe_decimal(rec_val) or safe_decimal(rec_val) != safe_decimal(api_val):
                passed = False
                discrepancy_count += 1
                details_msg = f"Discrepancy detected: raw={raw_val}, rec={rec_val}, api={api_val}"

        records.append(
            DataIntegrityRecord(
                transaction_id=t.transaction_id,
                source_file=prov.get("source_file") if prov else None,
                source_row=prov.get("source_row") if prov else None,
                raw_bank_amount=str(raw_val) if raw_val is not None else None,
                parsed_bank_amount=parsed_val,
                normalized_bank_amount=norm_val,
                reconciliation_bank_amount=rec_val,
                api_bank_amount=api_val,
                integrity_passed=passed,
                details=details_msg,
            )
        )

    return DataIntegrityDiagnosticResponse(
        run_id=run_id,
        environment=env,
        total_records=len(records),
        all_passed=(discrepancy_count == 0),
        discrepancy_count=discrepancy_count,
        records=records,
    )


@router.get("/{run_id}/report")
def get_run_report(
    run_id: str,
    format: str = "markdown",
    download: bool = False,
    db: Session = Depends(get_db),
):
    """
    Generates and downloads the reconciliation exception report for a run.
    Format can be 'markdown' or 'json'.
    """
    try:
        report = build_exception_report(db, run_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if format.lower() == "json":
        json_content = json.dumps(report.as_dict(), indent=2)
        if download:
            return Response(
                content=json_content,
                media_type="application/json",
                headers={"Content-Disposition": f'attachment; filename="reconciliation_report_{run_id}.json"'},
            )
        return Response(content=json_content, media_type="application/json")
    else:
        md_content = format_as_markdown(report)
        if download:
            return Response(
                content=md_content,
                media_type="text/markdown; charset=utf-8",
                headers={"Content-Disposition": f'attachment; filename="reconciliation_report_{run_id}.md"'},
            )
        return Response(content=md_content, media_type="text/markdown; charset=utf-8")
