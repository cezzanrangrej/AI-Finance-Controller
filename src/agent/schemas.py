"""
Pydantic schemas for structured agent I/O, audit logs, and evaluation metrics.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator


class AgentDecision(BaseModel):
    """
    Structured output produced by the AI agent for every investigated exception.

    decision:
        AUTO_RESOLVED  — agent found deterministic evidence explaining the discrepancy
        HUMAN_REVIEW   — evidence is insufficient; a human must review
        NOT_EVALUATED  — provider API error or unselected in subset evaluation
    """

    transaction_id: str
    decision: Literal["AUTO_RESOLVED", "HUMAN_REVIEW", "NOT_EVALUATED"]
    exception_type: str
    resolution_type: Optional[Literal["NONE", "ADJUSTMENT_EXPLAINED", "OTHER_EVIDENCE"]] = "NONE"
    resolved_difference: Optional[float] = None
    reason: str
    evidence: List[str]
    confidence: float = Field(..., ge=0.0, le=1.0)
    recommended_action: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("confidence")
    @classmethod
    def confidence_must_be_in_range(cls, v: float) -> float:
        """Enforce confidence is a float in [0, 1]."""
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"confidence must be between 0.0 and 1.0, got {v}")
        return v

    @field_validator("evidence")
    @classmethod
    def evidence_must_not_be_empty(cls, v: List[str]) -> List[str]:
        """Require at least one evidence item."""
        if not v:
            raise ValueError("evidence list must contain at least one item")
        return v


class ToolCallTrace(BaseModel):
    """Non-sensitive audit trace of a single tool execution during investigation."""

    transaction_id: str
    tool_name: str
    tool_arguments: Dict[str, Any]
    tool_result_summary: str
    tool_call_index: int
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    early_stop_reason: Optional[str] = None
    evidence_sufficient: Optional[bool] = None
    duplicate_call_prevented: Optional[bool] = None
    deterministic_resolution: Optional[str] = None



class InvestigationProposal(BaseModel):
    """
    Structured proposal produced by the Investigator Agent.
    Contains gathered evidence and a recommended resolution without chain-of-thought.
    """
    transaction_id: str
    exception_type: str
    evidence: List[str] = Field(default_factory=list)
    proposed_resolution: Literal["AUTO_RESOLVED", "HUMAN_REVIEW"]
    resolution_type: Optional[Literal["NONE", "ADJUSTMENT_EXPLAINED", "OTHER_EVIDENCE"]] = "NONE"
    resolved_difference: Optional[float] = None
    confidence: float = Field(..., ge=0.0, le=1.0)
    unresolved_questions: List[str] = Field(default_factory=list)
    tool_history: List[str] = Field(default_factory=list)
    reason: Optional[str] = None
    recommended_action: Optional[str] = None

    @field_validator("confidence")
    @classmethod
    def confidence_must_be_in_range(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"confidence must be between 0.0 and 1.0, got {v}")
        return v


class VerificationResult(BaseModel):
    """
    Structured verification produced by the Verifier Agent.
    Independently validates whether evidence supports the proposed resolution.
    """
    transaction_id: str
    verified: bool
    decision: Literal["AUTO_RESOLVED", "HUMAN_REVIEW"]
    reason: str
    evidence_references: List[str] = Field(default_factory=list)
    contradictions: List[str] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0)

    @field_validator("confidence")
    @classmethod
    def confidence_must_be_in_range(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"confidence must be between 0.0 and 1.0, got {v}")
        return v


class InvestigationLog(BaseModel):
    """Full audit record for a single exception investigation."""

    transaction_id: str
    initial_exception: str
    tools_used: List[str]
    evidence: List[str]
    decision: Literal["AUTO_RESOLVED", "HUMAN_REVIEW", "NOT_EVALUATED"]
    resolution_type: Optional[str] = "NONE"
    resolved_difference: Optional[float] = None
    reason: str
    confidence: float
    recommended_action: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tool_call_count: int = 0
    tool_traces: List[ToolCallTrace] = Field(default_factory=list)

    # Multi-Agent Audit Fields
    agent_mode: Optional[str] = "INDIVIDUAL"
    resolution_source: Optional[str] = None  # e.g., "DETERMINISTIC_EVIDENCE", "MULTI_AGENT_CONSENSUS", "HUMAN_ESCALATION"
    investigator_proposal: Optional[Dict[str, Any]] = None
    verification_result: Optional[Dict[str, Any]] = None
    disagreement_detected: Optional[bool] = False
    investigator_calls: int = 0
    verifier_calls: int = 0
    model_interactions: int = 1



class EvaluationMetrics(BaseModel):
    """Ground-truth evaluation metrics for Phase 1 & Phase 2 accuracy."""

    phase1_accuracy: float
    phase2_decision_accuracy: float
    auto_resolution_precision: float
    auto_resolution_recall: float

    # Raw counts
    agent_total_decisions: int
    agent_correct_decisions: int
    auto_resolved_correct: int
    auto_resolved_total: int
    human_review_correct: int
    human_review_total: int
    ground_truth_auto_resolvable: int

    # Category breakdown
    category_accuracy: Dict[str, Dict[str, int]]

    # Subset evaluation fields (optional)
    cases_selected: Optional[int] = None
    cases_completed: Optional[int] = None
    cases_not_evaluated: Optional[int] = None
    is_subset_evaluation: bool = False


class BatchInvestigationCase(BaseModel):
    """Prefetched deterministic evidence for a single exception within a batch."""
    transaction_id: str
    initial_exception: str
    payment: Optional[Dict[str, Any]] = None
    ledger: Optional[Dict[str, Any]] = None
    bank_records: List[Dict[str, Any]] = Field(default_factory=list)
    adjustments: List[Dict[str, Any]] = Field(default_factory=list)
    duplicate_check: Optional[Dict[str, Any]] = None
    expected_settlement: Optional[Dict[str, Any]] = None
    adjusted_expected_settlement: Optional[Dict[str, Any]] = None


class BatchAgentResponse(BaseModel):
    """Structured response container for multiple transaction decisions."""
    decisions: List[AgentDecision]


class BatchInvestigationLog(BaseModel):
    """Audit log for a batch investigation interaction."""
    batch_id: str
    batch_size: int
    transaction_ids: List[str]
    provider: str
    model: str
    request_start: datetime
    request_end: datetime
    processing_time_sec: float
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    llm_interactions: int = 1
    fallback_count: int = 0
    fallback_transaction_ids: List[str] = Field(default_factory=list)
    decisions: List[AgentDecision] = Field(default_factory=list)
    partition_strategy: str = "balanced_exception_type"
    exception_type_counts: Dict[str, int] = Field(default_factory=dict)
    case_count: Optional[int] = None


class BatchStatus(BaseModel):
    """Per-batch execution lifecycle status, timing, and error tracking."""
    batch_id: str
    batch_number: int
    transaction_ids: List[str]
    status: Literal["PENDING", "RUNNING", "COMPLETED", "FAILED", "NOT_EVALUATED"]
    batch_started_at: Optional[datetime] = None
    batch_completed_at: Optional[datetime] = None
    batch_latency_sec: Optional[float] = None
    batch_error: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    partition_strategy: str = "balanced_exception_type"
    case_count: Optional[int] = None
    exception_type_counts: Dict[str, int] = Field(default_factory=dict)


class BatchInvestigatorResponse(BaseModel):
    """Structured response container for multiple transaction investigation proposals."""
    proposals: List[InvestigationProposal]


class BatchVerifierResponse(BaseModel):
    """Structured response container for multiple transaction verification results."""
    verifications: List[VerificationResult]
