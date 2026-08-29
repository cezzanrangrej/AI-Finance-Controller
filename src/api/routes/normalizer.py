"""
API endpoints for dataset normalization preview and execution.
"""

import json
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from src.api.schemas import RunSummaryResponse
from src.db.database import get_db, init_db
from src.db.repository import FinanceRepository
from src.normalizer import get_normalizer, list_normalizers
from src.normalizer.schemas import NormalizationPreviewResponse
from src.reconciliation import ReconciliationEngine
from src.utils.formatters import safe_decimal, safe_numeric

router = APIRouter(prefix="/api/normalizer", tags=["Normalizer"])


@router.get("/registry")
def get_registry() -> List[Dict[str, str]]:
    """Returns all registered dataset normalizers."""
    return list_normalizers()


@router.post("/preview", response_model=NormalizationPreviewResponse)
async def preview_normalization(
    file: UploadFile = File(...),
    source_type: str = Form("ibm_aml"),
    mapping: Optional[str] = Form(None),
):
    """
    Parses and previews normalization results without persisting into the database.
    """
    try:
        normalizer = get_normalizer(source_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    file_bytes = await file.read()
    mapping_dict = None
    if mapping:
        try:
            mapping_dict = json.loads(mapping)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON format for column mapping.")

    try:
        raw_rows, filename = normalizer.read_csv_rows(file_bytes, file.filename)
        normalized = normalizer.normalize(
            source_input=raw_rows,
            filename=filename,
            derive_reconciliation_sources=True,
            mapping=mapping_dict,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Normalization preview failed: {str(e)}")

    sample_source = raw_rows[:5] if raw_rows else []
    sample_normalized = [
        {
            "transaction_id": p.transaction_id,
            "amount": p.amount,
            "merchant_id": p.merchant_id,
            "date": p.date,
            "status": p.status,
        }
        for p in normalized.payments[:5]
    ]

    return NormalizationPreviewResponse(
        normalizer=normalized.manifest.normalizer,
        source_dataset=normalized.manifest.source_dataset,
        source_type=normalized.manifest.source_type,
        source_filename=normalized.manifest.source_file,
        total_source_rows=len(raw_rows),
        normalized_payments_count=len(normalized.payments),
        derived_ledger_count=len(normalized.ledger),
        derived_bank_count=len(normalized.bank),
        derived_adjustments_count=len(normalized.adjustments),
        sample_source_rows=sample_source,
        sample_normalized_rows=sample_normalized,
        column_mapping=normalized.manifest.column_mapping,
        warnings=normalized.warnings,
        errors=normalized.errors,
        valid=len(normalized.errors) == 0 and len(normalized.payments) > 0,
    )
