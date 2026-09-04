"""
Unit and integration tests for Phase 2 & 3.1 AI Investigation Agent.
"""

import json
from unittest.mock import MagicMock
import pytest
from pydantic import ValidationError

from src.agent.controller import AgentController, LLMClient, MAX_TOOL_CALLS
from src.agent.evaluator import evaluate_agent_decisions, compute_phase2_metrics
from src.agent.schemas import AgentDecision, InvestigationLog
from src.agent.tools import FinancialToolkit
from src.generator import SyntheticDataGenerator
from src.reconciliation import ReconciliationEngine


class MockFunction:
    def __init__(self, name: str, arguments: str):
        self.name = name
        self.arguments = arguments


class MockToolCall:
    def __init__(self, tool_id: str, name: str, arguments: str):
        self.id = tool_id
        self.type = "function"
        self.function = MockFunction(name, arguments)


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
def sample_toolkit_data():
    payments = [
        {"transaction_id": "TXN001", "merchant_id": "M001", "amount": 10000, "date": "2026-08-01", "status": "CAPTURED"},
        {"transaction_id": "TXN002", "merchant_id": "M002", "amount": 15000, "date": "2026-08-02", "status": "CAPTURED"},
        {"transaction_id": "TXN034", "merchant_id": "M003", "amount": 10000, "date": "2026-08-03", "status": "CAPTURED"},
    ]
    ledger = [
        {"transaction_id": "TXN001", "gross_amount": 10000, "fee": 200, "net_amount": 9800, "date": "2026-08-01", "status": "POSTED"},
        {"transaction_id": "TXN002", "gross_amount": 15000, "fee": 200, "net_amount": 14800, "date": "2026-08-02", "status": "POSTED"},
        {"transaction_id": "TXN034", "gross_amount": 10000, "fee": 200, "net_amount": 9800, "date": "2026-08-03", "status": "POSTED"},
    ]
    bank = [
        {"bank_reference": "BNK001", "transaction_id": "TXN001", "credited_amount": 9800, "date": "2026-08-01"},
        {"bank_reference": "BNK002_A", "transaction_id": "TXN002", "credited_amount": 7400, "date": "2026-08-02"},
        {"bank_reference": "BNK002_B", "transaction_id": "TXN002", "credited_amount": 7400, "date": "2026-08-02"},
        {"bank_reference": "BNK034", "transaction_id": "TXN034", "credited_amount": 9700, "date": "2026-08-03"},
    ]
    adjustments = [
        {
            "transaction_id": "TXN034",
            "adjustment_type": "BANK_PROCESSING_FEE",
            "amount": 100,
            "reason": "Processing fee charge",
            "date": "2026-08-03",
            "reference": "ADJ001",
        }
    ]
    return FinancialToolkit(payments, ledger, bank, adjustments)


# ----------------------------------------------------------------------
# Test 1: Tool returns correct transaction
# ----------------------------------------------------------------------
def test_tool_get_transaction(sample_toolkit_data):
    toolkit = sample_toolkit_data
    txn = toolkit.get_transaction("TXN001")
    assert txn["transaction_id"] == "TXN001"
    assert txn["payment"]["amount"] == 10000
    assert txn["ledger"]["gross_amount"] == 10000
    assert len(txn["bank_records"]) == 1
    assert txn["bank_records"][0]["credited_amount"] == 9800


# ----------------------------------------------------------------------
# Test 2: Tool returns duplicate bank records
# ----------------------------------------------------------------------
def test_tool_duplicate_bank_records(sample_toolkit_data):
    toolkit = sample_toolkit_data
    dup_info = toolkit.check_for_duplicates("TXN002")
    assert dup_info["is_duplicate"] is True
    assert dup_info["duplicate_count"] == 2
    assert "BNK002_A" in dup_info["bank_references"]
    assert "BNK002_B" in dup_info["bank_references"]

    bank_records = toolkit.get_bank_records("TXN002")
    assert bank_records["count"] == 2


# ----------------------------------------------------------------------
# Test 3: Settlement calculation is deterministic
# ----------------------------------------------------------------------
def test_tool_calculate_expected_settlement(sample_toolkit_data):
    toolkit = sample_toolkit_data
    settlement = toolkit.calculate_expected_settlement("TXN001")
    assert settlement["gross_amount"] == 10000
    assert settlement["fee"] == 200
    assert settlement["expected_net"] == 9800
    assert settlement["calculation"] == "10000 - 200 = 9800"


# ----------------------------------------------------------------------
# Test 4: Tool get_adjustments and calculate_adjusted_expected_settlement
# ----------------------------------------------------------------------
def test_tool_get_adjustments_and_adjusted_settlement(sample_toolkit_data):
    toolkit = sample_toolkit_data
    adj = toolkit.get_adjustments("TXN034")
    assert adj["count"] == 1
    assert adj["adjustments"][0]["amount"] == 100
    assert adj["adjustments"][0]["adjustment_type"] == "BANK_PROCESSING_FEE"

    adj_settlement = toolkit.calculate_adjusted_expected_settlement("TXN034")
    assert adj_settlement["gross_amount"] == 10000
    assert adj_settlement["fee"] == 200
    assert adj_settlement["total_adjustments"] == 100
    assert adj_settlement["adjusted_expected_net"] == 9700
    assert adj_settlement["calculation"] == "10000 - 200 - 100 = 9700"


# ----------------------------------------------------------------------
# Test 5: Agent auto-resolves a fee/adjustment explained settlement
# ----------------------------------------------------------------------
def test_agent_auto_resolves_adjustment_explained(sample_toolkit_data):
    mock_llm = MagicMock(spec=LLMClient)
    decision_json = json.dumps({
        "transaction_id": "TXN034",
        "decision": "AUTO_RESOLVED",
        "exception_type": "BANK_AMOUNT_MISMATCH",
        "resolution_type": "ADJUSTMENT_EXPLAINED",
        "resolved_difference": 100,
        "reason": "Bank amount is 100 lower than expected, and adjustment explicitly accounts for the difference.",
        "evidence": [
            "Expected settlement = 9,800",
            "Bank credit = 9,700",
            "Adjustment (BANK_PROCESSING_FEE) = 100"
        ],
        "confidence": 1.0,
        "recommended_action": "No action needed; settlement matches calculation with adjustment."
    })
    mock_llm.chat.return_value = MockResponse(MockMessage(content=decision_json))

    agent = AgentController(toolkit=sample_toolkit_data, llm_client=mock_llm)
    exception_record = {
        "transaction_id": "TXN034",
        "status": "EXCEPTION",
        "reason": "BANK_AMOUNT_MISMATCH",
        "payment_amount": 10000,
        "gross_amount": 10000,
        "fee": 200,
        "expected_net_amount": 9800,
        "bank_amount": 9700,
        "difference": 100,
    }
    decision, log = agent.investigate_exception(exception_record)

    assert decision.decision == "AUTO_RESOLVED"
    assert decision.resolution_type == "ADJUSTMENT_EXPLAINED"
    assert decision.confidence == 1.0
    assert log.decision == "AUTO_RESOLVED"


# ----------------------------------------------------------------------
# Test 6: Agent escalates unexplained amount mismatch
# ----------------------------------------------------------------------
def test_agent_escalates_unexplained_mismatch(sample_toolkit_data):
    mock_llm = MagicMock(spec=LLMClient)
    decision_json = json.dumps({
        "transaction_id": "TXN002",
        "decision": "HUMAN_REVIEW",
        "exception_type": "BANK_AMOUNT_MISMATCH",
        "resolution_type": "NONE",
        "reason": "Bank credit is lower than expected and no adjustment record explains the difference.",
        "evidence": [
            "Payment amount = 15,000",
            "Expected settlement = 14,800",
            "Bank credit = 7,400",
            "Adjustment records found: 0"
        ],
        "confidence": 0.95,
        "recommended_action": "Review bank settlement details."
    })
    mock_llm.chat.return_value = MockResponse(MockMessage(content=decision_json))

    agent = AgentController(toolkit=sample_toolkit_data, llm_client=mock_llm)
    exception_record = {
        "transaction_id": "TXN002",
        "status": "EXCEPTION",
        "reason": "BANK_AMOUNT_MISMATCH",
        "payment_amount": 15000,
        "gross_amount": 15000,
        "fee": 200,
        "expected_net_amount": 14800,
        "bank_amount": 7400,
        "difference": 7400,
    }
    decision, log = agent.investigate_exception(exception_record)

    assert decision.decision == "HUMAN_REVIEW"
    assert decision.resolution_type == "NONE"


# ----------------------------------------------------------------------
# Test 7: Malformed agent output is safely rejected and falls back
# ----------------------------------------------------------------------
def test_malformed_agent_output_rejected(sample_toolkit_data):
    mock_llm = MagicMock(spec=LLMClient)
    mock_llm.chat.return_value = MockResponse(MockMessage(content="Invalid JSON output"))

    agent = AgentController(toolkit=sample_toolkit_data, llm_client=mock_llm)
    exception_record = {
        "transaction_id": "TXN999",
        "status": "EXCEPTION",
        "reason": "UNKNOWN_ERROR",
    }
    decision, log = agent.investigate_exception(exception_record)

    assert decision.decision == "HUMAN_REVIEW"
    assert decision.confidence == 0.0


# ----------------------------------------------------------------------
# Test 8: Confidence outside 0-1 is rejected by schema validator
# ----------------------------------------------------------------------
def test_confidence_outside_range_rejected():
    with pytest.raises(ValidationError):
        AgentDecision(
            transaction_id="TXN001",
            decision="HUMAN_REVIEW",
            exception_type="TEST",
            reason="Test reason",
            evidence=["Some evidence"],
            confidence=1.5,
            recommended_action="Review",
        )


# ----------------------------------------------------------------------
# Test 9: Batch processes exceptions and computes precision and recall
# ----------------------------------------------------------------------
def test_batch_processes_and_computes_precision_recall(tmp_path):
    generator = SyntheticDataGenerator(seed=42, total_transactions=100)
    data_dir = str(tmp_path)
    p_path, l_path, b_path, a_path = generator.save_to_csv(data_dir)
    payments, ledger, bank, adjustments, ground_truth = generator.generate()

    p1_results, p1_metrics = ReconciliationEngine.reconcile_batch(p_path, l_path, b_path)
    exceptions = [r for r in p1_results if r["status"] == "EXCEPTION"]

    toolkit = FinancialToolkit(payments, ledger, bank, adjustments)

    # Use LLM client with demo mode enabled
    llm_client = LLMClient()
    agent = AgentController(toolkit=toolkit, llm_client=llm_client)

    decisions = []
    for exc in exceptions:
        d, log = agent.investigate_exception(exc)
        decisions.append(d)

    assert len(decisions) == 30

    auto_resolved_count = sum(1 for d in decisions if d.decision == "AUTO_RESOLVED")
    human_review_count = sum(1 for d in decisions if d.decision == "HUMAN_REVIEW")

    # Verify both decisions are produced in real pipeline run!
    assert auto_resolved_count > 0
    assert human_review_count > 0
    assert auto_resolved_count + human_review_count == 30

    # phase1_results must be supplied for Phase 1 to be *measured* rather than
    # assumed. Without it phase1_accuracy is None ("not measured") by design.
    eval_metrics = evaluate_agent_decisions(decisions, ground_truth, phase1_results=p1_results)
    assert eval_metrics.phase1_accuracy == 100.0
    assert eval_metrics.phase2_decision_accuracy == 100.0
    assert eval_metrics.auto_resolution_precision == 100.0
    assert eval_metrics.auto_resolution_recall == 100.0

    # The 100% above is now backed by a confusion matrix over every labelled
    # record, not by a hardcoded constant.
    assert eval_metrics.phase1_labelled_records == 100
    assert eval_metrics.phase1_true_positives == 30
    assert eval_metrics.phase1_false_positives == 0
    assert eval_metrics.phase1_false_negatives == 0
    assert eval_metrics.phase1_detection_precision == 100.0
    assert eval_metrics.phase1_detection_recall == 100.0


def test_phase1_accuracy_is_none_without_phase1_results():
    """Phase 1 accuracy is unmeasured, not 100%, when no Phase 1 rows are given."""
    from src.agent.schemas import AgentDecision

    decisions = [
        AgentDecision(
            transaction_id="TXN001",
            decision="HUMAN_REVIEW",
            exception_type="BANK_AMOUNT_MISMATCH",
            resolution_type="NONE",
            reason="r",
            evidence=["Phase 1 exception: BANK_AMOUNT_MISMATCH"],
            confidence=0.5,
            recommended_action="a",
        )
    ]
    ground_truth = [{"transaction_id": "TXN001", "expected_phase2_decision": "HUMAN_REVIEW"}]

    metrics = evaluate_agent_decisions(decisions, ground_truth)
    assert metrics.phase1_accuracy is None
    assert metrics.phase1_detection_precision is None
    assert metrics.phase1_detection_recall is None
    # Phase 2 was measurable, so it is a real number.
    assert metrics.phase2_decision_accuracy == 100.0
    # No auto-resolutions were made and none were expected: unmeasured, not perfect.
    assert metrics.auto_resolution_precision is None
    assert metrics.auto_resolution_recall is None


def test_phase1_detection_metrics_catch_false_positives_and_negatives():
    """A rule engine that mislabels records is scored as such, not assumed correct."""
    from src.agent.evaluator import compute_phase1_detection_metrics

    phase1_results = [
        {"transaction_id": "T1", "status": "EXCEPTION"},    # true positive
        {"transaction_id": "T2", "status": "EXCEPTION"},    # false positive
        {"transaction_id": "T3", "status": "RECONCILED"},   # false negative
        {"transaction_id": "T4", "status": "RECONCILED"},   # true negative
    ]
    ground_truth = [
        {"transaction_id": "T1", "is_phase1_exception": True},
        {"transaction_id": "T2", "is_phase1_exception": False},
        {"transaction_id": "T3", "is_phase1_exception": True},
        {"transaction_id": "T4", "is_phase1_exception": False},
    ]

    m = compute_phase1_detection_metrics(phase1_results, ground_truth)
    assert m["phase1_true_positives"] == 1
    assert m["phase1_false_positives"] == 1
    assert m["phase1_false_negatives"] == 1
    assert m["phase1_labelled_records"] == 4
    assert m["phase1_accuracy"] == 50.0
    assert m["phase1_detection_precision"] == 50.0
    assert m["phase1_detection_recall"] == 50.0

    # The generator's `expected_phase1_status` spelling must score identically.
    gt_alt = [
        {"transaction_id": "T1", "expected_phase1_status": "EXCEPTION"},
        {"transaction_id": "T2", "expected_phase1_status": "RECONCILED"},
        {"transaction_id": "T3", "expected_phase1_status": "EXCEPTION"},
        {"transaction_id": "T4", "expected_phase1_status": "RECONCILED"},
    ]
    assert compute_phase1_detection_metrics(phase1_results, gt_alt) == m

    # Unlabelled rows are excluded from the denominator, not counted as clean.
    unlabelled = compute_phase1_detection_metrics(phase1_results, [{"transaction_id": "T1"}])
    assert unlabelled["phase1_labelled_records"] == 0
    assert unlabelled["phase1_accuracy"] is None


# ----------------------------------------------------------------------
# Test 10: Case A - TXN003-style adjustment resolution (stops early)
# ----------------------------------------------------------------------
def test_case_a_adjustment_resolution_stops_early():
    payments = [{"transaction_id": "TXN003", "merchant_id": "M1", "amount": 14500, "date": "2026-08-01", "status": "CAPTURED"}]
    ledger = [{"transaction_id": "TXN003", "gross_amount": 14500, "fee": 290, "net_amount": 14210, "date": "2026-08-01", "status": "POSTED"}]
    bank = [{"bank_reference": "BNK003", "transaction_id": "TXN003", "credited_amount": 14110, "date": "2026-08-01"}]
    adjustments = [{"transaction_id": "TXN003", "adjustment_type": "SETTLEMENT_ADJUSTMENT", "amount": 100, "reason": "Standard fee", "date": "2026-08-01", "reference": "ADJ003"}]

    toolkit = FinancialToolkit(payments, ledger, bank, adjustments)

    # LLM simulates calling get_transaction
    mock_llm = MagicMock(spec=LLMClient)
    mock_llm.chat.return_value = MockResponse(MockMessage(
        tool_calls=[MockToolCall("call_1", "get_transaction", json.dumps({"transaction_id": "TXN003"}))]
    ))

    agent = AgentController(toolkit=toolkit, llm_client=mock_llm)
    exc = {
        "transaction_id": "TXN003",
        "status": "EXCEPTION",
        "reason": "BANK_AMOUNT_MISMATCH",
        "payment_amount": 14500,
        "gross_amount": 14500,
        "fee": 290,
        "expected_net_amount": 14210,
        "bank_amount": 14110,
        "difference": 100,
    }

    decision, log = agent.investigate_exception(exc)

    assert decision.decision == "AUTO_RESOLVED"
    assert decision.resolution_type == "ADJUSTMENT_EXPLAINED"
    assert decision.resolved_difference == 100.0
    assert decision.confidence == 1.0
    # Verified early termination: tool call count must be less than MAX_TOOL_CALLS
    assert log.tool_call_count < MAX_TOOL_CALLS
    assert log.tool_traces[0].evidence_sufficient is True


# ----------------------------------------------------------------------
# Test 11: Case B - TXN008-style gross adjustment
# ----------------------------------------------------------------------
def test_case_b_gross_adjustment():
    payments = [{"transaction_id": "TXN008", "merchant_id": "M1", "amount": 20700, "date": "2026-08-01", "status": "CAPTURED"}]
    ledger = [{"transaction_id": "TXN008", "gross_amount": 21700, "fee": 621, "net_amount": 21079, "date": "2026-08-01", "status": "POSTED"}]
    bank = [{"bank_reference": "BNK008", "transaction_id": "TXN008", "credited_amount": 20079, "date": "2026-08-01"}]
    adjustments = [{"transaction_id": "TXN008", "adjustment_type": "GROSS_INVOICE_ADJUSTMENT", "amount": 1000, "reason": "Merchant gross adjustment", "date": "2026-08-01", "reference": "ADJ008"}]

    toolkit = FinancialToolkit(payments, ledger, bank, adjustments)
    mock_llm = MagicMock(spec=LLMClient)
    mock_llm.chat.return_value = MockResponse(MockMessage(
        tool_calls=[MockToolCall("call_1", "get_transaction", json.dumps({"transaction_id": "TXN008"}))]
    ))

    agent = AgentController(toolkit=toolkit, llm_client=mock_llm)
    exc = {"transaction_id": "TXN008", "status": "EXCEPTION", "reason": "GROSS_AMOUNT_MISMATCH"}

    decision, log = agent.investigate_exception(exc)
    assert decision.decision == "AUTO_RESOLVED"
    assert decision.resolved_difference == 1000.0
    assert log.tool_call_count < MAX_TOOL_CALLS


# ----------------------------------------------------------------------
# Test 12: Case C - TXN018-style bank fee adjustment
# ----------------------------------------------------------------------
def test_case_c_bank_fee_adjustment():
    payments = [{"transaction_id": "TXN018", "merchant_id": "M1", "amount": 3900, "date": "2026-08-01", "status": "CAPTURED"}]
    ledger = [{"transaction_id": "TXN018", "gross_amount": 3900, "fee": 78, "net_amount": 3822, "date": "2026-08-01", "status": "POSTED"}]
    bank = [{"bank_reference": "BNK018", "transaction_id": "TXN018", "credited_amount": 3322, "date": "2026-08-01"}]
    adjustments = [{"transaction_id": "TXN018", "adjustment_type": "BANK_PROCESSING_FEE", "amount": 500, "reason": "Bank fee", "date": "2026-08-01", "reference": "ADJ018"}]

    toolkit = FinancialToolkit(payments, ledger, bank, adjustments)
    mock_llm = MagicMock(spec=LLMClient)
    mock_llm.chat.return_value = MockResponse(MockMessage(
        tool_calls=[MockToolCall("call_1", "get_transaction", json.dumps({"transaction_id": "TXN018"}))]
    ))

    agent = AgentController(toolkit=toolkit, llm_client=mock_llm)
    exc = {"transaction_id": "TXN018", "status": "EXCEPTION", "reason": "BANK_AMOUNT_MISMATCH"}

    decision, log = agent.investigate_exception(exc)
    assert decision.decision == "AUTO_RESOLVED"
    assert decision.resolved_difference == 500.0


# ----------------------------------------------------------------------
# Test 13: Case D - Unresolved mismatch with no adjustments
# ----------------------------------------------------------------------
def test_case_d_unresolved_mismatch():
    payments = [{"transaction_id": "TXN019", "merchant_id": "M1", "amount": 25800, "date": "2026-08-01", "status": "CAPTURED"}]
    ledger = [{"transaction_id": "TXN019", "gross_amount": 26800, "fee": 387, "net_amount": 26413, "date": "2026-08-01", "status": "POSTED"}]
    bank = [{"bank_reference": "BNK019", "transaction_id": "TXN019", "credited_amount": 25413, "date": "2026-08-01"}]
    adjustments = []

    toolkit = FinancialToolkit(payments, ledger, bank, adjustments)
    mock_llm = MagicMock(spec=LLMClient)
    # Turn 1: get_transaction
    # Turn 2: LLM produces final decision as HUMAN_REVIEW
    mock_llm.chat.side_effect = [
        MockResponse(MockMessage(tool_calls=[MockToolCall("c1", "get_transaction", json.dumps({"transaction_id": "TXN019"}))])),
        MockResponse(MockMessage(content=json.dumps({
            "decision": "HUMAN_REVIEW",
            "exception_type": "GROSS_AMOUNT_MISMATCH",
            "resolution_type": "NONE",
            "confidence": 0.95,
            "reason": "Unexplained mismatch with no adjustment record.",
            "evidence": ["Bank credit lower than expected."],
            "recommended_action": "Review bank settlement.",
        }))),
    ]

    agent = AgentController(toolkit=toolkit, llm_client=mock_llm)
    exc = {"transaction_id": "TXN019", "status": "EXCEPTION", "reason": "GROSS_AMOUNT_MISMATCH"}

    decision, log = agent.investigate_exception(exc)
    assert decision.decision == "HUMAN_REVIEW"
    assert decision.resolution_type == "NONE"


# ----------------------------------------------------------------------
# Test 14: Case E - Incorrect partial adjustment
# ----------------------------------------------------------------------
def test_case_e_incorrect_partial_adjustment():
    payments = [{"transaction_id": "TXN099", "merchant_id": "M1", "amount": 10000, "date": "2026-08-01", "status": "CAPTURED"}]
    ledger = [{"transaction_id": "TXN099", "gross_amount": 10000, "fee": 200, "net_amount": 9800, "date": "2026-08-01", "status": "POSTED"}]
    bank = [{"bank_reference": "BNK099", "transaction_id": "TXN099", "credited_amount": 9700, "date": "2026-08-01"}]  # diff is 100
    adjustments = [{"transaction_id": "TXN099", "adjustment_type": "FEE", "amount": 50, "reason": "Partial fee", "date": "2026-08-01", "reference": "ADJ099"}]  # only 50

    toolkit = FinancialToolkit(payments, ledger, bank, adjustments)
    mock_llm = MagicMock(spec=LLMClient)
    mock_llm.chat.side_effect = [
        MockResponse(MockMessage(tool_calls=[MockToolCall("c1", "get_transaction", json.dumps({"transaction_id": "TXN099"}))])),
        MockResponse(MockMessage(content=json.dumps({
            "decision": "HUMAN_REVIEW",
            "exception_type": "BANK_AMOUNT_MISMATCH",
            "resolution_type": "NONE",
            "confidence": 0.9,
            "reason": "Adjustment amount (50) does not match difference (100).",
            "evidence": ["Partial adjustment mismatch."],
            "recommended_action": "Review fee difference.",
        }))),
    ]

    agent = AgentController(toolkit=toolkit, llm_client=mock_llm)
    exc = {"transaction_id": "TXN099", "status": "EXCEPTION", "reason": "BANK_AMOUNT_MISMATCH"}

    decision, log = agent.investigate_exception(exc)
    assert decision.decision == "HUMAN_REVIEW"


# ----------------------------------------------------------------------
# Test 15: Case F - Duplicate tool call deduplication
# ----------------------------------------------------------------------
def test_case_f_duplicate_tool_calls_deduplicated():
    payments = [{"transaction_id": "TXN024", "merchant_id": "M1", "amount": 24100, "date": "2026-08-01", "status": "CAPTURED"}]
    ledger = [{"transaction_id": "TXN024", "gross_amount": 24100, "fee": 361, "net_amount": 23739, "date": "2026-08-01", "status": "POSTED"}]
    bank = [
        {"bank_reference": "BNK024_A", "transaction_id": "TXN024", "credited_amount": 23739, "date": "2026-08-01"},
        {"bank_reference": "BNK024_B", "transaction_id": "TXN024", "credited_amount": 23739, "date": "2026-08-01"},
    ]
    adjustments = []

    toolkit = FinancialToolkit(payments, ledger, bank, adjustments)
    mock_llm = MagicMock(spec=LLMClient)
    # Simulate model calling check_for_duplicates twice
    mock_llm.chat.side_effect = [
        MockResponse(MockMessage(tool_calls=[
            MockToolCall("c1", "check_for_duplicates", json.dumps({"transaction_id": "TXN024"})),
            MockToolCall("c2", "check_for_duplicates", json.dumps({"transaction_id": "TXN024"})),
        ])),
        MockResponse(MockMessage(content=json.dumps({
            "decision": "HUMAN_REVIEW",
            "exception_type": "DUPLICATE_BANK_RECORD",
            "resolution_type": "NONE",
            "confidence": 0.95,
            "reason": "Duplicate bank record confirmed.",
            "evidence": ["2 bank credits."],
            "recommended_action": "Resolve duplicate.",
        }))),
    ]

    agent = AgentController(toolkit=toolkit, llm_client=mock_llm)
    exc = {"transaction_id": "TXN024", "status": "EXCEPTION", "reason": "DUPLICATE_BANK_RECORD"}

    decision, log = agent.investigate_exception(exc)
    assert decision.decision == "HUMAN_REVIEW"
    assert log.tool_call_count == 2
    assert log.tool_traces[1].duplicate_call_prevented is True


# ----------------------------------------------------------------------
# Test 16: Case G - Tool limit fallback without sufficient evidence
# ----------------------------------------------------------------------
def test_case_g_tool_limit_fallback():
    payments = []
    ledger = []
    bank = []
    adjustments = []

    toolkit = FinancialToolkit(payments, ledger, bank, adjustments)
    mock_llm = MagicMock(spec=LLMClient)
    # Repeat tool calls up to MAX_TOOL_CALLS
    mock_llm.chat.return_value = MockResponse(MockMessage(tool_calls=[
        MockToolCall("c1", "get_transaction", json.dumps({"transaction_id": "TXN_UNKNOWN"}))
    ]))

    agent = AgentController(toolkit=toolkit, llm_client=mock_llm)
    exc = {"transaction_id": "TXN_UNKNOWN", "status": "EXCEPTION", "reason": "MISSING_LEDGER_RECORD"}

    decision, log = agent.investigate_exception(exc)
    assert decision.decision == "HUMAN_REVIEW"
    assert "maximum tool-call limit" in decision.reason
    assert decision.confidence == 0.5
    assert log.tool_call_count == MAX_TOOL_CALLS

