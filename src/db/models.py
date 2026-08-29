"""
SQLAlchemy ORM models for database persistence.
"""

from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
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

    # Evaluation metrics
    phase1_accuracy = Column(Float, nullable=True)
    phase2_accuracy = Column(Float, nullable=True)
    auto_resolution_precision = Column(Float, nullable=True)
    auto_resolution_recall = Column(Float, nullable=True)
    ground_truth_accuracy = Column(Float, nullable=True)

    # LLM Provider Metadata & Token Usage
    llm_provider = Column(String(20), nullable=True)
    llm_mode = Column(String(20), nullable=True)
    llm_model = Column(String(50), nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)
    llm_cases_selected = Column(Integer, nullable=True)
    llm_cases_completed = Column(Integer, nullable=True)
    llm_cases_not_evaluated = Column(Integer, nullable=True)

    # Multi-run Evaluation Group Metadata
    evaluation_group_id = Column(String(50), nullable=True, index=True)
    evaluation_run_number = Column(Integer, nullable=True)
    evaluation_runs_total = Column(Integer, nullable=True)


    # Phase-separated timing & throughput metrics
    phase1_time_sec = Column(Float, nullable=True)
    phase2_time_sec = Column(Float, nullable=True)
    end_to_end_time_sec = Column(Float, nullable=True)
    total_processing_time_sec = Column(Float, nullable=True)
    records_per_second = Column(Float, nullable=True)
    average_time_per_record_sec = Column(Float, nullable=True)

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
    """Ground truth repository for evaluation."""
    __tablename__ = "ground_truth"

    transaction_id = Column(String(50), primary_key=True, index=True)
    expected_status = Column(String(20), nullable=False)
    expected_exception = Column(String(50), nullable=True)
    expected_phase2_decision = Column(String(20), nullable=True)
