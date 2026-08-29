"""
Canonical financial schemas and dataset structures for the normalization layer.

Matches the existing reconciliation engine's expected fields:
- Payments: transaction_id, amount, merchant_id, date, status
- Ledger: transaction_id, gross_amount, fee, net_amount, date, status
- Bank: bank_reference, transaction_id, credited_amount, date
- Adjustments: transaction_id, adjustment_type, amount, reason, date, reference
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator

from src.utils.formatters import safe_decimal, safe_numeric


class ProvenanceRecord(BaseModel):
    """Provenance tracking for a single normalized record."""
    source_file: str
    source_row: int
    source_dataset: str
    raw_transaction_id: Optional[str] = None
    raw_amount: Optional[str] = None
    normalized_transaction_id: str
    normalized_amount: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CanonicalPaymentRecord(BaseModel):
    """Canonical payment gateway record."""
    transaction_id: str
    amount: float
    merchant_id: str = "MERCHANT_DEFAULT"
    date: str = "2026-08-20"
    status: str = "CAPTURED"
    provenance: Optional[ProvenanceRecord] = None

    @field_validator("transaction_id", mode="before")
    @classmethod
    def sanitize_id(cls, v: Any) -> str:
        return str(v).strip()

    @field_validator("amount", mode="before")
    @classmethod
    def sanitize_amount(cls, v: Any) -> float:
        dec = safe_decimal(v)
        if dec is None:
            raise ValueError(f"Invalid monetary amount: {v}")
        return float(safe_numeric(dec))


class CanonicalLedgerRecord(BaseModel):
    """Canonical internal accounting ledger record."""
    transaction_id: str
    gross_amount: float
    fee: float = 0.0
    net_amount: float
    date: str = "2026-08-20"
    status: str = "POSTED"
    provenance: Optional[ProvenanceRecord] = None

    @field_validator("transaction_id", mode="before")
    @classmethod
    def sanitize_id(cls, v: Any) -> str:
        return str(v).strip()

    @field_validator("gross_amount", "fee", "net_amount", mode="before")
    @classmethod
    def sanitize_amounts(cls, v: Any) -> float:
        dec = safe_decimal(v)
        if dec is None:
            raise ValueError(f"Invalid monetary amount: {v}")
        return float(safe_numeric(dec))


class CanonicalBankRecord(BaseModel):
    """Canonical bank settlement record."""
    bank_reference: str
    transaction_id: str
    credited_amount: float
    date: str = "2026-08-20"
    provenance: Optional[ProvenanceRecord] = None

    @field_validator("transaction_id", mode="before")
    @classmethod
    def sanitize_id(cls, v: Any) -> str:
        return str(v).strip()

    @field_validator("credited_amount", mode="before")
    @classmethod
    def sanitize_amount(cls, v: Any) -> float:
        dec = safe_decimal(v)
        if dec is None:
            raise ValueError(f"Invalid credited amount: {v}")
        return float(safe_numeric(dec))


class CanonicalAdjustmentRecord(BaseModel):
    """Canonical adjustment / dispute record."""
    transaction_id: str
    adjustment_type: str
    amount: float
    reason: str
    date: str = "2026-08-20"
    reference: Optional[str] = None
    provenance: Optional[ProvenanceRecord] = None

    @field_validator("transaction_id", mode="before")
    @classmethod
    def sanitize_id(cls, v: Any) -> str:
        return str(v).strip()

    @field_validator("amount", mode="before")
    @classmethod
    def sanitize_amount(cls, v: Any) -> float:
        dec = safe_decimal(v)
        if dec is None:
            raise ValueError(f"Invalid adjustment amount: {v}")
        return float(safe_numeric(dec))


class ColumnMappingConfig(BaseModel):
    """Configuration mapping raw source CSV columns to canonical fields."""
    transaction_id: str
    amount: str
    date: Optional[str] = None
    status: Optional[str] = None
    merchant_id: Optional[str] = None
    additional_mappings: Dict[str, str] = Field(default_factory=dict)


class DatasetManifest(BaseModel):
    """Manifest describing a normalized dataset."""
    source_dataset: str
    source_type: str = "synthetic_public_dataset"
    source_file: str
    normalizer: str
    normalization_timestamp: str
    record_count: int
    column_mapping: Dict[str, str] = Field(default_factory=dict)
    provenance_notes: str = ""
    is_derived_test_data: bool = False
    derived_records_count: Optional[int] = None


class NormalizedDataset(BaseModel):
    """In-memory representation of a complete normalized dataset."""
    source_dataset: str
    source_type: str
    manifest: DatasetManifest
    payments: List[CanonicalPaymentRecord] = Field(default_factory=list)
    ledger: List[CanonicalLedgerRecord] = Field(default_factory=list)
    bank: List[CanonicalBankRecord] = Field(default_factory=list)
    adjustments: List[CanonicalAdjustmentRecord] = Field(default_factory=list)
    provenance: List[ProvenanceRecord] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


class NormalizationPreviewResponse(BaseModel):
    """API response model for dataset normalization preview."""
    normalizer: str
    source_dataset: str
    source_type: str
    source_filename: str
    total_source_rows: int
    normalized_payments_count: int
    derived_ledger_count: int
    derived_bank_count: int
    derived_adjustments_count: int
    sample_source_rows: List[Dict[str, Any]]
    sample_normalized_rows: List[Dict[str, Any]]
    column_mapping: Dict[str, str]
    warnings: List[str]
    errors: List[str]
    valid: bool
