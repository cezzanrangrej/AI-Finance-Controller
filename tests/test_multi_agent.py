"""
Unit and integration tests for the Controlled Multi-Agent Investigation Layer.
Tests cover Investigator, Verifier, Orchestrator, Disagreement Policy, and Safety Guardrails.
"""

import json
from unittest.mock import MagicMock, patch
import pytest

from src.agent.controller import AgentController, LLMClient, MAX_TOOL_CALLS
from src.agent.multi_agent.investigator import InvestigatorAgent
from src.agent.multi_agent.orchestrator import MultiAgentOrchestrator
from src.agent.multi_agent.verifier import VerifierAgent
from src.agent.schemas import AgentDecision, InvestigationProposal, VerificationResult
from src.agent.tools import FinancialToolkit
from src.generator import SyntheticDataGenerator
from src.reconciliation import ReconciliationEngine
from src.run_llm_eval import run_evaluation


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
# Test 1: Investigator selects tools
# ----------------------------------------------------------------------
def test_investigator_selects_tools(sample_toolkit_data):
    mock_llm = MagicMock(spec=LLMClient)
    # Simulate LLM choosing get_transaction and get_adjustments
    mock_llm.chat.side_effect = [
        MockResponse(MockMessage(tool_calls=[MockToolCall("c1", "get_transaction", json.dumps({"transaction_id": "TXN034"}))])),
    ]

    investigator = InvestigatorAgent(toolkit=sample_toolkit_data, llm_client=mock_llm, max_tool_calls=5)
    exc = {"transaction_id": "TXN034", "reason": "BANK_AMOUNT_MISMATCH"}
    proposal, ev, traces, state, count = investigator.investigate(exc)

    assert count >= 1
    assert any(t.tool_name == "get_transaction" for t in traces)
    assert proposal.transaction_id == "TXN034"


# ----------------------------------------------------------------------
# Test 2: Investigator produces structured evidence
# ----------------------------------------------------------------------
def test_investigator_produces_structured_evidence(sample_toolkit_data):
    mock_llm = MagicMock(spec=LLMClient)
    proposal_json = json.dumps({
        "transaction_id": "TXN002",
        "exception_type": "BANK_AMOUNT_MISMATCH",
        "evidence": ["Bank credit 7,400 < Expected 14,800"],
        "proposed_resolution": "HUMAN_REVIEW",
        "resolution_type": "NONE",
        "confidence": 0.95,
        "unresolved_questions": ["Where is the remainder?"],
        "tool_history": ["get_transaction"],
        "reason": "Unexplained difference",
        "recommended_action": "Review with bank",
    })
    mock_llm.chat.return_value = MockResponse(MockMessage(content=proposal_json))

    investigator = InvestigatorAgent(toolkit=sample_toolkit_data, llm_client=mock_llm)
    exc = {"transaction_id": "TXN002", "reason": "BANK_AMOUNT_MISMATCH"}
    proposal, ev, traces, state, count = investigator.investigate(exc)

    assert isinstance(proposal, InvestigationProposal)
    assert proposal.proposed_resolution == "HUMAN_REVIEW"
    assert len(proposal.evidence) > 0
    assert proposal.confidence == 0.95


# ----------------------------------------------------------------------
# Test 3: Verifier independently checks evidence
# ----------------------------------------------------------------------
def test_verifier_independently_checks_evidence():
    mock_llm = MagicMock(spec=LLMClient)
    ver_json = json.dumps({
        "transaction_id": "TXN034",
        "verified": True,
        "decision": "AUTO_RESOLVED",
        "reason": "Calculations strictly match documented adjustment.",
        "evidence_references": ["Adjusted expected net = 9,700 matches bank credit"],
        "contradictions": [],
        "confidence": 1.0,
    })
    mock_llm.chat.return_value = MockResponse(MockMessage(content=ver_json))

    verifier = VerifierAgent(llm_client=mock_llm)
    state = MagicMock()
    state.transaction_id = "TXN034"
    state.expected_settlement = None
    state.adjusted_expected_settlement = None
    state.adjustments = []
    state.duplicate_check = None
    state.bank_records = []
    state.ledger = None

    proposal = InvestigationProposal(
        transaction_id="TXN034",
        exception_type="BANK_AMOUNT_MISMATCH",
        evidence=["Documented adjustment found."],
        proposed_resolution="AUTO_RESOLVED",
        confidence=1.0,
    )

    result = verifier.verify(
        exception_record={"transaction_id": "TXN034", "reason": "BANK_AMOUNT_MISMATCH"},
        source_evidence=["Documented adjustment found."],
        evidence_state=state,
        proposal=proposal,
    )

    assert isinstance(result, VerificationResult)
    assert result.verified is True
    assert result.decision == "AUTO_RESOLVED"


# ----------------------------------------------------------------------
# Test 4: Both agents agree -> AUTO_RESOLVED
# ----------------------------------------------------------------------
def test_both_agents_agree_auto_resolved(sample_toolkit_data):
    orchestrator = MultiAgentOrchestrator(toolkit=sample_toolkit_data, provider="demo")

    exc = {
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

    decision, log = orchestrator.investigate_exception(exc)
    assert decision.decision == "AUTO_RESOLVED"
    assert decision.resolution_type == "ADJUSTMENT_EXPLAINED"
    assert log.decision == "AUTO_RESOLVED"
    assert log.agent_mode == "MULTI_AGENT"


# ----------------------------------------------------------------------
# Test 5: Investigator AUTO_RESOLVED + Verifier HUMAN_REVIEW -> HUMAN_REVIEW
# ----------------------------------------------------------------------
def test_disagreement_investigator_auto_verifier_human(sample_toolkit_data):
    mock_inv_llm = MagicMock(spec=LLMClient)
    mock_ver_llm = MagicMock(spec=LLMClient)

    # Investigator says AUTO_RESOLVED (without deterministic equality)
    inv_json = json.dumps({
        "transaction_id": "TXN_DISAGREE_1",
        "exception_type": "BANK_AMOUNT_MISMATCH",
        "evidence": ["Unverified claim of fee adjustment"],
        "proposed_resolution": "AUTO_RESOLVED",
        "confidence": 0.8,
    })
    mock_inv_llm.chat.return_value = MockResponse(MockMessage(content=inv_json))

    # Verifier says HUMAN_REVIEW (flags insufficient proof)
    ver_json = json.dumps({
        "transaction_id": "TXN_DISAGREE_1",
        "verified": False,
        "decision": "HUMAN_REVIEW",
        "reason": "No valid adjustment record in database.",
        "contradictions": ["Missing adjustment evidence."],
        "confidence": 0.95,
    })
    mock_ver_llm.chat.return_value = MockResponse(MockMessage(content=ver_json))

    orchestrator = MultiAgentOrchestrator(toolkit=sample_toolkit_data, provider="demo")
    orchestrator.investigator = InvestigatorAgent(toolkit=sample_toolkit_data, llm_client=mock_inv_llm)
    orchestrator.verifier = VerifierAgent(llm_client=mock_ver_llm)

    exc = {"transaction_id": "TXN_DISAGREE_1", "reason": "BANK_AMOUNT_MISMATCH"}
    decision, log = orchestrator.investigate_exception(exc)

    # Safe conservative escalation to HUMAN_REVIEW
    assert decision.decision == "HUMAN_REVIEW"
    assert log.disagreement_detected is True
    assert log.resolution_source == "VERIFIER_ESCALATION"


# ----------------------------------------------------------------------
# Test 6: Investigator HUMAN_REVIEW + Verifier AUTO_RESOLVED -> deterministic proof required
# ----------------------------------------------------------------------
def test_disagreement_investigator_human_verifier_auto_no_proof(sample_toolkit_data):
    mock_inv_llm = MagicMock(spec=LLMClient)
    mock_ver_llm = MagicMock(spec=LLMClient)

    inv_json = json.dumps({
        "transaction_id": "TXN_DISAGREE_2",
        "exception_type": "BANK_AMOUNT_MISMATCH",
        "evidence": ["Discrepancy found"],
        "proposed_resolution": "HUMAN_REVIEW",
        "confidence": 0.9,
    })
    mock_inv_llm.chat.return_value = MockResponse(MockMessage(content=inv_json))

    # Verifier incorrectly proposes AUTO_RESOLVED without proof
    ver_json = json.dumps({
        "transaction_id": "TXN_DISAGREE_2",
        "verified": False,
        "decision": "AUTO_RESOLVED",
        "reason": "Speculative fee match",
        "confidence": 0.7,
    })
    mock_ver_llm.chat.return_value = MockResponse(MockMessage(content=ver_json))

    orchestrator = MultiAgentOrchestrator(toolkit=sample_toolkit_data, provider="demo")
    orchestrator.investigator = InvestigatorAgent(toolkit=sample_toolkit_data, llm_client=mock_inv_llm)
    orchestrator.verifier = VerifierAgent(llm_client=mock_ver_llm)

    exc = {"transaction_id": "TXN_DISAGREE_2", "reason": "BANK_AMOUNT_MISMATCH"}
    decision, log = orchestrator.investigate_exception(exc)

    # Without objective deterministic proof, defaults safely to HUMAN_REVIEW
    assert decision.decision == "HUMAN_REVIEW"
    assert log.disagreement_detected is True


# ----------------------------------------------------------------------
# Test 7: Deterministic proof overrides disagreement
# ----------------------------------------------------------------------
def test_deterministic_proof_overrides_disagreement(sample_toolkit_data):
    mock_ver_llm = MagicMock(spec=LLMClient)
    ver_json = json.dumps({
        "transaction_id": "TXN034",
        "verified": False,
        "decision": "HUMAN_REVIEW",
        "reason": "Skeptical verification",
        "confidence": 0.5,
    })
    mock_ver_llm.chat.return_value = MockResponse(MockMessage(content=ver_json))

    orchestrator = MultiAgentOrchestrator(toolkit=sample_toolkit_data, provider="demo")
    orchestrator.verifier = VerifierAgent(llm_client=mock_ver_llm)

    exc = {
        "transaction_id": "TXN034",
        "reason": "BANK_AMOUNT_MISMATCH",
        "expected_net_amount": 9800,
        "bank_amount": 9700,
        "difference": 100,
    }
    decision, log = orchestrator.investigate_exception(exc)

    # Deterministic proof (expected 9800 - adjustment 100 == bank 9700) proves AUTO_RESOLVED
    assert decision.decision == "AUTO_RESOLVED"
    assert decision.resolution_type == "ADJUSTMENT_EXPLAINED"
    assert log.resolution_source == "DETERMINISTIC_EVIDENCE"


# ----------------------------------------------------------------------
# Test 8: No sufficient evidence -> HUMAN_REVIEW
# ----------------------------------------------------------------------
def test_no_sufficient_evidence_human_review(sample_toolkit_data):
    orchestrator = MultiAgentOrchestrator(toolkit=sample_toolkit_data, provider="demo")

    exc = {
        "transaction_id": "TXN002",
        "reason": "BANK_AMOUNT_MISMATCH",
        "payment_amount": 15000,
        "expected_net_amount": 14800,
        "bank_amount": 7400,
        "difference": 7400,
    }
    decision, log = orchestrator.investigate_exception(exc)

    assert decision.decision == "HUMAN_REVIEW"
    assert log.decision == "HUMAN_REVIEW"


# ----------------------------------------------------------------------
# Test 9: Malformed Investigator response handled safely
# ----------------------------------------------------------------------
def test_malformed_investigator_response(sample_toolkit_data):
    mock_inv_llm = MagicMock(spec=LLMClient)
    mock_inv_llm.chat.return_value = MockResponse(MockMessage(content="NOT_VALID_JSON_AT_ALL"))

    investigator = InvestigatorAgent(toolkit=sample_toolkit_data, llm_client=mock_inv_llm)
    exc = {"transaction_id": "TXN999", "reason": "BANK_AMOUNT_MISMATCH"}
    proposal, ev, traces, state, count = investigator.investigate(exc)

    assert proposal.proposed_resolution == "HUMAN_REVIEW"
    assert proposal.confidence == 0.0
    assert "parse error" in proposal.reason.lower()


# ----------------------------------------------------------------------
# Test 10: Malformed Verifier response handled safely
# ----------------------------------------------------------------------
def test_malformed_verifier_response(sample_toolkit_data):
    mock_ver_llm = MagicMock(spec=LLMClient)
    mock_ver_llm.chat.return_value = MockResponse(MockMessage(content="MALFORMED_OUTPUT"))

    verifier = VerifierAgent(llm_client=mock_ver_llm)
    state = MagicMock()
    state.transaction_id = "TXN999"
    state.expected_settlement = None
    state.adjusted_expected_settlement = None
    state.adjustments = []
    state.duplicate_check = None
    state.bank_records = []
    state.ledger = None

    proposal = InvestigationProposal(
        transaction_id="TXN999",
        exception_type="TEST",
        proposed_resolution="AUTO_RESOLVED",
        confidence=0.9,
    )

    res = verifier.verify({"transaction_id": "TXN999"}, [], state, proposal)
    assert res.verified is False
    assert res.decision == "HUMAN_REVIEW"
    assert res.confidence == 0.0


# ----------------------------------------------------------------------
# Test 11: Provider failure -> NOT_EVALUATED
# ----------------------------------------------------------------------
def test_provider_failure_not_evaluated(sample_toolkit_data):
    mock_inv_llm = MagicMock(spec=LLMClient)
    mock_inv_llm.chat.side_effect = ConnectionError("OpenRouter 503 Service Unavailable")

    orchestrator = MultiAgentOrchestrator(toolkit=sample_toolkit_data, provider="demo")
    orchestrator.investigator = InvestigatorAgent(toolkit=sample_toolkit_data, llm_client=mock_inv_llm)

    exc = {"transaction_id": "TXN002", "reason": "BANK_AMOUNT_MISMATCH"}
    decision, log = orchestrator.investigate_exception(exc)

    assert decision.decision == "NOT_EVALUATED"
    assert "Provider request failed" in decision.reason
    assert log.resolution_source == "PROVIDER_ERROR"


# ----------------------------------------------------------------------
# Test 12: Tool limit enforced
# ----------------------------------------------------------------------
def test_max_tool_calls_limit(sample_toolkit_data):
    mock_llm = MagicMock(spec=LLMClient)
    mock_llm.chat.return_value = MockResponse(MockMessage(tool_calls=[
        MockToolCall("c", "get_transaction", json.dumps({"transaction_id": "TXN002"}))
    ]))

    investigator = InvestigatorAgent(toolkit=sample_toolkit_data, llm_client=mock_llm, max_tool_calls=5)
    exc = {"transaction_id": "TXN002", "reason": "BANK_AMOUNT_MISMATCH"}
    proposal, ev, traces, state, count = investigator.investigate(exc)

    assert count == 5
    assert proposal.proposed_resolution == "HUMAN_REVIEW"


# ----------------------------------------------------------------------
# Test 13: Investigator tool deduplication
# ----------------------------------------------------------------------
def test_investigator_tool_deduplication(sample_toolkit_data):
    mock_llm = MagicMock(spec=LLMClient)
    mock_llm.chat.side_effect = [
        MockResponse(MockMessage(tool_calls=[
            MockToolCall("c1", "check_for_duplicates", json.dumps({"transaction_id": "TXN002"})),
            MockToolCall("c2", "check_for_duplicates", json.dumps({"transaction_id": "TXN002"})),
        ])),
        MockResponse(MockMessage(content=json.dumps({
            "transaction_id": "TXN002",
            "exception_type": "DUPLICATE_BANK_RECORD",
            "proposed_resolution": "HUMAN_REVIEW",
            "confidence": 0.95,
        }))),
    ]

    investigator = InvestigatorAgent(toolkit=sample_toolkit_data, llm_client=mock_llm)
    exc = {"transaction_id": "TXN002", "reason": "DUPLICATE_BANK_RECORD"}
    _, _, traces, _, count = investigator.investigate(exc)

    assert count == 2
    assert traces[1].duplicate_call_prevented is True


# ----------------------------------------------------------------------
# Test 14: No recursive agent spawning
# ----------------------------------------------------------------------
def test_no_recursive_agent_spawning():
    # Verify agents have fixed bounded references without self-instantiation
    investigator = InvestigatorAgent(toolkit=MagicMock(), llm_client=MagicMock())
    assert not hasattr(investigator, "spawn_agent")
    verifier = VerifierAgent(llm_client=MagicMock())
    assert not hasattr(verifier, "spawn_agent")


# ----------------------------------------------------------------------
# Test 15: Maximum multi-agent steps bounded
# ----------------------------------------------------------------------
def test_max_multi_agent_steps_safety(sample_toolkit_data):
    orchestrator = MultiAgentOrchestrator(toolkit=sample_toolkit_data, provider="demo", max_tool_calls=3)
    assert orchestrator.investigator.max_tool_calls == 3


# ----------------------------------------------------------------------
# Test 16: Provider selection
# ----------------------------------------------------------------------
def test_provider_selection(sample_toolkit_data):
    orch_demo = MultiAgentOrchestrator(toolkit=sample_toolkit_data, provider="demo")
    assert orch_demo.provider == "demo"


# ----------------------------------------------------------------------
# Test 17: Separate model configuration
# ----------------------------------------------------------------------
def test_separate_model_configuration(sample_toolkit_data):
    with patch.dict("os.environ", {"INVESTIGATOR_MODEL": "meta-llama/llama-3.3-70b-instruct", "VERIFIER_MODEL": "gemini-2.5-flash"}):
        orch = MultiAgentOrchestrator(toolkit=sample_toolkit_data, provider="demo")
        assert getattr(orch.investigator_llm, "model", None) == "meta-llama/llama-3.3-70b-instruct"
        assert getattr(orch.verifier_llm, "model", None) == "gemini-2.5-flash"


# ----------------------------------------------------------------------
# Test 18: Audit trail records multi-agent metadata
# ----------------------------------------------------------------------
def test_audit_trail_fields(sample_toolkit_data):
    orchestrator = MultiAgentOrchestrator(toolkit=sample_toolkit_data, provider="demo")
    exc = {"transaction_id": "TXN034", "reason": "BANK_AMOUNT_MISMATCH"}
    decision, log = orchestrator.investigate_exception(exc)

    assert log.agent_mode == "MULTI_AGENT"
    assert log.investigator_proposal is not None
    assert log.investigator_calls >= 1
    assert log.model_interactions >= 1


# ----------------------------------------------------------------------
# Test 19: Token and latency tracking
# ----------------------------------------------------------------------
def test_token_and_latency_tracking(tmp_path):
    result = run_evaluation(
        provider="demo",
        cases=5,
        runs=1,
        mode="multi-agent",
    )

    assert result["mode"] == "multi-agent"
    assert result["completed"] == 5
    assert result["aggregate_accuracy"] == 1.0
    assert "investigator_calls" in result["per_run_summaries"][0]
    assert "verifier_calls" in result["per_run_summaries"][0]


# ----------------------------------------------------------------------
# Test 20: Existing individual and batch modes unaffected
# ----------------------------------------------------------------------
def test_existing_individual_and_batch_modes_unaffected(sample_toolkit_data):
    # Test Individual Controller
    agent = AgentController(toolkit=sample_toolkit_data, llm_client=LLMClient(provider="demo"))
    dec, log = agent.investigate_exception({"transaction_id": "TXN034", "reason": "BANK_AMOUNT_MISMATCH"})
    assert dec.decision == "AUTO_RESOLVED"

    # Test Batch evaluation in demo mode
    batch_res = run_evaluation(provider="demo", cases=5, mode="batch")
    assert batch_res["completed"] == 5
    assert batch_res["aggregate_accuracy"] == 1.0
