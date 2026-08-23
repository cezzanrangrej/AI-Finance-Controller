"""
Unit and integration tests for Batch Investigation Mode (BatchAgentController).
"""

import json
from unittest.mock import MagicMock
import pytest

from src.agent.batch_controller import BatchAgentController, prefetch_case_evidence
from src.agent.controller import AgentController, LLMClient
from src.agent.schemas import AgentDecision, BatchInvestigationCase
from src.agent.tools import FinancialToolkit
from src.generator import SyntheticDataGenerator
from src.reconciliation import ReconciliationEngine
from src.run_llm_eval import run_evaluation


class MockMessage:
    def __init__(self, content: str = None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []


class MockChoice:
    def __init__(self, message: MockMessage):
        self.message = message


class MockResponse:
    def __init__(self, message: MockMessage):
        self.choices = [MockChoice(message)]


@pytest.fixture
def sample_batch_toolkit_and_exceptions(tmp_path):
    generator = SyntheticDataGenerator(seed=42, total_transactions=100)
    data_dir = str(tmp_path)
    p_path, l_path, b_path, a_path = generator.save_to_csv(data_dir)
    payments, ledger, bank, adjustments, ground_truth = generator.generate()
    toolkit = FinancialToolkit(payments, ledger, bank, adjustments)

    p1_results, _ = ReconciliationEngine.reconcile_batch(p_path, l_path, b_path)
    exceptions = [r for r in p1_results if r["status"] == "EXCEPTION"]

    return toolkit, exceptions, ground_truth


    return toolkit, exceptions, ground_truth


# ----------------------------------------------------------------------
# Test 1: 5-case batch input
# ----------------------------------------------------------------------
def test_5_case_batch_input(sample_batch_toolkit_and_exceptions):
    toolkit, exceptions, _ = sample_batch_toolkit_and_exceptions
    batch_5 = exceptions[:5]

    mock_llm = MagicMock(spec=LLMClient)
    mock_decisions = [
        {
            "transaction_id": e["transaction_id"],
            "decision": "AUTO_RESOLVED" if i % 2 == 0 else "HUMAN_REVIEW",
            "exception_type": e.get("reason", "TEST"),
            "resolution_type": "ADJUSTMENT_EXPLAINED" if i % 2 == 0 else "NONE",
            "resolved_difference": 100.0 if i % 2 == 0 else None,
            "reason": f"Evaluated case {e['transaction_id']}",
            "evidence": ["Prefetched evidence verified."],
            "confidence": 0.95,
            "recommended_action": "Review action.",
        }
        for i, e in enumerate(batch_5)
    ]
    mock_llm.chat.return_value = MockResponse(MockMessage(content=json.dumps({"decisions": mock_decisions})))

    batch_controller = BatchAgentController(toolkit=toolkit, llm_client=mock_llm)
    decisions, log = batch_controller.investigate_batch(batch_5)

    assert len(decisions) == 5
    assert log.batch_size == 5
    assert log.fallback_count == 0


# ----------------------------------------------------------------------
# Test 2: 10-case batch input
# ----------------------------------------------------------------------
def test_10_case_batch_input(sample_batch_toolkit_and_exceptions):
    toolkit, exceptions, _ = sample_batch_toolkit_and_exceptions
    batch_10 = exceptions[:10]

    mock_llm = MagicMock(spec=LLMClient)
    mock_decisions = [
        {
            "transaction_id": e["transaction_id"],
            "decision": "HUMAN_REVIEW",
            "exception_type": e.get("reason", "TEST"),
            "resolution_type": "NONE",
            "reason": f"Evaluated case {e['transaction_id']}",
            "evidence": ["Evidence checked."],
            "confidence": 0.9,
            "recommended_action": "Review.",
        }
        for e in batch_10
    ]
    mock_llm.chat.return_value = MockResponse(MockMessage(content=json.dumps({"decisions": mock_decisions})))

    batch_controller = BatchAgentController(toolkit=toolkit, llm_client=mock_llm)
    decisions, log = batch_controller.investigate_batch(batch_10)

    assert len(decisions) == 10
    assert log.batch_size == 10
    assert log.fallback_count == 0


# ----------------------------------------------------------------------
# Test 3: Exactly one decision per transaction
# ----------------------------------------------------------------------
def test_exactly_one_decision_per_transaction(sample_batch_toolkit_and_exceptions):
    toolkit, exceptions, _ = sample_batch_toolkit_and_exceptions
    batch_cases = exceptions[:5]
    expected_ids = [e["transaction_id"] for e in batch_cases]

    mock_llm = MagicMock(spec=LLMClient)
    mock_decisions = [
        {
            "transaction_id": tid,
            "decision": "HUMAN_REVIEW",
            "exception_type": "TEST",
            "resolution_type": "NONE",
            "reason": "Test reason",
            "evidence": ["Evidence"],
            "confidence": 0.9,
            "recommended_action": "Action",
        }
        for tid in expected_ids
    ]
    mock_llm.chat.return_value = MockResponse(MockMessage(content=json.dumps({"decisions": mock_decisions})))

    batch_controller = BatchAgentController(toolkit=toolkit, llm_client=mock_llm)
    decisions, _ = batch_controller.investigate_batch(batch_cases)

    result_ids = [d.transaction_id for d in decisions]
    assert result_ids == expected_ids


# ----------------------------------------------------------------------
# Test 4: No duplicate transaction IDs in output
# ----------------------------------------------------------------------
def test_no_duplicate_transaction_ids(sample_batch_toolkit_and_exceptions):
    toolkit, exceptions, _ = sample_batch_toolkit_and_exceptions
    batch_cases = exceptions[:5]
    expected_ids = [e["transaction_id"] for e in batch_cases]

    mock_llm = MagicMock(spec=LLMClient)
    # LLM mistakenly sends duplicate of first txn
    mock_decisions = [
        {
            "transaction_id": expected_ids[0],
            "decision": "HUMAN_REVIEW",
            "exception_type": "TEST",
            "resolution_type": "NONE",
            "reason": "Duplicate 1",
            "evidence": [],
            "confidence": 0.9,
            "recommended_action": "Action",
        },
        {
            "transaction_id": expected_ids[0],
            "decision": "HUMAN_REVIEW",
            "exception_type": "TEST",
            "resolution_type": "NONE",
            "reason": "Duplicate 2",
            "evidence": [],
            "confidence": 0.9,
            "recommended_action": "Action",
        },
    ]
    # For missing cases, fallback agent will be called
    mock_llm.chat.side_effect = [
        MockResponse(MockMessage(content=json.dumps({"decisions": mock_decisions}))),
        # Fallback individual calls
        MockResponse(MockMessage(content=json.dumps({"transaction_id": expected_ids[1], "decision": "HUMAN_REVIEW", "exception_type": "TEST", "reason": "Fallback", "evidence": [], "confidence": 0.5, "recommended_action": "Review"}))),
        MockResponse(MockMessage(content=json.dumps({"transaction_id": expected_ids[2], "decision": "HUMAN_REVIEW", "exception_type": "TEST", "reason": "Fallback", "evidence": [], "confidence": 0.5, "recommended_action": "Review"}))),
        MockResponse(MockMessage(content=json.dumps({"transaction_id": expected_ids[3], "decision": "HUMAN_REVIEW", "exception_type": "TEST", "reason": "Fallback", "evidence": [], "confidence": 0.5, "recommended_action": "Review"}))),
        MockResponse(MockMessage(content=json.dumps({"transaction_id": expected_ids[4], "decision": "HUMAN_REVIEW", "exception_type": "TEST", "reason": "Fallback", "evidence": [], "confidence": 0.5, "recommended_action": "Review"}))),
    ]

    batch_controller = BatchAgentController(toolkit=toolkit, llm_client=mock_llm)
    decisions, log = batch_controller.investigate_batch(batch_cases)

    result_ids = [d.transaction_id for d in decisions]
    assert len(result_ids) == len(set(result_ids))
    assert result_ids == expected_ids


# ----------------------------------------------------------------------
# Test 5: Malformed batch response rejected and falls back
# ----------------------------------------------------------------------
def test_malformed_batch_response_rejected_and_falls_back(sample_batch_toolkit_and_exceptions):
    toolkit, exceptions, _ = sample_batch_toolkit_and_exceptions
    batch_cases = exceptions[:3]
    expected_ids = [e["transaction_id"] for e in batch_cases]

    mock_llm = MagicMock(spec=LLMClient)
    # Return invalid non-JSON string on batch call
    mock_llm.chat.side_effect = [
        MockResponse(MockMessage(content="This is not valid json!")),
        # Fallbacks for all 3 cases
        MockResponse(MockMessage(content=json.dumps({"transaction_id": expected_ids[0], "decision": "HUMAN_REVIEW", "exception_type": "TEST", "reason": "FB1", "evidence": [], "confidence": 0.5, "recommended_action": "Review"}))),
        MockResponse(MockMessage(content=json.dumps({"transaction_id": expected_ids[1], "decision": "HUMAN_REVIEW", "exception_type": "TEST", "reason": "FB2", "evidence": [], "confidence": 0.5, "recommended_action": "Review"}))),
        MockResponse(MockMessage(content=json.dumps({"transaction_id": expected_ids[2], "decision": "HUMAN_REVIEW", "exception_type": "TEST", "reason": "FB3", "evidence": [], "confidence": 0.5, "recommended_action": "Review"}))),
    ]

    batch_controller = BatchAgentController(toolkit=toolkit, llm_client=mock_llm)
    decisions, log = batch_controller.investigate_batch(batch_cases)

    assert len(decisions) == 3
    assert log.fallback_count == 3
    assert set(log.fallback_transaction_ids) == set(expected_ids)


# ----------------------------------------------------------------------
# Test 6: Missing decision in batch triggers fallback for missing case
# ----------------------------------------------------------------------
def test_missing_decision_triggers_fallback(sample_batch_toolkit_and_exceptions):
    toolkit, exceptions, _ = sample_batch_toolkit_and_exceptions
    batch_cases = exceptions[:3]
    expected_ids = [e["transaction_id"] for e in batch_cases]

    mock_llm = MagicMock(spec=LLMClient)
    # Batch response only includes case 0 and case 1 (misses case 2)
    mock_decisions = [
        {"transaction_id": expected_ids[0], "decision": "HUMAN_REVIEW", "exception_type": "TEST", "reason": "R0", "evidence": ["Evidence 0"], "confidence": 0.9, "recommended_action": "A0"},
        {"transaction_id": expected_ids[1], "decision": "HUMAN_REVIEW", "exception_type": "TEST", "reason": "R1", "evidence": ["Evidence 1"], "confidence": 0.9, "recommended_action": "A1"},
    ]
    mock_llm.chat.side_effect = [
        MockResponse(MockMessage(content=json.dumps({"decisions": mock_decisions}))),
        # Fallback for missing case 2
        MockResponse(MockMessage(content=json.dumps({"transaction_id": expected_ids[2], "decision": "HUMAN_REVIEW", "exception_type": "TEST", "reason": "FB2", "evidence": ["Fallback evidence"], "confidence": 0.5, "recommended_action": "Review"}))),
    ]

    batch_controller = BatchAgentController(toolkit=toolkit, llm_client=mock_llm)
    decisions, log = batch_controller.investigate_batch(batch_cases)

    assert len(decisions) == 3
    assert log.fallback_count == 1
    assert log.fallback_transaction_ids == [expected_ids[2]]


# ----------------------------------------------------------------------
# Test 7: Extra decision in batch ignored / handled safely
# ----------------------------------------------------------------------
def test_extra_decision_in_batch_ignored(sample_batch_toolkit_and_exceptions):
    toolkit, exceptions, _ = sample_batch_toolkit_and_exceptions
    batch_cases = exceptions[:2]
    expected_ids = [e["transaction_id"] for e in batch_cases]

    mock_llm = MagicMock(spec=LLMClient)
    mock_decisions = [
        {"transaction_id": expected_ids[0], "decision": "HUMAN_REVIEW", "exception_type": "TEST", "reason": "R0", "evidence": ["Evidence 0"], "confidence": 0.9, "recommended_action": "A0"},
        {"transaction_id": expected_ids[1], "decision": "HUMAN_REVIEW", "exception_type": "TEST", "reason": "R1", "evidence": ["Evidence 1"], "confidence": 0.9, "recommended_action": "A1"},
        {"transaction_id": "TXN_UNKNOWN_999", "decision": "HUMAN_REVIEW", "exception_type": "TEST", "reason": "Extra", "evidence": ["Evidence extra"], "confidence": 0.9, "recommended_action": "A"},
    ]
    mock_llm.chat.return_value = MockResponse(MockMessage(content=json.dumps({"decisions": mock_decisions})))

    batch_controller = BatchAgentController(toolkit=toolkit, llm_client=mock_llm)
    decisions, log = batch_controller.investigate_batch(batch_cases)

    assert len(decisions) == 2
    assert [d.transaction_id for d in decisions] == expected_ids
    assert log.fallback_count == 0


# ----------------------------------------------------------------------
# Test 8: Unknown transaction in batch rejected safely
# ----------------------------------------------------------------------
def test_unknown_transaction_in_batch_rejected(sample_batch_toolkit_and_exceptions):
    toolkit, exceptions, _ = sample_batch_toolkit_and_exceptions
    batch_cases = exceptions[:1]
    expected_id = batch_cases[0]["transaction_id"]

    mock_llm = MagicMock(spec=LLMClient)
    # LLM returns completely different ID
    mock_decisions = [
        {"transaction_id": "TXN_WRONG_ID", "decision": "AUTO_RESOLVED", "exception_type": "TEST", "reason": "Wrong", "evidence": ["Wrong evidence"], "confidence": 1.0, "recommended_action": "Action"}
    ]
    mock_llm.chat.side_effect = [
        MockResponse(MockMessage(content=json.dumps({"decisions": mock_decisions}))),
        MockResponse(MockMessage(content=json.dumps({"transaction_id": expected_id, "decision": "HUMAN_REVIEW", "exception_type": "TEST", "reason": "Recovered", "evidence": ["Recovered evidence"], "confidence": 0.5, "recommended_action": "Review"}))),
    ]

    batch_controller = BatchAgentController(toolkit=toolkit, llm_client=mock_llm)
    decisions, log = batch_controller.investigate_batch(batch_cases)

    assert len(decisions) == 1
    assert decisions[0].transaction_id == expected_id
    assert log.fallback_count == 1


# ----------------------------------------------------------------------
# Test 9: Deterministic evidence prefetch
# ----------------------------------------------------------------------
def test_deterministic_evidence_prefetch(sample_batch_toolkit_and_exceptions):
    toolkit, exceptions, _ = sample_batch_toolkit_and_exceptions
    txn_id = "TXN003"
    exc_rec = next((e for e in exceptions if e["transaction_id"] == txn_id), None)
    assert exc_rec is not None

    prefetched = prefetch_case_evidence(exc_rec, toolkit)
    assert isinstance(prefetched, BatchInvestigationCase)
    assert prefetched.transaction_id == "TXN003"
    assert prefetched.payment is not None
    assert prefetched.ledger is not None
    assert len(prefetched.bank_records) == 1
    assert len(prefetched.adjustments) == 1
    assert prefetched.expected_settlement is not None
    assert prefetched.adjusted_expected_settlement is not None


# ----------------------------------------------------------------------
# Test 10: Batch audit logging
# ----------------------------------------------------------------------
def test_batch_audit_logging(sample_batch_toolkit_and_exceptions):
    toolkit, exceptions, _ = sample_batch_toolkit_and_exceptions
    batch_cases = exceptions[:3]

    mock_llm = MagicMock(spec=LLMClient)
    mock_llm.provider = "openrouter"
    mock_llm.model = "meta-llama/llama-3.3-70b-instruct"
    mock_decisions = [
        {"transaction_id": e["transaction_id"], "decision": "HUMAN_REVIEW", "exception_type": "TEST", "reason": "R", "evidence": ["Evidence log"], "confidence": 0.9, "recommended_action": "A"}
        for e in batch_cases
    ]
    mock_llm.chat.return_value = MockResponse(MockMessage(content=json.dumps({"decisions": mock_decisions})))

    batch_controller = BatchAgentController(toolkit=toolkit, llm_client=mock_llm)
    decisions, log = batch_controller.investigate_batch(batch_cases)

    assert log.batch_id.startswith("batch_")
    assert log.batch_size == 3
    assert log.provider == "openrouter"
    assert log.model == "meta-llama/llama-3.3-70b-instruct"
    assert log.processing_time_sec >= 0.0
    assert len(log.decisions) == 3


# ----------------------------------------------------------------------
# Test 11: Token & latency measurement
# ----------------------------------------------------------------------
def test_token_and_latency_measurement(sample_batch_toolkit_and_exceptions):
    toolkit, exceptions, _ = sample_batch_toolkit_and_exceptions
    batch_cases = exceptions[:2]

    mock_llm = MagicMock(spec=LLMClient)
    mock_llm.cumulative_total_tokens = 1200
    mock_llm.cumulative_prompt_tokens = 800
    mock_llm.cumulative_completion_tokens = 400

    mock_decisions = [
        {"transaction_id": e["transaction_id"], "decision": "HUMAN_REVIEW", "exception_type": "TEST", "reason": "R", "evidence": ["Evidence tok"], "confidence": 0.9, "recommended_action": "A"}
        for e in batch_cases
    ]
    mock_llm.chat.return_value = MockResponse(MockMessage(content=json.dumps({"decisions": mock_decisions})))

    batch_controller = BatchAgentController(toolkit=toolkit, llm_client=mock_llm)
    _, log = batch_controller.investigate_batch(batch_cases)

    assert log.processing_time_sec > 0.0
    assert log.total_tokens is not None



# ----------------------------------------------------------------------
# Test 12: Batch size limits (1 <= N <= 10)
# ----------------------------------------------------------------------
def test_batch_size_limits(sample_batch_toolkit_and_exceptions):
    toolkit, exceptions, _ = sample_batch_toolkit_and_exceptions
    mock_llm = MagicMock(spec=LLMClient)
    batch_controller = BatchAgentController(toolkit=toolkit, llm_client=mock_llm)

    with pytest.raises(ValueError):
        batch_controller.investigate_exceptions_batch(exceptions, batch_size=0)

    with pytest.raises(ValueError):
        batch_controller.investigate_exceptions_batch(exceptions, batch_size=11)


# ----------------------------------------------------------------------
# Test 13: Demo mode batch evaluation executes cleanly
# ----------------------------------------------------------------------
def test_demo_mode_batch_evaluation_e2e(tmp_path):
    result = run_evaluation(
        provider="demo",
        cases=5,
        runs=1,
        batch_size=5,
        mode="batch",
    )

    assert result["completed"] == 5
    assert result["batch_size"] == 5
    assert result["mode"] == "batch"
    assert result["aggregate_accuracy"] == 1.0


# ----------------------------------------------------------------------
# Test 14: Compare mode executes both individual and batch modes
# ----------------------------------------------------------------------
def test_demo_mode_compare_e2e():
    result = run_evaluation(
        provider="demo",
        cases=5,
        runs=1,
        batch_size=5,
        mode="compare",
    )

    assert result["mode"] == "compare"
    assert "individual_aggregate" in result
    assert "batch_aggregate" in result
    assert "latency_reduction_percent" in result
    assert "token_reduction_percent" in result
