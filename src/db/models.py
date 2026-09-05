"""
SQLAlchemy ORM models for database persistence.
"""

from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from src.db.database import Base


class RunModel(Base):
    """Represents a single batch reconciliation execution run."""
    __tablename__ = "runs"

    id = Column(String(50), primary_key=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    total_records = Column(Integer, nullable=False)
    initial_reconciled = Column(Integer, nullable=False)
    initial_exceptions = Column(Integer, nullable=False)
    ai_auto_resolved = Column(Integer, nullable=False)
    human_review = Column(Integer, nullable=False)
    final_resolved = Column(Integer, nullable=False)
    final_unresolved = Column(Integer, nullable=False)
    initial_match_rate = Column(Float, nullable=False)
    agent_resolution_rate = Column(Float, nullable=False)
    final_resolution_rate = Column(Float, nullable=False)

    # Evaluation metrics. All nullable: NULL means "not measured" (no ground
    # truth supplied for this run) and must render as N/A, never as 100%.
    phase1_accuracy = Column(Float, nullable=True)
    phase2_accuracy = Column(Float, nullable=True)
    auto_resolution_precision = Column(Float, nullable=True)
    auto_resolution_recall = Column(Float, nullable=True)
    ground_truth_accuracy = Column(Float, nullable=True)
    has_ground_truth = Column(Boolean, nullable=False, default=False)

    # Phase 1 detection quality vs the ground-truth is_phase1_exception flag
    phase1_detection_precision = Column(Float, nullable=True)
    phase1_detection_recall = Column(Float, nullable=True)
    phase1_false_positives = Column(Integer, nullable=True)
    phase1_false_negatives = Column(Integer, nullable=True)

    # Honest exception accounting: cases the agent could not assess at all,
    # kept separate from cases it deliberately escalated to a human.
    not_evaluated = Column(Integer, nullable=False, default=0)
    degraded_cases = Column(Integer, nullable=False, default=0)

    # LLM Provider Metadata & Token Usage
    llm_provider = Column(String(20), nullable=True)
    llm_mode = Column(String(20), nullable=True)
    llm_model = Column(String(50), nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)
    pre_resolved_count = Column(Integer, nullable=True, default=0)
    llm_cases_selected = Column(Integer, nullable=True)
    llm_cases_completed = Column(Integer, nullable=True)
    llm_cases_not_evaluated = Column(Integer, nullable=True)

    # True when a role silently fell back to the offline demo engine because its
    # provider credentials were unusable. Persisted so a run's decisions can
    # never be mistaken for real-model output after the fact.
    llm_degraded = Column(Boolean, nullable=False, default=False)
    llm_degraded_reason = Column(String(500), nullable=True)

    # Multi-run Evaluation Group Metadata
    evaluation_group_id = Column(String(50), nullable=True, index=True)
    evaluation_run_number = Column(Integer, nullable=True)
    evaluation_runs_total = Column(Integer, nullable=True)


    # Phase-separated timing & throughput metrics
    phase1_time_sec = Column(Float, nullable=True)
    phase2_time_sec = Column(Float, nullable=True)
    end_to_end_time_sec = Column(Float, nullable=True)
    total_processing_time_sec = Column(Float, nullable=True)
    # records_per_second is the END-TO-END rate over all records. The
    # phase-specific rates are stored separately so neither can be mistaken
    # for the other.
    records_per_second = Column(Float, nullable=True)
    phase1_records_per_second = Column(Float, nullable=True)
    phase2_cases_per_second = Column(Float, nullable=True)
    average_time_per_record_sec = Column(Float, nullable=True)
    average_case_latency_sec = Column(Float, nullable=True)
    tokens_per_case = Column(Float, nullable=True)

    transactions = relationship("TransactionResultModel", back_populates="run", cascade="all, delete-orphan")
    investigations = relationship("AgentInvestigationModel", back_populates="run", cascade="all, delete-orphan")
    adjustments = relationship("AdjustmentModel", back_populates="run", cascade="all, delete-orphan")


class TransactionResultModel(Base):
    """Stores Phase 1 reconciliation results for a transaction within a run."""
    __tablename__ = "transaction_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(50), ForeignKey("runs.id"), nullable=False, index=True)
    transaction_id = Column(String(50), nullable=False, index=True)
    status = Column(String(20), nullable=False)
    exception_type = Column(String(50), nullable=True)
    payment_amount = Column(Float, nullable=True)
    gross_amount = Column(Float, nullable=True)
    fee = Column(Float, nullable=True)
    expected_net_amount = Column(Float, nullable=True)
    bank_amount = Column(Float, nullable=True)
    difference = Column(Float, nullable=True)
    source_provenance_json = Column(Text, nullable=True)

    run = relationship("RunModel", back_populates="transactions")


class AdjustmentModel(Base):
    """Stores source adjustment records for a transaction within a run."""
    __tablename__ = "adjustments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(50), ForeignKey("runs.id"), nullable=False, index=True)
    transaction_id = Column(String(50), nullable=False, index=True)
    adjustment_type = Column(String(50), nullable=False)
    amount = Column(Float, nullable=False)
    reason = Column(Text, nullable=False)
    date = Column(String(20), nullable=True)
    reference = Column(String(50), nullable=True)

    run = relationship("RunModel", back_populates="adjustments")


class AgentInvestigationModel(Base):
    """Stores Phase 2 agent investigation decisions, audit evidence, and recommendations."""
    __tablename__ = "agent_investigations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(50), ForeignKey("runs.id"), nullable=False, index=True)
    transaction_id = Column(String(50), nullable=False, index=True)
    initial_exception = Column(String(50), nullable=False)
    decision = Column(String(20), nullable=False)
    resolution_type = Column(String(50), nullable=True)
    resolved_difference = Column(Float, nullable=True)
    reason = Column(Text, nullable=False)
    recommended_action = Column(Text, nullable=False)
    confidence = Column(Float, nullable=False)
    evidence_json = Column(Text, nullable=False)
    tools_used_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    run = relationship("RunModel", back_populates="investigations")


class GroundTruthModel(Base):
    """
    Ground truth repository for evaluation. **Currently unused.**

    Nothing reads or writes this table: ground truth reaches the evaluator as
    in-memory rows, either from ``generator.generate()`` or from the uploaded
    ``ground_truth`` CSV. The table is retained only so existing databases keep
    their schema.

    Do not wire it up as declared. ``transaction_id`` is the whole primary key,
    with no ``run_id``, so two runs that both contain TXN001 -- the normal case,
    since the synthetic generator reuses ids -- would collide and silently
    overwrite each other's expected decisions. A ``run_id`` column belongs in the
    key before this is populated.
    """
    __tablename__ = "ground_truth"

    transaction_id = Column(String(50), primary_key=True, index=True)
    expected_status = Column(String(20), nullable=False)
    expected_exception = Column(String(50), nullable=True)
    expected_phase2_decision = Column(String(20), nullable=True)
