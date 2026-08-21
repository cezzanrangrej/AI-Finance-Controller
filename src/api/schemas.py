"""
Pydantic API schemas for request and response validation.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class RunSummaryResponse(BaseModel):
    """Run summary response model."""
    run_id: str
    created_at: str
    total_records: int
    initial_reconciled: int
    initial_exceptions: int
    ai_auto_resolved: int
    human_review: int
    final_resolved: int
    final_unresolved: int
    initial_match_rate: float
    agent_resolution_rate: float
    final_resolution_rate: float

    # Evaluation metrics
    phase1_accuracy: Optional[float] = None
    phase2_accuracy: Optional[float] = None
    auto_resolution_precision: Optional[float] = None
    auto_resolution_recall: Optional[float] = None
    ground_truth_accuracy: Optional[float] = None

    # Phase-separated timing
    phase1_time_sec: Optional[float] = None
    phase2_time_sec: Optional[float] = None
    end_to_end_time_sec: Optional[float] = None
    total_processing_time_sec: Optional[float] = None
    records_per_second: Optional[float] = None


class MetricsResponse(BaseModel):
    """Metrics detail response model."""
    run_id: str
    total_records: int
    initial_reconciled: int
    initial_exceptions: int
    ai_auto_resolved: int
    human_review: int
    final_resolved: int
    final_unresolved: int
    initial_match_rate: float
    agent_resolution_rate: float
    final_resolution_rate: float

    # Evaluation metrics
    phase1_accuracy: Optional[float] = 100.0
    phase2_accuracy: Optional[float] = None
    auto_resolution_precision: Optional[float] = None
    auto_resolution_recall: Optional[float] = None
    ground_truth_accuracy: Optional[float] = None

    # Phase-separated timing & throughput
    phase1_time_sec: Optional[float] = None
    phase2_time_sec: Optional[float] = None
    end_to_end_time_sec: Optional[float] = None
    total_processing_time_sec: Optional[float] = None
    records_per_second: Optional[float] = None
    average_time_per_record_sec: Optional[float] = None

    exception_breakdown: Dict[str, int]


class ExceptionItemResponse(BaseModel):
    """Exception item response model."""
    transaction_id: str
    exception_type: str
    status: str
    decision: str
    resolution_type: Optional[str] = "NONE"
    payment_amount: Optional[int] = None
    gross_amount: Optional[int] = None
    fee: Optional[int] = None
    expected_amount: Optional[int] = None
    actual_amount: Optional[int] = None
    difference: Optional[int] = None
    reason: str
    recommended_action: str
    confidence: float
    evidence: List[str]


class TransactionDetailResponse(BaseModel):
    """Single transaction detailed view model."""
    transaction_id: str
    status: str
    exception_type: Optional[str] = None
    payment_amount: Optional[int] = None
    gross_amount: Optional[int] = None
    fee: Optional[int] = None
    expected_net_amount: Optional[int] = None
    bank_amount: Optional[int] = None
    difference: Optional[int] = None
    adjustments: Optional[List[Dict[str, Any]]] = None
    agent_investigation: Optional[Dict[str, Any]] = None


class AuditItemResponse(BaseModel):
    """Audit timeline item model."""
    transaction_id: str
    step: str
    status: str
    event: str
    evidence: Optional[List[str]] = None
    decision: Optional[str] = None
    reason: Optional[str] = None
    confidence: Optional[float] = None
