"""
API routes for transaction listing and detailed multi-source deep dives.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.api.schemas import TransactionDetailResponse
from src.db.database import get_db
from src.db.repository import FinanceRepository

router = APIRouter(prefix="/api/runs", tags=["transactions"])


@router.get("/{run_id}/transactions", response_model=List[TransactionDetailResponse])
def get_run_transactions(
    run_id: str,
    status: Optional[str] = Query(None, description="Filter by status (RECONCILED / EXCEPTION)"),
    exception_type: Optional[str] = Query(None, description="Filter by exception category"),
    db: Session = Depends(get_db),
):
    """
    Returns transactions for a run.
    """
    run = FinanceRepository.get_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    transactions = FinanceRepository.get_transactions_by_run(
        db=db,
        run_id=run_id,
        status=status,
        exception_type=exception_type,
    )

    results = []
    for t in transactions:
        detail = FinanceRepository.get_transaction_detail(db, run_id, t.transaction_id)
        if detail:
            results.append(TransactionDetailResponse(**detail))
    return results


@router.get("/{run_id}/transactions/{transaction_id}", response_model=TransactionDetailResponse)
def get_transaction_detail(run_id: str, transaction_id: str, db: Session = Depends(get_db)):
    """
    Returns full details for a single transaction including Phase 1 result & Phase 2 investigation.
    """
    run = FinanceRepository.get_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    detail = FinanceRepository.get_transaction_detail(db, run_id, transaction_id)
    if not detail:
        raise HTTPException(status_code=404, detail=f"Transaction '{transaction_id}' not found in run '{run_id}'")

    return TransactionDetailResponse(**detail)
