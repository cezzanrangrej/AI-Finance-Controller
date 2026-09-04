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

    # LLM Provider Metadata
    llm_provider: Optional[str] = "demo"
    llm_mode: Optional[str] = "DEMO"
    llm_model: Optional[str] = "demo"
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    llm_cases_selected: Optional[int] = None
    llm_cases_completed: Optional[int] = None
    llm_cases_not_evaluated: Optional[int] = None
    # True when a role fell back to the offline demo engine despite a real
    # provider being configured. Surfaced so the UI can label such a run.
    llm_degraded: Optional[bool] = False
    llm_degraded_reason: Optional[str] = None
    evaluation_group_id: Optional[str] = None
    evaluation_run_number: Optional[int] = None
    evaluation_runs_total: Optional[int] = None

    # Evaluation metrics. None means "not measured" -- render as N/A.
    phase1_accuracy: Optional[float] = None
    phase2_accuracy: Optional[float] = None
    auto_resolution_precision: Optional[float] = None
    auto_resolution_recall: Optional[float] = None
    ground_truth_accuracy: Optional[float] = None
    has_ground_truth: bool = False
    phase1_detection_precision: Optional[float] = None
    phase1_detection_recall: Optional[float] = None
    phase1_false_positives: Optional[int] = None
    phase1_false_negatives: Optional[int] = None

    # Honest exception accounting
    not_evaluated: int = 0
    degraded_cases: int = 0

    # Phase-separated timing
    phase1_time_sec: Optional[float] = None
    phase2_time_sec: Optional[float] = None
    end_to_end_time_sec: Optional[float] = None
    total_processing_time_sec: Optional[float] = None
    records_per_second: Optional[float] = None
    phase1_records_per_second: Optional[float] = None
    phase2_cases_per_second: Optional[float] = None
    average_case_latency_sec: Optional[float] = None
    tokens_per_case: Optional[float] = None


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

    # LLM Provider Metadata
    llm_provider: Optional[str] = "demo"
    llm_mode: Optional[str] = "DEMO"
    llm_model: Optional[str] = "demo"
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    llm_cases_selected: Optional[int] = None
    llm_cases_completed: Optional[int] = None
    llm_cases_not_evaluated: Optional[int] = None
    # True when a role fell back to the offline demo engine despite a real
    # provider being configured. Surfaced so the UI can label such a run.
    llm_degraded: Optional[bool] = False
    llm_degraded_reason: Optional[str] = None
    evaluation_group_id: Optional[str] = None
    evaluation_run_number: Optional[int] = None
    evaluation_runs_total: Optional[int] = None

    # Evaluation metrics. None means "not measured" -- render as N/A, never 100%.
    phase1_accuracy: Optional[float] = None
    phase2_accuracy: Optional[float] = None
    auto_resolution_precision: Optional[float] = None
    auto_resolution_recall: Optional[float] = None
    ground_truth_accuracy: Optional[float] = None
    has_ground_truth: bool = False
    phase1_detection_precision: Optional[float] = None
    phase1_detection_recall: Optional[float] = None
    phase1_false_positives: Optional[int] = None
    phase1_false_negatives: Optional[int] = None

    # Honest exception accounting
    not_evaluated: int = 0
    degraded_cases: int = 0

    # Phase-separated timing & throughput
    phase1_time_sec: Optional[float] = None
    phase2_time_sec: Optional[float] = None
    end_to_end_time_sec: Optional[float] = None
    total_processing_time_sec: Optional[float] = None
    records_per_second: Optional[float] = None
    phase1_records_per_second: Optional[float] = None
    phase2_cases_per_second: Optional[float] = None
    average_time_per_record_sec: Optional[float] = None
    average_case_latency_sec: Optional[float] = None
    tokens_per_case: Optional[float] = None

    exception_breakdown: Dict[str, int]


class EvaluationRunRequest(BaseModel):
    """Request model for initiating a multi-run evaluation."""
    provider: Optional[str] = "demo"
    cases_per_run: Optional[int] = 5
    runs: Optional[int] = 1
    batch_size: Optional[int] = 5
    parallel_batches: Optional[int] = None
    model: Optional[str] = None


class PerRunSummary(BaseModel):
    """Summary of a single run within an evaluation group."""
    run_number: int
    run_id: str
    cases_selected: int
    cases_completed: int
    cases_not_evaluated: int
    auto_resolved: int
    human_review: int
    decision_accuracy: Optional[float] = None
    auto_resolution_precision: Optional[float] = None
    auto_resolution_recall: Optional[float] = None
    phase2_time_sec: float
    total_tokens: Optional[int] = None


class EvaluationGroupSummaryResponse(BaseModel):
    """Aggregate response model for multi-run evaluations."""
    evaluation_group_id: str
    provider: str
    model: str
    runs: int
    cases_per_run: int
    total_selected: int
    completed: int
    not_evaluated: int
    auto_resolved: int
    human_review: int
    aggregate_accuracy: Optional[float] = None
    aggregate_precision: Optional[float] = None
    aggregate_recall: Optional[float] = None
    human_review_rate: float
    not_evaluated_rate: float
    total_processing_time_sec: float
    average_case_latency_sec: float
    total_tokens: int
    average_tokens_per_case: int
    per_run_summaries: List[PerRunSummary]



from typing import Any, Dict, List, Optional, Union


class ExceptionItemResponse(BaseModel):
    """Exception item response model."""
    transaction_id: str
    exception_type: str
    status: str
    decision: str
    resolution_type: Optional[str] = "NONE"
    payment_amount: Optional[Union[float, int]] = None
    gross_amount: Optional[Union[float, int]] = None
    fee: Optional[Union[float, int]] = None
    expected_amount: Optional[Union[float, int]] = None
    actual_amount: Optional[Union[float, int]] = None
    difference: Optional[Union[float, int]] = None
    reason: str
    recommended_action: str
    confidence: float
    evidence: List[str]


class SourceProvenance(BaseModel):
    """Provenance tracking for a transaction source record."""
    source_file: Optional[str] = None
    source_row: Optional[int] = None
    raw_credited_amount: Optional[str] = None
    parsed_credited_amount: Optional[Union[float, int, str]] = None
    raw_amount: Optional[str] = None
    parsed_amount: Optional[Union[float, int, str]] = None


class TransactionDetailResponse(BaseModel):
    """Single transaction detailed view model."""
    transaction_id: str
    status: str
    exception_type: Optional[str] = None
    payment_amount: Optional[Union[float, int]] = None
    gross_amount: Optional[Union[float, int]] = None
    fee: Optional[Union[float, int]] = None
    expected_net_amount: Optional[Union[float, int]] = None
    bank_amount: Optional[Union[float, int]] = None
    difference: Optional[Union[float, int]] = None
    adjustments: Optional[List[Dict[str, Any]]] = None
    agent_investigation: Optional[Dict[str, Any]] = None
    source_provenance: Optional[Dict[str, Any]] = None


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


class DataIntegrityRecord(BaseModel):
    """Per-transaction data integrity verification record."""
    transaction_id: str
    source_file: Optional[str] = None
    source_row: Optional[int] = None
    raw_bank_amount: Optional[str] = None
    parsed_bank_amount: Optional[Union[float, int]] = None
    normalized_bank_amount: Optional[Union[float, int]] = None
    reconciliation_bank_amount: Optional[Union[float, int]] = None
    api_bank_amount: Optional[Union[float, int]] = None
    integrity_passed: bool
    details: Optional[str] = None


class DataIntegrityDiagnosticResponse(BaseModel):
    """Development-only data integrity verification report."""
    run_id: str
    environment: str
    total_records: int
    all_passed: bool
    discrepancy_count: int
    records: List[DataIntegrityRecord]

