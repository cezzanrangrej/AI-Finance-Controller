"""
API routes for querying exceptions and AI decision findings.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.api.schemas import ExceptionItemResponse
from src.db.database import get_db
from src.db.repository import FinanceRepository

router = APIRouter(prefix="/api/runs", tags=["exceptions"])


@router.get("/{run_id}/exceptions", response_model=List[ExceptionItemResponse])
def get_run_exceptions(
    run_id: str,
    status: Optional[str] = Query(None, description="Filter by status (e.g. EXCEPTION)"),
    exception_type: Optional[str] = Query(None, description="Filter by exception type"),
    decision: Optional[str] = Query(None, description="Filter by agent decision (AUTO_RESOLVED or HUMAN_REVIEW)"),
    db: Session = Depends(get_db),
):
    """
    Returns exception records for a run with optional filtering parameters.
    """
    run = FinanceRepository.get_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    exceptions = FinanceRepository.get_exceptions_by_run(
        db=db,
        run_id=run_id,
        status=status,
        exception_type=exception_type,
        decision=decision,
    )
    return [ExceptionItemResponse(**item) for item in exceptions]
