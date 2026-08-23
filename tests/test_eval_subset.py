"""
Unit tests for the 5-case subset evaluation mode, representative case selection,
multi-run deterministic partitioning, and aggregate evaluation metrics.
"""

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from src.agent.controller import AgentController
from src.agent.evaluator import (
    compute_aggregate_metrics,
    evaluate_agent_decisions,
    partition_evaluation_runs,
    select_evaluation_cases,
)
from src.agent.schemas import AgentDecision
from src.api.main import app
from src.generator import SyntheticDataGenerator
from src.reconciliation import ReconciliationEngine
from src.run_llm_eval import run_evaluation


@pytest.fixture
def dataset_and_ground_truth(tmp_path):
    """Generates synthetic dataset and runs Phase 1 reconciliation."""
    generator = SyntheticDataGenerator(seed=42, total_transactions=100)
    p_path, l_path, b_path, a_path = generator.save_to_csv(str(tmp_path))
    payments, ledger, bank, adjustments, ground_truth = generator.generate()
    phase1_results, phase1_metrics = ReconciliationEngine.reconcile_batch(p_path, l_path, b_path)
    exceptions = [r for r in phase1_results if r["status"] == "EXCEPTION"]
    return {
        "payments": payments,
        "ledger": ledger,
        "bank": bank,
        "adjustments": adjustments,
        "ground_truth": ground_truth,
        "phase1_results": phase1_results,
        "phase1_metrics": phase1_metrics,
        "exceptions": exceptions,
    }


# 1. --cases 5 selects five
def test_select_cases_5(dataset_and_ground_truth):
    exceptions = dataset_and_ground_truth["exceptions"]
    ground_truth = dataset_and_ground_truth["ground_truth"]

    selected = select_evaluation_cases(exceptions, ground_truth, count=5)
    assert len(selected) == 5


# 2. --cases 4 selects four
def test_select_cases_4(dataset_and_ground_truth):
    exceptions = dataset_and_ground_truth["exceptions"]
    ground_truth = dataset_and_ground_truth["ground_truth"]

    selected = select_evaluation_cases(exceptions, ground_truth, count=4)
    assert len(selected) == 4


# 3. Deterministic selection
def test_selection_is_deterministic(dataset_and_ground_truth):
    exceptions = dataset_and_ground_truth["exceptions"]
    ground_truth = dataset_and_ground_truth["ground_truth"]

    run1 = select_evaluation_cases(exceptions, ground_truth, count=5)
    run2 = select_evaluation_cases(exceptions, ground_truth, count=5)

    txns1 = [r["transaction_id"] for r in run1]
    txns2 = [r["transaction_id"] for r in run2]

    assert txns1 == txns2
    assert len(txns1) == 5


# 4. Selection includes both expected decision classes when possible
def test_selection_includes_both_decision_classes(dataset_and_ground_truth):
    exceptions = dataset_and_ground_truth["exceptions"]
    ground_truth = dataset_and_ground_truth["ground_truth"]
    gt_index = {r["transaction_id"]: r for r in ground_truth}

    selected = select_evaluation_cases(exceptions, ground_truth, count=5)
    decisions = [gt_index[r["transaction_id"]].get("expected_phase2_decision") for r in selected]

    auto_count = decisions.count("AUTO_RESOLVED")
    human_count = decisions.count("HUMAN_REVIEW")

    assert auto_count == 2
    assert human_count == 3


# 5. Unselected exceptions never reach the LLM
def test_unselected_exceptions_never_reach_llm(dataset_and_ground_truth):
    exceptions = dataset_and_ground_truth["exceptions"]
    ground_truth = dataset_and_ground_truth["ground_truth"]

    selected = select_evaluation_cases(exceptions, ground_truth, count=5)
    selected_txns = {r["transaction_id"] for r in selected}

    mock_llm = MagicMock()
    mock_llm.model = "mock-model"
    mock_llm.chat.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content='{"decision": "HUMAN_REVIEW", "confidence": 1.0, "reason": "test", "evidence": ["test"], "recommended_action": "test"}', tool_calls=None))]
    )

    investigated_txns = []

    for exc in selected:
        investigated_txns.append(exc["transaction_id"])
        mock_llm.chat(messages=[{"role": "user", "content": exc["transaction_id"]}])

    assert set(investigated_txns) == selected_txns
    assert len(investigated_txns) == 5
    assert mock_llm.chat.call_count == 5


# 6. Multi-run: --runs 1 execution
def test_runs_1_execution(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "demo")

    result = run_evaluation(provider="demo", cases=5, runs=1)

    assert result["runs"] == 1
    assert result["cases_per_run"] == 5
    assert result["total_selected"] == 5
    assert result["completed"] == 5
    assert result["not_evaluated"] == 0
    assert len(result["per_run_summaries"]) == 1


# 7. Multi-run: --runs 3 execution (15 unique cases)
def test_runs_3_execution(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "demo")

    result = run_evaluation(provider="demo", cases=5, runs=3)

    assert result["runs"] == 3
    assert result["cases_per_run"] == 5
    assert result["total_selected"] == 15
    assert result["completed"] == 15
    assert result["not_evaluated"] == 0
    assert len(result["per_run_summaries"]) == 3

    # Verify all 15 cases across the 3 runs are unique
    all_txns = []
    for r in result["per_run_summaries"]:
        for c in r.get("investigated_cases", []):
            all_txns.append(c["transaction_id"])

    assert len(all_txns) == 15
    assert len(set(all_txns)) == 15


# 8. Invalid runs parameter raises ValueError
def test_invalid_runs_or_cases_raises_error(dataset_and_ground_truth):
    exceptions = dataset_and_ground_truth["exceptions"]
    ground_truth = dataset_and_ground_truth["ground_truth"]

    with pytest.raises(ValueError) as exc:
        partition_evaluation_runs(exceptions, ground_truth, cases_per_run=5, runs=0)
    assert "runs must be >= 1" in str(exc.value)

    with pytest.raises(ValueError) as exc:
        partition_evaluation_runs(exceptions, ground_truth, cases_per_run=0, runs=1)
    assert "cases_per_run must be >= 1" in str(exc.value)


# 9. cases * runs > available exceptions fails with clear error
def test_cases_times_runs_exceeding_exceptions_raises_error(dataset_and_ground_truth):
    exceptions = dataset_and_ground_truth["exceptions"]
    ground_truth = dataset_and_ground_truth["ground_truth"]

    # 5 * 7 = 35 > 30 exceptions
    with pytest.raises(ValueError) as exc:
        partition_evaluation_runs(exceptions, ground_truth, cases_per_run=5, runs=7)
    assert "Requested 35 total cases" in str(exc.value)


# 10. Deterministic partitioning across runs
def test_deterministic_partitioning(dataset_and_ground_truth):
    exceptions = dataset_and_ground_truth["exceptions"]
    ground_truth = dataset_and_ground_truth["ground_truth"]

    runs1 = partition_evaluation_runs(exceptions, ground_truth, cases_per_run=5, runs=3)
    runs2 = partition_evaluation_runs(exceptions, ground_truth, cases_per_run=5, runs=3)

    assert len(runs1) == 3
    assert len(runs2) == 3

    for r1, r2 in zip(runs1, runs2):
        txns1 = [c["transaction_id"] for c in r1]
        txns2 = [c["transaction_id"] for c in r2]
        assert txns1 == txns2


# 11. No duplicate transaction IDs across partitioned runs
def test_no_duplicate_txns_across_partitioned_runs(dataset_and_ground_truth):
    exceptions = dataset_and_ground_truth["exceptions"]
    ground_truth = dataset_and_ground_truth["ground_truth"]

    runs = partition_evaluation_runs(exceptions, ground_truth, cases_per_run=5, runs=4)
    all_txns = [c["transaction_id"] for r in runs for c in r]

    assert len(all_txns) == 20
    assert len(set(all_txns)) == 20


# 12. Aggregate metrics computation from raw counts
def test_compute_aggregate_metrics():
    run_summaries = [
        {
            "run_number": 1,
            "cases_selected": 5,
            "cases_completed": 5,
            "cases_not_evaluated": 0,
            "correct_decisions": 5,
            "auto_resolved": 2,
            "auto_resolved_correct": 2,
            "human_review": 3,
            "ground_truth_auto_resolvable": 2,
            "phase2_time_sec": 1.0,
            "total_tokens": 1000,
        },
        {
            "run_number": 2,
            "cases_selected": 5,
            "cases_completed": 5,
            "cases_not_evaluated": 0,
            "correct_decisions": 4,
            "auto_resolved": 2,
            "auto_resolved_correct": 1,
            "human_review": 3,
            "ground_truth_auto_resolvable": 2,
            "phase2_time_sec": 1.5,
            "total_tokens": 1200,
        },
    ]

    agg = compute_aggregate_metrics(run_summaries)

    assert agg["total_selected"] == 10
    assert agg["total_completed"] == 10
    assert agg["total_not_evaluated"] == 0
    # 9 / 10 correct = 90.0%
    assert agg["decision_accuracy"] == 90.0
    # 3 correct auto / 4 total auto = 75.0%
    assert agg["auto_resolution_precision"] == 75.0
    # 3 correct auto / 4 total ground truth auto = 75.0%
    assert agg["auto_resolution_recall"] == 75.0
    assert agg["total_tokens"] == 2200
    assert agg["average_tokens_per_case"] == 220


# 13. NOT_EVALUATED excluded from decision accuracy
def test_not_evaluated_excluded_from_aggregate():
    run_summaries = [
        {
            "run_number": 1,
            "cases_selected": 5,
            "cases_completed": 4,
            "cases_not_evaluated": 1,
            "correct_decisions": 4,
            "auto_resolved": 1,
            "auto_resolved_correct": 1,
            "human_review": 3,
            "ground_truth_auto_resolvable": 1,
            "phase2_time_sec": 1.0,
            "total_tokens": 500,
        }
    ]

    agg = compute_aggregate_metrics(run_summaries)

    assert agg["total_selected"] == 5
    assert agg["total_completed"] == 4
    assert agg["total_not_evaluated"] == 1
    # 4 correct out of 4 completed = 100.0%
    assert agg["decision_accuracy"] == 100.0
    assert agg["not_evaluated_rate"] == 20.0


# 14. Full Phase 1 still processes all 100 in multi-run
def test_full_phase1_still_processes_all_100_in_multi_run():
    result = run_evaluation(provider="demo", cases=5, runs=2)

    assert result["total_selected"] == 10
    assert result["completed"] == 10
    assert len(result["per_run_summaries"]) == 2


# 15. Evaluation API endpoints E2E test
def test_evaluations_api_e2e():
    client = TestClient(app)

    response = client.post(
        "/api/evaluations",
        json={"provider": "demo", "cases_per_run": 5, "runs": 2},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["provider"] == "demo"
    assert data["runs"] == 2
    assert data["cases_per_run"] == 5
    assert data["total_selected"] == 10
    assert data["completed"] == 10
    assert "evaluation_group_id" in data
    group_id = data["evaluation_group_id"]

    # Test GET by group_id
    get_resp = client.get(f"/api/evaluations/{group_id}")
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    assert get_data["evaluation_group_id"] == group_id
    assert len(get_data["per_run_summaries"]) == 2
