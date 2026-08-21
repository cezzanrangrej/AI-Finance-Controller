"""
Pydantic schemas for structured agent I/O, audit logs, and evaluation metrics.
"""

from datetime import datetime, timezone
from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator


class AgentDecision(BaseModel):
    """
    Structured output produced by the AI agent for every investigated exception.

    decision:
        AUTO_RESOLVED  — agent found deterministic evidence explaining the discrepancy
        HUMAN_REVIEW   — evidence is insufficient; a human must review
    """

    transaction_id: str
    decision: Literal["AUTO_RESOLVED", "HUMAN_REVIEW"]
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


class InvestigationLog(BaseModel):
    """Full audit record for a single exception investigation."""

    transaction_id: str
    initial_exception: str
    tools_used: List[str]
    evidence: List[str]
    decision: Literal["AUTO_RESOLVED", "HUMAN_REVIEW"]
    resolution_type: Optional[str] = "NONE"
    resolved_difference: Optional[float] = None
    reason: str
    confidence: float
    recommended_action: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tool_call_count: int = 0


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
