"""
API routes for batch execution runs.
"""

import os
import time
import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.agent.controller import AgentController, LLMClient
from src.agent.evaluator import evaluate_agent_decisions
from src.agent.tools import FinancialToolkit
from src.api.schemas import RunSummaryResponse
from src.db.database import get_db, init_db
from src.db.repository import FinanceRepository
from src.generator import SyntheticDataGenerator
from src.reconciliation import ReconciliationEngine

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.post("", response_model=RunSummaryResponse, status_code=201)
def create_run(db: Session = Depends(get_db)):
    """
    Triggers an end-to-end reconciliation and AI investigation batch run.

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

    # Step 4: Phase 2 AI agent investigation
    t_p2_start = time.time()
    toolkit = FinancialToolkit(payments, ledger, bank, adjustments)
    llm_client = LLMClient()
    agent = AgentController(toolkit=toolkit, llm_client=llm_client)

    agent_decisions = []
    investigation_logs = []

    for exc in exceptions:
        try:
            decision, log = agent.investigate_exception(exc)
            agent_decisions.append(decision)
            investigation_logs.append(log.model_dump())
        except Exception as e:
            fallback_log = {
                "transaction_id": exc["transaction_id"],
                "initial_exception": exc["reason"],
                "tools_used": [],
                "evidence": [f"Error: {str(e)}"],
                "decision": "HUMAN_REVIEW",
                "resolution_type": "NONE",
                "resolved_difference": None,
                "reason": f"Agent error: {str(e)}",
                "confidence": 0.0,
                "recommended_action": "Manual review required.",
            }
            investigation_logs.append(fallback_log)

    t_p2_end = time.time()
    phase2_time_sec = max(t_p2_end - t_p2_start, 0.001)
    end_to_end_time_sec = max(time.time() - t_start, 0.001)

    # Step 5: Metrics & Ground Truth Evaluation
    total_records = len(phase1_results)
    initial_reconciled = phase1_metrics["reconciled_records"]
    initial_exceptions = phase1_metrics["exception_records"]

    auto_resolved = sum(1 for d in agent_decisions if d.decision == "AUTO_RESOLVED")
    human_review = sum(1 for d in agent_decisions if d.decision == "HUMAN_REVIEW")

    final_resolved = initial_reconciled + auto_resolved
    final_unresolved = human_review

    initial_match_rate = phase1_metrics["match_rate"]
    agent_resolution_rate = (auto_resolved / initial_exceptions * 100) if initial_exceptions > 0 else 0.0
    final_resolution_rate = (final_resolved / total_records * 100) if total_records > 0 else 0.0

    eval_results = evaluate_agent_decisions(agent_decisions, ground_truth)

    phase1_throughput = total_records / phase1_time_sec
    avg_time_per_record = end_to_end_time_sec / total_records

    provider_name = getattr(llm_client, "provider", "demo")
    mode_name = getattr(llm_client, "mode", "DEMO")
    model_name = getattr(llm_client, "model", "demo")

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
        "prompt_tokens": getattr(llm_client, "last_prompt_tokens", None),
        "completion_tokens": getattr(llm_client, "last_completion_tokens", None),
        "total_tokens": getattr(llm_client, "last_total_tokens", None),
        "phase1_accuracy": eval_results.phase1_accuracy,
        "phase2_accuracy": eval_results.phase2_decision_accuracy,
        "auto_resolution_precision": eval_results.auto_resolution_precision,
        "auto_resolution_recall": eval_results.auto_resolution_recall,
        "ground_truth_accuracy": eval_results.phase2_decision_accuracy,
        "phase1_time_sec": round(phase1_time_sec, 4),
        "phase2_time_sec": round(phase2_time_sec, 4),
        "end_to_end_time_sec": round(end_to_end_time_sec, 4),
        "total_processing_time_sec": round(end_to_end_time_sec, 4),
        "records_per_second": round(phase1_throughput, 2),
        "average_time_per_record_sec": round(avg_time_per_record, 6),
    }

    # Step 6: Persist in Database
    run_model = FinanceRepository.create_run(db, run_data)
    FinanceRepository.save_transaction_results(db, run_id, phase1_results)
    FinanceRepository.save_adjustments(db, run_id, adjustments)
    FinanceRepository.save_agent_investigations(db, run_id, investigation_logs)

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
        llm_provider=getattr(run_model, "llm_provider", provider_name),
        llm_mode=getattr(run_model, "llm_mode", mode_name),
        llm_model=getattr(run_model, "llm_model", model_name),
        prompt_tokens=getattr(run_model, "prompt_tokens", None),
        completion_tokens=getattr(run_model, "completion_tokens", None),
        total_tokens=getattr(run_model, "total_tokens", None),
        phase1_accuracy=run_model.phase1_accuracy,
        phase2_accuracy=run_model.phase2_accuracy,
        auto_resolution_precision=run_model.auto_resolution_precision,
        auto_resolution_recall=run_model.auto_resolution_recall,
        ground_truth_accuracy=run_model.ground_truth_accuracy,
        phase1_time_sec=run_model.phase1_time_sec,
        phase2_time_sec=run_model.phase2_time_sec,
        end_to_end_time_sec=run_model.end_to_end_time_sec,
        total_processing_time_sec=run_model.total_processing_time_sec,
        records_per_second=run_model.records_per_second,
    )


@router.get("", response_model=List[RunSummaryResponse])
def list_runs(limit: int = 20, db: Session = Depends(get_db)):
    """Lists recent execution runs."""
    runs = FinanceRepository.list_runs(db, limit=limit)
    return [
        RunSummaryResponse(
            run_id=r.id,
            created_at=r.created_at.isoformat(),
            total_records=r.total_records,
            initial_reconciled=r.initial_reconciled,
            initial_exceptions=r.initial_exceptions,
            ai_auto_resolved=r.ai_auto_resolved,
            human_review=r.human_review,
            final_resolved=r.final_resolved,
            final_unresolved=r.final_unresolved,
            initial_match_rate=r.initial_match_rate,
            agent_resolution_rate=r.agent_resolution_rate,
            final_resolution_rate=r.final_resolution_rate,
            llm_provider=getattr(r, "llm_provider", "demo") or "demo",
            llm_mode=getattr(r, "llm_mode", "DEMO") or "DEMO",
            llm_model=getattr(r, "llm_model", "demo") or "demo",
            prompt_tokens=getattr(r, "prompt_tokens", None),
            completion_tokens=getattr(r, "completion_tokens", None),
            total_tokens=getattr(r, "total_tokens", None),
            phase1_accuracy=r.phase1_accuracy,
            phase2_accuracy=r.phase2_accuracy,
            auto_resolution_precision=r.auto_resolution_precision,
            auto_resolution_recall=r.auto_resolution_recall,
            ground_truth_accuracy=r.ground_truth_accuracy,
            phase1_time_sec=r.phase1_time_sec,
            phase2_time_sec=r.phase2_time_sec,
            end_to_end_time_sec=r.end_to_end_time_sec,
            total_processing_time_sec=r.total_processing_time_sec,
            records_per_second=r.records_per_second,
        )
        for r in runs
    ]
