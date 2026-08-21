"""
API routes for audit trails.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.api.schemas import AuditItemResponse
from src.db.database import get_db
from src.db.repository import FinanceRepository

router = APIRouter(prefix="/api/runs", tags=["audit"])


@router.get("/{run_id}/audit", response_model=List[AuditItemResponse])
def get_run_audit_trail(run_id: str, db: Session = Depends(get_db)):
    """
    Returns a chronological audit trail for a run showing detection,
    Phase 1 reconciliation, and Phase 2 agent investigation events.
    """
    run = FinanceRepository.get_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    audit_events = FinanceRepository.get_audit_trail(db, run_id)
    return [AuditItemResponse(**ev) for ev in audit_events]
