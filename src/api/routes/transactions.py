import csv
import io
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response
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


@router.get("/{run_id}/export/csv")
def export_run_transactions_csv(run_id: str, db: Session = Depends(get_db)):
    """
    Exports the reconciliation ledger for a run as a downloadable CSV file.
    """
    run = FinanceRepository.get_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    transactions = FinanceRepository.get_transactions_by_run(db=db, run_id=run_id)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Transaction ID",
        "Status",
        "Exception Type",
        "Payment Amount",
        "Gross Amount",
        "Fee",
        "Expected Net Amount",
        "Bank Amount",
        "Difference",
        "AI Decision",
        "Confidence",
        "Reason",
        "Recommended Action",
    ])

    for t in transactions:
        detail = FinanceRepository.get_transaction_detail(db, run_id, t.transaction_id)
        inv = detail.get("agent_investigation") if detail else None
        writer.writerow([
            t.transaction_id,
            t.status,
            t.exception_type or "None",
            t.payment_amount if t.payment_amount is not None else "",
            t.gross_amount if t.gross_amount is not None else "",
            t.fee if t.fee is not None else "",
            t.expected_net_amount if t.expected_net_amount is not None else "",
            t.bank_amount if t.bank_amount is not None else "",
            t.difference if t.difference is not None else 0,
            inv.get("decision", "N/A") if inv else ("RECONCILED" if t.status == "RECONCILED" else "HUMAN_REVIEW"),
            f"{(inv.get('confidence', 1.0) * 100):.0f}%" if inv else ("100%" if t.status == "RECONCILED" else "0%"),
            inv.get("reason", "Reconciled successfully" if t.status == "RECONCILED" else "") if inv else ("Reconciled successfully" if t.status == "RECONCILED" else ""),
            inv.get("recommended_action", "") if inv else "",
        ])

    csv_content = output.getvalue()
    filename = f"reconciliation_ledger_{run_id}.csv"
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

