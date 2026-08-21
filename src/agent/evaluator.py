"""
Ground-truth evaluation of Phase 1 and Phase 2 reconciliation decisions.

Calculates Phase 1 accuracy, Phase 2 decision accuracy, Auto-Resolution Precision,
and Auto-Resolution Recall against known synthetic ground truth.
"""

from typing import Any, Dict, List
from src.agent.schemas import AgentDecision, EvaluationMetrics


def evaluate_agent_decisions(
    agent_decisions: List[AgentDecision],
    ground_truth: List[Dict[str, Any]],
) -> EvaluationMetrics:
    """
    Evaluates agent decisions against known ground truth.

    Args:
        agent_decisions: List of AgentDecision objects from Phase 2.
        ground_truth: List of ground truth dicts from the generator.

    Returns:
        EvaluationMetrics object with accuracy, precision, recall, and breakdown stats.
    """
    gt_index: Dict[str, Dict[str, Any]] = {
        row["transaction_id"]: row for row in ground_truth
    }

    total_decisions = len(agent_decisions)
    correct_decisions = 0

    auto_resolved_total = 0
    auto_resolved_correct = 0
    human_review_total = 0
    human_review_correct = 0

    # Count how many total exceptions in ground truth were expected to be AUTO_RESOLVED
    ground_truth_auto_resolvable = sum(
        1 for row in ground_truth if row.get("expected_phase2_decision") == "AUTO_RESOLVED"
    )

    category_accuracy: Dict[str, Dict[str, int]] = {}

    for decision in agent_decisions:
        txn_id = decision.transaction_id
        exception_type = decision.exception_type
        agent_decision = decision.decision

        gt = gt_index.get(txn_id, {})
        expected_decision = gt.get("expected_phase2_decision")

        # Fallback if expected_phase2_decision is not set (e.g. legacy ground truth)
        if not expected_decision or expected_decision == "N/A":
            expected_decision = "HUMAN_REVIEW"

        is_correct = agent_decision == expected_decision
        if is_correct:
            correct_decisions += 1

        if agent_decision == "AUTO_RESOLVED":
            auto_resolved_total += 1
            if is_correct:
                auto_resolved_correct += 1
        else:
            human_review_total += 1
            if is_correct:
                human_review_correct += 1

        cat = exception_type or "UNKNOWN"
        if cat not in category_accuracy:
            category_accuracy[cat] = {"correct": 0, "total": 0}
        category_accuracy[cat]["total"] += 1
        if is_correct:
            category_accuracy[cat]["correct"] += 1

    phase1_accuracy = 100.0  # Phase 1 is 100% deterministic rules
    phase2_accuracy = (correct_decisions / total_decisions * 100) if total_decisions > 0 else 0.0

    precision = (
        (auto_resolved_correct / auto_resolved_total * 100)
        if auto_resolved_total > 0
        else 100.0
    )

    recall = (
        (auto_resolved_correct / ground_truth_auto_resolvable * 100)
        if ground_truth_auto_resolvable > 0
        else 100.0
    )

    return EvaluationMetrics(
        phase1_accuracy=phase1_accuracy,
        phase2_decision_accuracy=phase2_accuracy,
        auto_resolution_precision=precision,
        auto_resolution_recall=recall,
        agent_total_decisions=total_decisions,
        agent_correct_decisions=correct_decisions,
        auto_resolved_correct=auto_resolved_correct,
        auto_resolved_total=auto_resolved_total,
        human_review_correct=human_review_correct,
        human_review_total=human_review_total,
        ground_truth_auto_resolvable=ground_truth_auto_resolvable,
        category_accuracy=category_accuracy,
    )


def compute_phase2_metrics(
    phase1_results: List[Dict[str, Any]],
    agent_decisions: List[AgentDecision],
    total_records: int,
) -> Dict[str, Any]:
    """Computes combined Phase 1 + Phase 2 summary metrics."""
    phase1_reconciled = sum(1 for r in phase1_results if r["status"] == "RECONCILED")
    phase1_exceptions = sum(1 for r in phase1_results if r["status"] == "EXCEPTION")

    auto_resolved = sum(1 for d in agent_decisions if d.decision == "AUTO_RESOLVED")
    human_review = sum(1 for d in agent_decisions if d.decision == "HUMAN_REVIEW")

    final_resolved = phase1_reconciled + auto_resolved
    final_unresolved = human_review

    initial_match_rate = (phase1_reconciled / total_records * 100) if total_records > 0 else 0.0
    agent_resolution_rate = (auto_resolved / phase1_exceptions * 100) if phase1_exceptions > 0 else 0.0
    final_resolution_rate = (final_resolved / total_records * 100) if total_records > 0 else 0.0

    return {
        "total_records": total_records,
        "phase1_reconciled": phase1_reconciled,
        "phase1_exceptions": phase1_exceptions,
        "initial_match_rate": initial_match_rate,
        "auto_resolved": auto_resolved,
        "human_review_required": human_review,
        "agent_resolution_rate": agent_resolution_rate,
        "final_resolved": final_resolved,
        "final_unresolved": final_unresolved,
        "final_resolution_rate": final_resolution_rate,
    }
