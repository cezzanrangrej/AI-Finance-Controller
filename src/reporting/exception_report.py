"""
Exception Report Generator for AI Finance Controller.

Extracts reconciliation runs, transactions, adjustments, and agent investigations
from SQLite and formats structured executive exception reports (JSON & Markdown).
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from src.db.models import AdjustmentModel, AgentInvestigationModel, RunModel, TransactionResultModel


@dataclass
class ExceptionReport:
    """Structured data container for a reconciliation exception report."""

    run_id: str
    created_at: str
    summary: Dict[str, Any]
    exceptions_breakdown: Dict[str, int]
    auto_resolved_cases: List[Dict[str, Any]] = field(default_factory=list)
    human_review_cases: List[Dict[str, Any]] = field(default_factory=list)
    # Cases the agent never managed to assess (infrastructure failure). Kept
    # apart from human_review_cases: an escalation is a judgment, a
    # NOT_EVALUATED case is the absence of one. Merging them would inflate the
    # apparent triage queue quality and hide the agent's real failure count.
    not_evaluated_cases: List[Dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        """Returns the report data as a serializable dictionary."""
        return asdict(self)


def build_exception_report(db: Session, run_id: str) -> ExceptionReport:
    """
    Builds a comprehensive ExceptionReport object for a given run from the database.

    Args:
        db: Active SQLAlchemy database session.
        run_id: Unique execution run ID.

    Returns:
        ExceptionReport dataclass instance.

    Raises:
        ValueError: If run_id is not found in the database.
    """
    run = db.query(RunModel).filter(RunModel.id == run_id).first()
    if not run:
        raise ValueError(f"Run '{run_id}' not found.")

    # Query associated transactions, investigations, and adjustments
    transactions = db.query(TransactionResultModel).filter(TransactionResultModel.run_id == run_id).all()
    investigations = db.query(AgentInvestigationModel).filter(AgentInvestigationModel.run_id == run_id).all()
    adjustments = db.query(AdjustmentModel).filter(AdjustmentModel.run_id == run_id).all()

    # Index adjustments by transaction_id
    adj_by_txn: Dict[str, List[Dict[str, Any]]] = {}
    for adj in adjustments:
        adj_by_txn.setdefault(adj.transaction_id, []).append({
            "adjustment_type": adj.adjustment_type,
            "amount": adj.amount,
            "reason": adj.reason,
            "reference": adj.reference,
            "date": adj.date,
        })

    # Index transactions by transaction_id
    txn_map = {t.transaction_id: t for t in transactions}

    # Exception counts breakdown
    breakdown: Dict[str, int] = {}
    for t in transactions:
        if t.status == "EXCEPTION" and t.exception_type:
            breakdown[t.exception_type] = breakdown.get(t.exception_type, 0) + 1

    # Classify investigations into three buckets, not two.
    auto_resolved_cases = []
    human_review_cases = []
    not_evaluated_cases = []

    for inv in investigations:
        t_id = inv.transaction_id
        txn = txn_map.get(t_id)

        evidence = []
        if inv.evidence_json:
            try:
                evidence = json.loads(inv.evidence_json)
            except Exception:
                evidence = [inv.evidence_json]

        tools_used = []
        if inv.tools_used_json:
            try:
                tools_used = json.loads(inv.tools_used_json)
            except Exception:
                tools_used = [inv.tools_used_json]

        case_data = {
            "transaction_id": t_id,
            "initial_exception": inv.initial_exception,
            "decision": inv.decision,
            "resolution_type": inv.resolution_type or "NONE",
            "resolved_difference": inv.resolved_difference,
            "expected_net_amount": txn.expected_net_amount if txn else None,
            "bank_amount": txn.bank_amount if txn else None,
            "difference": txn.difference if txn else None,
            "reason": inv.reason,
            "recommended_action": inv.recommended_action,
            "confidence": inv.confidence,
            "evidence": evidence,
            "tools_used": tools_used,
            "adjustments": adj_by_txn.get(t_id, []),
        }

        if inv.decision == "AUTO_RESOLVED":
            auto_resolved_cases.append(case_data)
        elif inv.decision == "NOT_EVALUATED":
            not_evaluated_cases.append(case_data)
        else:
            human_review_cases.append(case_data)

    created_iso = run.created_at.isoformat() if isinstance(run.created_at, datetime) else str(run.created_at)

    summary_data = {
        "run_id": run.id,
        "total_records": run.total_records,
        "initial_reconciled": run.initial_reconciled,
        "initial_exceptions": run.initial_exceptions,
        "ai_auto_resolved": run.ai_auto_resolved,
        "human_review": run.human_review,
        "final_resolved": run.final_resolved,
        "final_unresolved": run.final_unresolved,
        "initial_match_rate": run.initial_match_rate,
        "agent_resolution_rate": run.agent_resolution_rate,
        "final_resolution_rate": run.final_resolution_rate,
        # Third bucket, reported explicitly rather than folded into human_review.
        "not_evaluated": getattr(run, "not_evaluated", 0) or 0,
        "degraded_cases": getattr(run, "degraded_cases", 0) or 0,
        # Accuracy is only present when a ground-truth file was supplied. These
        # stay None otherwise so the report prints "not measured" instead of a
        # figure no reader could check.
        "has_ground_truth": bool(getattr(run, "has_ground_truth", False)),
        "phase1_accuracy": run.phase1_accuracy,
        "phase2_accuracy": run.phase2_accuracy,
        "auto_resolution_precision": run.auto_resolution_precision,
        "auto_resolution_recall": run.auto_resolution_recall,
        "phase1_detection_precision": getattr(run, "phase1_detection_precision", None),
        "phase1_detection_recall": getattr(run, "phase1_detection_recall", None),
        "phase1_false_positives": getattr(run, "phase1_false_positives", None),
        "phase1_false_negatives": getattr(run, "phase1_false_negatives", None),
        "llm_provider": run.llm_provider,
        "llm_mode": run.llm_mode,
        "llm_model": run.llm_model,
        "total_tokens": run.total_tokens,
        "phase1_time_sec": run.phase1_time_sec,
        "phase2_time_sec": run.phase2_time_sec,
        "end_to_end_time_sec": run.end_to_end_time_sec,
        "total_processing_time_sec": run.total_processing_time_sec,
        "records_per_second": run.records_per_second,
    }

    return ExceptionReport(
        run_id=run.id,
        created_at=created_iso,
        summary=summary_data,
        exceptions_breakdown=breakdown,
        auto_resolved_cases=auto_resolved_cases,
        human_review_cases=human_review_cases,
        not_evaluated_cases=not_evaluated_cases,
    )


def _rate(value: Any, suffix: str = "%") -> str:
    """
    Renders a rate, or "not measured" when it is None.

    A missing metric is never printed as a number. `0.0` is a real measurement
    and prints as 0.0%, which is why this checks for None rather than falsiness.
    """
    if value is None:
        return "*not measured*"
    return f"{float(value):.1f}{suffix}"


def format_as_markdown(report: ExceptionReport) -> str:
    """
    Formats an ExceptionReport into a clean, executive-ready Markdown document.
    """
    s = report.summary
    lines: List[str] = []

    lines.append(f"# Financial Reconciliation Exception Report")
    lines.append(f"**Run ID**: `{report.run_id}` | **Date**: `{report.created_at}`")
    lines.append(f"**Provider**: `{s.get('llm_provider', 'N/A')}` | **Model**: `{s.get('llm_model', 'N/A')}`\n")

    lines.append("## 1. Executive Summary")
    lines.append("| Metric | Value |")
    lines.append("| :--- | :--- |")
    lines.append(f"| **Total Processed Transactions** | **{s.get('total_records', 0):,}** |")
    lines.append(f"| **Phase 1 Deterministic Matches** | {s.get('initial_reconciled', 0):,} ({_rate(s.get('initial_match_rate'))}) |")
    lines.append(f"| **Phase 1 Exceptions Detected** | {s.get('initial_exceptions', 0):,} |")
    lines.append(f"| **AI Auto-Resolved Discrepancies** | {s.get('ai_auto_resolved', 0):,} ({_rate(s.get('agent_resolution_rate'))} of exceptions) |")
    lines.append(f"| **Escalated for Human Review** | **{s.get('human_review', 0):,}** |")
    not_evaluated = s.get("not_evaluated", 0) or 0
    lines.append(f"| **Not Evaluated (agent failure)** | **{not_evaluated:,}** |")
    lines.append(f"| **Overall Final Resolution Rate** | **{_rate(s.get('final_resolution_rate'))}** |")
    if s.get("total_processing_time_sec"):
        lines.append(f"| **Total Processing Time** | {s.get('total_processing_time_sec'):.3f}s ({s.get('records_per_second') or 0:.1f} rec/s end-to-end) |")
    if s.get("total_tokens"):
        lines.append(f"| **Total Token Usage** | {s.get('total_tokens'):,} tokens |")
    lines.append("")

    lines.append("## 2. Measured Accuracy")
    if s.get("has_ground_truth"):
        lines.append("Scored against the supplied ground-truth file.\n")
        lines.append("| Metric | Value |")
        lines.append("| :--- | :--- |")
        lines.append(f"| Phase 1 detection accuracy | {_rate(s.get('phase1_accuracy'))} |")
        lines.append(f"| Phase 1 detection precision | {_rate(s.get('phase1_detection_precision'))} |")
        lines.append(f"| Phase 1 detection recall | {_rate(s.get('phase1_detection_recall'))} |")
        fp = s.get("phase1_false_positives")
        fn = s.get("phase1_false_negatives")
        lines.append(f"| Phase 1 false positives / false negatives | {fp if fp is not None else '—'} / {fn if fn is not None else '—'} |")
        lines.append(f"| Phase 2 decision accuracy | {_rate(s.get('phase2_accuracy'))} |")
        lines.append(f"| Auto-resolution precision | {_rate(s.get('auto_resolution_precision'))} |")
        lines.append(f"| Auto-resolution recall | {_rate(s.get('auto_resolution_recall'))} |")
        lines.append("")
        if not_evaluated:
            lines.append(
                f"> {not_evaluated} case(s) were never assessed and are excluded from the "
                "accuracy denominators above. They are listed in full below."
            )
            lines.append("")
    else:
        lines.append(
            "*No ground-truth file was supplied for this run, so accuracy, precision "
            "and recall are **not measured**. The throughput and resolution counts "
            "above are still exact; the accuracy of those resolutions is unverified.*"
        )
        lines.append("")

    lines.append("## 3. Exception Breakdown by Category")
    if report.exceptions_breakdown:
        lines.append("| Exception Type | Count | Percentage |")
        lines.append("| :--- | :---: | :---: |")
        total_exc = sum(report.exceptions_breakdown.values()) or 1
        for exc_type, count in sorted(report.exceptions_breakdown.items(), key=lambda x: x[1], reverse=True):
            pct = (count / total_exc) * 100
            lines.append(f"| `{exc_type}` | {count} | {pct:.1f}% |")
    else:
        lines.append("*No exceptions detected in this reconciliation run.*")
    lines.append("")

    lines.append("## 4. Auto-Resolved Discrepancies (Proven by Adjustments)")
    if report.auto_resolved_cases:
        lines.append(f"Total: **{len(report.auto_resolved_cases)} cases** verified mathematically.\n")
        lines.append("| Transaction ID | Exception Type |  | Difference | Reason |")
        lines.append("| :--- | :--- | :--- | :---: | :--- |")
        for c in report.auto_resolved_cases:
            diff_str = f"₹{abs(c['difference']):,.2f}" if c.get("difference") is not None else "N/A"
            lines.append(f"| `{c['transaction_id']}` | `{c['initial_exception']}` | `{c['resolution_type']}` | {diff_str} | {c['reason']} |")
        lines.append("")
    else:
        lines.append("*No cases were automatically resolved in this run.*")
        lines.append("")

    lines.append("## 5. Human Review Escalations (Triage Queue)")
    if report.human_review_cases:
        lines.append(f"Total: **{len(report.human_review_cases)} cases** requiring finance operations inspection.\n")
        for idx, c in enumerate(report.human_review_cases, 1):
            lines.append(f"### {idx}. Transaction `{c['transaction_id']}` — `{c['initial_exception']}`")
            lines.append(f"- **Discrepancy / Difference**: ₹{abs(c['difference'] or 0):,.2f} (Expected: ₹{c.get('expected_net_amount') or 0:,.2f} vs Bank: ₹{c.get('bank_amount') or 0:,.2f})")
            lines.append(f"- **Root Cause Analysis**: {c['reason']}")
            lines.append(f"- **Recommended Action**: **{c['recommended_action']}**")
            if c.get("evidence"):
                lines.append("- **Audit Evidence**:")
                for ev in c["evidence"]:
                    lines.append(f"  - {ev}")
            lines.append("")
    else:
        lines.append("*Zero human review escalations.*")
        lines.append("")

    lines.append("## 6. Cases Not Evaluated (Agent Could Not Assess)")
    if report.not_evaluated_cases:
        lines.append(
            f"Total: **{len(report.not_evaluated_cases)} cases** the agent failed to "
            "assess. These are declared here rather than counted as resolutions or as "
            "considered escalations, because no judgment was ever produced for them. "
            "They are excluded from the accuracy denominators in section 2 and counted "
            "as unresolved in section 1.\n"
        )
        lines.append("| Transaction ID | Exception Type | Failure |")
        lines.append("| :--- | :--- | :--- |")
        for c in report.not_evaluated_cases:
            lines.append(f"| `{c['transaction_id']}` | `{c['initial_exception']}` | {c['reason']} |")
        lines.append("")
    else:
        lines.append("*Every exception received a decision. No cases were left unassessed.*")
        lines.append("")

    lines.append("---")
    lines.append("*Report generated autonomously by the ReconPilot Audit Engine.*")
    return "\n".join(lines)
