"""
Repository pattern for database operations.
"""

import json
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from src.db.models import AdjustmentModel, AgentInvestigationModel, GroundTruthModel, RunModel, TransactionResultModel


class FinanceRepository:
    """Encapsulates all database interactions for runs, transactions, adjustments, and audit trails."""

    @staticmethod
    def create_run(db: Session, run_data: Dict[str, Any]) -> RunModel:
        """Saves a new run summary to the database."""
        run = RunModel(**run_data)
        db.add(run)
        db.commit()
        db.refresh(run)
        return run

    @staticmethod
    def save_transaction_results(db: Session, run_id: str, results: List[Dict[str, Any]]) -> None:
        """Bulk inserts Phase 1 transaction results."""
        objects = []
        for r in results:
            objects.append(
                TransactionResultModel(
                    run_id=run_id,
                    transaction_id=r["transaction_id"],
                    status=r["status"],
                    exception_type=r["reason"],
                    payment_amount=r.get("payment_amount"),
                    gross_amount=r.get("gross_amount"),
                    fee=r.get("fee"),
                    expected_net_amount=r.get("expected_net_amount"),
                    bank_amount=r.get("bank_amount"),
                    difference=r.get("difference"),
                )
            )
        db.bulk_save_objects(objects)
        db.commit()

    @staticmethod
    def save_adjustments(db: Session, run_id: str, adjustments: List[Dict[str, Any]]) -> None:
        """Bulk inserts source adjustment records."""
        objects = []
        for adj in adjustments:
            objects.append(
                AdjustmentModel(
                    run_id=run_id,
                    transaction_id=adj["transaction_id"],
                    adjustment_type=adj["adjustment_type"],
                    amount=int(adj["amount"]),
                    reason=adj["reason"],
                    date=adj.get("date"),
                    reference=adj.get("reference"),
                )
            )
        db.bulk_save_objects(objects)
        db.commit()

    @staticmethod
    def save_agent_investigations(db: Session, run_id: str, logs: List[Dict[str, Any]]) -> None:
        """Bulk inserts Phase 2 agent investigation logs."""
        objects = []
        for log in logs:
            evidence_json = json.dumps(log.get("evidence", []))
            tools_json = json.dumps(log.get("tools_used", []))
            objects.append(
                AgentInvestigationModel(
                    run_id=run_id,
                    transaction_id=log["transaction_id"],
                    initial_exception=log["initial_exception"],
                    decision=log["decision"],
                    resolution_type=log.get("resolution_type", "NONE"),
                    resolved_difference=log.get("resolved_difference"),
                    reason=log["reason"],
                    recommended_action=log["recommended_action"],
                    confidence=log["confidence"],
                    evidence_json=evidence_json,
                    tools_used_json=tools_json,
                )
            )
        db.bulk_save_objects(objects)
        db.commit()

    @staticmethod
    def get_run(db: Session, run_id: str) -> Optional[RunModel]:
        """Retrieves a single run by ID."""
        return db.query(RunModel).filter(RunModel.id == run_id).first()

    @staticmethod
    def list_runs(db: Session, limit: int = 20) -> List[RunModel]:
        """Retrieves recent runs ordered by creation date descending."""
        return db.query(RunModel).order_by(RunModel.created_at.desc()).limit(limit).all()

    @staticmethod
    def get_transactions_by_run(
        db: Session,
        run_id: str,
        status: Optional[str] = None,
        exception_type: Optional[str] = None
    ) -> List[TransactionResultModel]:
        """Queries transactions for a specific run with optional filters."""
        query = db.query(TransactionResultModel).filter(TransactionResultModel.run_id == run_id)
        if status:
            query = query.filter(TransactionResultModel.status == status)
        if exception_type:
            query = query.filter(TransactionResultModel.exception_type == exception_type)
        return query.all()

    @staticmethod
    def get_transaction_detail(db: Session, run_id: str, transaction_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves complete details for a transaction including payment, ledger, bank, adjustments, & AI investigation."""
        txn = (
            db.query(TransactionResultModel)
            .filter(TransactionResultModel.run_id == run_id, TransactionResultModel.transaction_id == transaction_id)
            .first()
        )
        if not txn:
            return None

        investigation = (
            db.query(AgentInvestigationModel)
            .filter(AgentInvestigationModel.run_id == run_id, AgentInvestigationModel.transaction_id == transaction_id)
            .first()
        )

        adj_records = (
            db.query(AdjustmentModel)
            .filter(AdjustmentModel.run_id == run_id, AdjustmentModel.transaction_id == transaction_id)
            .all()
        )

        adjustments_data = [
            {
                "adjustment_type": a.adjustment_type,
                "amount": a.amount,
                "reason": a.reason,
                "date": a.date,
                "reference": a.reference,
            }
            for a in adj_records
        ]

        inv_data = None
        if investigation:
            inv_data = {
                "decision": investigation.decision,
                "resolution_type": investigation.resolution_type,
                "resolved_difference": investigation.resolved_difference,
                "reason": investigation.reason,
                "recommended_action": investigation.recommended_action,
                "confidence": investigation.confidence,
                "evidence": json.loads(investigation.evidence_json),
                "tools_used": json.loads(investigation.tools_used_json),
                "created_at": investigation.created_at.isoformat(),
            }

        return {
            "transaction_id": txn.transaction_id,
            "status": txn.status,
            "exception_type": txn.exception_type,
            "payment_amount": txn.payment_amount,
            "gross_amount": txn.gross_amount,
            "fee": txn.fee,
            "expected_net_amount": txn.expected_net_amount,
            "bank_amount": txn.bank_amount,
            "difference": txn.difference,
            "adjustments": adjustments_data,
            "agent_investigation": inv_data,
        }

    @staticmethod
    def get_exceptions_by_run(
        db: Session,
        run_id: str,
        status: Optional[str] = None,
        exception_type: Optional[str] = None,
        decision: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Queries exception records joining transaction results and agent decisions."""
        query = (
            db.query(TransactionResultModel, AgentInvestigationModel)
            .outerjoin(
                AgentInvestigationModel,
                (TransactionResultModel.run_id == AgentInvestigationModel.run_id)
                & (TransactionResultModel.transaction_id == AgentInvestigationModel.transaction_id),
            )
            .filter(TransactionResultModel.run_id == run_id, TransactionResultModel.status == "EXCEPTION")
        )

        if exception_type:
            query = query.filter(TransactionResultModel.exception_type == exception_type)
        if decision:
            query = query.filter(AgentInvestigationModel.decision == decision)

        results = []
        for txn, inv in query.all():
            evidence = json.loads(inv.evidence_json) if inv else []
            results.append({
                "transaction_id": txn.transaction_id,
                "exception_type": txn.exception_type,
                "status": txn.status,
                "decision": inv.decision if inv else "HUMAN_REVIEW",
                "resolution_type": inv.resolution_type if inv else "NONE",
                "payment_amount": txn.payment_amount,
                "gross_amount": txn.gross_amount,
                "fee": txn.fee,
                "expected_amount": txn.expected_net_amount,
                "actual_amount": txn.bank_amount,
                "difference": txn.difference,
                "reason": inv.reason if inv else "Pending investigation",
                "recommended_action": inv.recommended_action if inv else "Manual review",
                "confidence": inv.confidence if inv else 0.0,
                "evidence": evidence,
            })
        return results

    @staticmethod
    def get_audit_trail(db: Session, run_id: str) -> List[Dict[str, Any]]:
        """Generates a chronological audit trail for a run."""
        txns = db.query(TransactionResultModel).filter(TransactionResultModel.run_id == run_id).all()
        investigations = (
            db.query(AgentInvestigationModel)
            .filter(AgentInvestigationModel.run_id == run_id)
            .all()
        )
        inv_map = {inv.transaction_id: inv for inv in investigations}

        audit_events = []
        for txn in txns:
            audit_events.append({
                "transaction_id": txn.transaction_id,
                "step": "DETECTION",
                "status": txn.status,
                "event": f"Transaction {txn.transaction_id} ingested across payments, ledger, bank, and adjustments.",
            })

            if txn.status == "RECONCILED":
                audit_events.append({
                    "transaction_id": txn.transaction_id,
                    "step": "PHASE_1_RECONCILIATION",
                    "status": "RECONCILED",
                    "event": f"Transaction {txn.transaction_id} reconciled by Phase 1 rules.",
                })
            else:
                audit_events.append({
                    "transaction_id": txn.transaction_id,
                    "step": "PHASE_1_RECONCILIATION",
                    "status": "EXCEPTION",
                    "event": f"Phase 1 exception: {txn.exception_type}.",
                })

                inv = inv_map.get(txn.transaction_id)
                if inv:
                    tools = json.loads(inv.tools_used_json)
                    evidence = json.loads(inv.evidence_json)
                    audit_events.append({
                        "transaction_id": txn.transaction_id,
                        "step": "AGENT_INVESTIGATION",
                        "status": inv.decision,
                        "event": f"Agent called tools ({', '.join(tools)}) and evaluated evidence.",
                        "evidence": evidence,
                        "decision": inv.decision,
                        "reason": inv.reason,
                        "confidence": inv.confidence,
                    })
        return audit_events
