"""
Ground-truth evaluation of Phase 1 and Phase 2 reconciliation decisions.

Calculates Phase 1 detection accuracy, Phase 2 decision accuracy, Auto-Resolution
Precision, and Auto-Resolution Recall against known synthetic ground truth.

Measurement policy: a rate whose denominator is zero is reported as None
("not measured"), never as 100%. A metric nobody could verify must not read
as a perfect score.
"""

from typing import Any, Dict, List, Optional, Tuple
from src.agent.schemas import AgentDecision, EvaluationMetrics


def _parse_bool_flag(value: Any) -> Optional[bool]:
    """
    Parses a ground-truth boolean that may arrive as a real bool or as CSV text.

    Returns None for absent/unrecognised values so callers can distinguish
    "labelled False" from "not labelled at all".
    """
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in ("true", "1", "yes", "y"):
        return True
    if text in ("false", "0", "no", "n"):
        return False
    return None


def _expected_is_exception(row: Dict[str, Any]) -> Optional[bool]:
    """
    Reads the ground-truth "should Phase 1 have flagged this" label.

    Accepts either spelling in circulation: the explicit `is_phase1_exception`
    boolean flag, or `expected_phase1_status` == "EXCEPTION". Returns None when
    the row carries neither, so unlabelled rows are excluded from the
    denominator rather than counted as clean.
    """
    flag = _parse_bool_flag(row.get("is_phase1_exception"))
    if flag is not None:
        return flag
    status = row.get("expected_phase1_status") or row.get("expected_status")
    if status is None:
        return None
    text = str(status).strip().upper()
    if text == "EXCEPTION":
        return True
    if text == "RECONCILED":
        return False
    return None


def compute_phase1_detection_metrics(
    phase1_results: List[Dict[str, Any]],
    ground_truth: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Measures the Phase 1 rule engine against the ground-truth exception label,
    treating "flagged as an exception" as the positive class.

    Deterministic does not mean correct: a rule set can miss a real break
    (false negative) or flag a clean record (false positive). This function
    measures that rather than assuming it away.

    Returns all-None rates when no record carries a usable label.
    """
    actual_flagged: Dict[str, bool] = {
        str(r.get("transaction_id", "")): (r.get("status") == "EXCEPTION")
        for r in phase1_results
    }

    tp = fp = fn = tn = 0
    labelled = 0

    for row in ground_truth:
        expected = _expected_is_exception(row)
        if expected is None:
            continue
        txn_id = str(row.get("transaction_id", ""))
        if txn_id not in actual_flagged:
            continue
        labelled += 1
        flagged = actual_flagged[txn_id]
        if expected and flagged:
            tp += 1
        elif expected and not flagged:
            fn += 1
        elif not expected and flagged:
            fp += 1
        else:
            tn += 1

    if labelled == 0:
        return {
            "phase1_accuracy": None,
            "phase1_detection_precision": None,
            "phase1_detection_recall": None,
            "phase1_true_positives": 0,
            "phase1_false_positives": 0,
            "phase1_false_negatives": 0,
            "phase1_labelled_records": 0,
        }

    precision = (tp / (tp + fp) * 100) if (tp + fp) > 0 else None
    recall = (tp / (tp + fn) * 100) if (tp + fn) > 0 else None

    return {
        "phase1_accuracy": round((tp + tn) / labelled * 100, 2),
        "phase1_detection_precision": round(precision, 2) if precision is not None else None,
        "phase1_detection_recall": round(recall, 2) if recall is not None else None,
        "phase1_true_positives": tp,
        "phase1_false_positives": fp,
        "phase1_false_negatives": fn,
        "phase1_labelled_records": labelled,
    }



def partition_evaluation_runs(
    exceptions: List[Dict[str, Any]],
    ground_truth: List[Dict[str, Any]],
    cases_per_run: int = 5,
    runs: int = 1,
) -> List[List[Dict[str, Any]]]:
    """
    Deterministically partitions exceptions into multiple non-overlapping runs.

    Ensures:
    - 0 duplicate transaction IDs across all runs.
    - Each run maintains a representative decision distribution (~40% AUTO_RESOLVED, ~60% HUMAN_REVIEW)
      where available in remaining pools.
    - Maximum exception reason diversity across all runs.

    Args:
        exceptions: Available Phase 1 exception records.
        ground_truth: Ground truth records for decision class balancing.
        cases_per_run: Number of cases per run (must be >= 1).
        runs: Number of evaluation runs (must be >= 1).

    Returns:
        List of runs, where each run is a list of exception records.
    """
    if cases_per_run < 1:
        raise ValueError(f"cases_per_run must be >= 1, got {cases_per_run}")
    if runs < 1:
        raise ValueError(f"runs must be >= 1, got {runs}")

    total_requested = cases_per_run * runs
    if total_requested > len(exceptions):
        raise ValueError(
            f"Requested {total_requested} total cases ({runs} runs x {cases_per_run} cases), "
            f"but only {len(exceptions)} Phase 1 exceptions are available. "
            f"Maximum possible runs with {cases_per_run} cases/run is {len(exceptions) // cases_per_run}."
        )

    gt_index: Dict[str, Dict[str, Any]] = {
        row["transaction_id"]: row for row in ground_truth
    }

    # Sort all exceptions deterministically first
    sorted_exceptions = sorted(exceptions, key=lambda x: str(x.get("transaction_id", "")))

    auto_pool: List[Dict[str, Any]] = []
    human_pool: List[Dict[str, Any]] = []

    for exc in sorted_exceptions:
        txn_id = exc.get("transaction_id", "")
        gt = gt_index.get(txn_id, {})
        expected = gt.get("expected_phase2_decision", "HUMAN_REVIEW")
        if expected == "AUTO_RESOLVED":
            auto_pool.append(exc)
        else:
            human_pool.append(exc)

    def _pop_diverse_by_reason(pool: List[Dict[str, Any]], target: int) -> List[Dict[str, Any]]:
        """Extracts up to target cases from pool maximizing reason diversity, removing them from pool."""
        if target <= 0 or not pool:
            return []

        by_reason: Dict[str, List[Dict[str, Any]]] = {}
        for c in pool:
            r = c.get("reason", "UNKNOWN")
            by_reason.setdefault(r, []).append(c)

        selected: List[Dict[str, Any]] = []
        reasons_order = sorted(by_reason.keys())

        idx = 0
        while len(selected) < target and any(by_reason.values()):
            reason = reasons_order[idx % len(reasons_order)]
            if by_reason[reason]:
                item = by_reason[reason].pop(0)
                selected.append(item)
                pool.remove(item)
            idx += 1

        return selected

    partitioned_runs: List[List[Dict[str, Any]]] = []

    for _ in range(runs):
        if cases_per_run == 5:
            target_auto = min(2, len(auto_pool))
            target_human = min(3, len(human_pool))
        else:
            target_auto = min(round(cases_per_run * 0.4), len(auto_pool))
            target_human = min(cases_per_run - target_auto, len(human_pool))

        # Fill remaining quota from whichever pool has cases left
        while (target_auto + target_human) < cases_per_run and (len(auto_pool) > target_auto or len(human_pool) > target_human):
            if len(auto_pool) > target_auto:
                target_auto += 1
            elif len(human_pool) > target_human:
                target_human += 1

        selected_auto = _pop_diverse_by_reason(auto_pool, target_auto)
        selected_human = _pop_diverse_by_reason(human_pool, target_human)

        run_cases = selected_auto + selected_human
        run_cases_sorted = sorted(run_cases, key=lambda x: str(x.get("transaction_id", "")))
        partitioned_runs.append(run_cases_sorted)

    return partitioned_runs


def select_evaluation_cases(
    exceptions: List[Dict[str, Any]],
    ground_truth: List[Dict[str, Any]],
    count: int = 5,
) -> List[Dict[str, Any]]:
    """
    Deterministically selects a diverse, representative subset of exceptions for single-run evaluation.
    """
    if count <= 0 or not exceptions:
        return []
    if count >= len(exceptions):
        return sorted(exceptions, key=lambda x: str(x.get("transaction_id", "")))

    runs = partition_evaluation_runs(exceptions, ground_truth, cases_per_run=count, runs=1)
    return runs[0] if runs else []


def compute_aggregate_metrics(run_summaries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Computes aggregate metrics across multiple evaluation runs from total raw counts.
    """
    if not run_summaries:
        return {
            "evaluation_runs_total": 0,
            "total_selected": 0,
            "total_completed": 0,
            "total_not_evaluated": 0,
            "auto_resolved": 0,
            "human_review": 0,
            "decision_accuracy": None,
            "auto_resolution_precision": None,
            "auto_resolution_recall": None,
            "human_review_rate": 0.0,
            "not_evaluated_rate": 0.0,
            "total_processing_time_sec": 0.0,
            "average_case_latency_sec": 0.0,
            "total_tokens": 0,
            "average_tokens_per_case": 0,
        }

    total_selected = sum(r.get("cases_selected", 0) for r in run_summaries)
    total_completed = sum(r.get("cases_completed", 0) for r in run_summaries)
    total_not_evaluated = sum(r.get("cases_not_evaluated", 0) for r in run_summaries)

    total_correct = sum(r.get("correct_decisions", 0) for r in run_summaries)
    total_auto_resolved = sum(r.get("auto_resolved", 0) for r in run_summaries)
    total_auto_resolved_correct = sum(r.get("auto_resolved_correct", 0) for r in run_summaries)
    total_human_review = sum(r.get("human_review", 0) for r in run_summaries)
    total_gt_auto_resolvable = sum(r.get("ground_truth_auto_resolvable", 0) for r in run_summaries)

    total_time = sum(r.get("phase2_time_sec", 0.0) for r in run_summaries)
    total_tokens = sum(r.get("total_tokens", 0) or 0 for r in run_summaries)

    # None, not 100.0: an empty denominator is an unmeasured rate.
    decision_accuracy = (total_correct / total_completed * 100) if total_completed > 0 else None
    precision = (total_auto_resolved_correct / total_auto_resolved * 100) if total_auto_resolved > 0 else None
    recall = (total_auto_resolved_correct / total_gt_auto_resolvable * 100) if total_gt_auto_resolvable > 0 else None
    human_review_rate = (total_human_review / total_completed * 100) if total_completed > 0 else 0.0
    not_evaluated_rate = (total_not_evaluated / total_selected * 100) if total_selected > 0 else 0.0
    avg_latency = (total_time / total_completed) if total_completed > 0 else 0.0
    avg_tokens = round(total_tokens / total_completed) if total_completed > 0 else 0

    return {
        "evaluation_runs_total": len(run_summaries),
        "total_selected": total_selected,
        "total_completed": total_completed,
        "total_not_evaluated": total_not_evaluated,
        "auto_resolved": total_auto_resolved,
        "human_review": total_human_review,
        "decision_accuracy": round(decision_accuracy, 2) if decision_accuracy is not None else None,
        "auto_resolution_precision": round(precision, 2) if precision is not None else None,
        "auto_resolution_recall": round(recall, 2) if recall is not None else None,
        "human_review_rate": round(human_review_rate, 2),
        "not_evaluated_rate": round(not_evaluated_rate, 2),
        "total_processing_time_sec": round(total_time, 4),
        "average_case_latency_sec": round(avg_latency, 4),
        "total_tokens": total_tokens,
        "average_tokens_per_case": avg_tokens,
    }



def evaluate_agent_decisions(
    agent_decisions: List[AgentDecision],
    ground_truth: List[Dict[str, Any]],
    is_subset: bool = False,
    total_selected: Optional[int] = None,
    phase1_results: Optional[List[Dict[str, Any]]] = None,
) -> EvaluationMetrics:
    """
    Evaluates agent decisions against known ground truth.

    Supports subset evaluation and NOT_EVALUATED exclusions. Metrics are calculated
    strictly over successfully completed LLM investigations.

    Args:
        agent_decisions: List of AgentDecision objects.
        ground_truth: List of ground truth dicts from the generator.
        is_subset: True if evaluating a subset of exceptions.
        total_selected: Number of cases selected for evaluation.
        phase1_results: Full Phase 1 result rows. Supplied, Phase 1 detection
            quality is measured against the ground-truth `is_phase1_exception`
            flag; omitted, the Phase 1 rates come back None rather than assumed.

    Returns:
        EvaluationMetrics with measured rates, or None for any rate whose
        denominator is empty.
    """
    gt_index: Dict[str, Dict[str, Any]] = {
        row["transaction_id"]: row for row in ground_truth
    }

    # Filter completed decisions vs NOT_EVALUATED
    completed_decisions = [d for d in agent_decisions if d.decision in ("AUTO_RESOLVED", "HUMAN_REVIEW")]
    not_evaluated_count = sum(1 for d in agent_decisions if d.decision == "NOT_EVALUATED")

    total_completed = len(completed_decisions)
    correct_decisions = 0

    auto_resolved_total = 0
    auto_resolved_correct = 0
    human_review_total = 0
    human_review_correct = 0

    category_accuracy: Dict[str, Dict[str, int]] = {}

    for decision in completed_decisions:
        txn_id = decision.transaction_id
        exception_type = decision.exception_type
        agent_decision = decision.decision

        gt = gt_index.get(txn_id, {})
        expected_decision = gt.get("expected_phase2_decision")

        if not expected_decision or expected_decision == "N/A":
            expected_decision = "HUMAN_REVIEW"

        is_correct = (agent_decision == expected_decision)
        if is_correct:
            correct_decisions += 1

        if agent_decision == "AUTO_RESOLVED":
            auto_resolved_total += 1
            if is_correct:
                auto_resolved_correct += 1
        elif agent_decision == "HUMAN_REVIEW":
            human_review_total += 1
            if is_correct:
                human_review_correct += 1

        cat = exception_type or "UNKNOWN"
        if cat not in category_accuracy:
            category_accuracy[cat] = {"correct": 0, "total": 0}
        category_accuracy[cat]["total"] += 1
        if is_correct:
            category_accuracy[cat]["correct"] += 1

    # Ground truth auto-resolvable count
    if is_subset or (total_selected is not None and total_selected < len(ground_truth)):
        # Scope-aware recall: ground-truth auto-resolvable within the evaluated completed subset
        gt_auto_resolvable = sum(
            1 for d in completed_decisions
            if gt_index.get(d.transaction_id, {}).get("expected_phase2_decision") == "AUTO_RESOLVED"
        )
    else:
        # Full-batch recall
        gt_auto_resolvable = sum(
            1 for row in ground_truth if row.get("expected_phase2_decision") == "AUTO_RESOLVED"
        )

    # Phase 1 is deterministic, which is not the same as correct. Measure it
    # against the ground-truth flag when we have the rows to measure with.
    if phase1_results:
        p1 = compute_phase1_detection_metrics(phase1_results, ground_truth)
    else:
        p1 = {
            "phase1_accuracy": None,
            "phase1_detection_precision": None,
            "phase1_detection_recall": None,
            "phase1_true_positives": 0,
            "phase1_false_positives": 0,
            "phase1_false_negatives": 0,
            "phase1_labelled_records": 0,
        }

    # An empty denominator means unmeasured, not perfect.
    phase2_accuracy = (correct_decisions / total_completed * 100) if total_completed > 0 else None
    precision = (auto_resolved_correct / auto_resolved_total * 100) if auto_resolved_total > 0 else None
    recall = (auto_resolved_correct / gt_auto_resolvable * 100) if gt_auto_resolvable > 0 else None

    selected_count = total_selected if total_selected is not None else len(agent_decisions)

    return EvaluationMetrics(
        phase1_accuracy=p1["phase1_accuracy"],
        phase2_decision_accuracy=round(phase2_accuracy, 2) if phase2_accuracy is not None else None,
        auto_resolution_precision=round(precision, 2) if precision is not None else None,
        auto_resolution_recall=round(recall, 2) if recall is not None else None,
        phase1_detection_precision=p1["phase1_detection_precision"],
        phase1_detection_recall=p1["phase1_detection_recall"],
        phase1_true_positives=p1["phase1_true_positives"],
        phase1_false_positives=p1["phase1_false_positives"],
        phase1_false_negatives=p1["phase1_false_negatives"],
        phase1_labelled_records=p1["phase1_labelled_records"],
        agent_total_decisions=total_completed,
        agent_correct_decisions=correct_decisions,
        auto_resolved_correct=auto_resolved_correct,
        auto_resolved_total=auto_resolved_total,
        human_review_correct=human_review_correct,
        human_review_total=human_review_total,
        ground_truth_auto_resolvable=gt_auto_resolvable,
        category_accuracy=category_accuracy,
        cases_selected=selected_count,
        cases_completed=total_completed,
        cases_not_evaluated=not_evaluated_count,
        is_subset_evaluation=is_subset or (selected_count < len(ground_truth)),
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
    not_evaluated = sum(1 for d in agent_decisions if d.decision == "NOT_EVALUATED")

    final_resolved = phase1_reconciled + auto_resolved
    # NOT_EVALUATED cases are unresolved. Counting only human_review here would
    # silently drop cases the agent never managed to judge, breaking the
    # final_resolved + final_unresolved == total_records invariant.
    final_unresolved = human_review + not_evaluated

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
        "not_evaluated": not_evaluated,
        "agent_resolution_rate": agent_resolution_rate,
        "final_resolved": final_resolved,
        "final_unresolved": final_unresolved,
        "final_resolution_rate": final_resolution_rate,
    }

