"""
Unit and integration tests for Unified Batch Multi-Agent Mode (BatchMultiAgentController).
"""

import json
from unittest.mock import MagicMock
import pytest

from src.agent.multi_agent.batch_multi_agent_controller import BatchMultiAgentController
from src.agent.controller import LLMClient
from src.agent.schemas import AgentDecision
from src.agent.tools import FinancialToolkit
from src.generator import SyntheticDataGenerator
from src.reconciliation import ReconciliationEngine


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
def sample_multi_agent_toolkit_and_exceptions(tmp_path):
    generator = SyntheticDataGenerator(seed=42, total_transactions=100)
    data_dir = str(tmp_path)
    p_path, l_path, b_path, a_path = generator.save_to_csv(data_dir)
    payments, ledger, bank, adjustments, ground_truth = generator.generate()
    toolkit = FinancialToolkit(payments, ledger, bank, adjustments)

    p1_results, _ = ReconciliationEngine.reconcile_batch(p_path, l_path, b_path)
    exceptions = [r for r in p1_results if r["status"] == "EXCEPTION"]

    return toolkit, exceptions, ground_truth


def test_batch_multi_agent_demo_mode(sample_multi_agent_toolkit_and_exceptions):
    """Verifies that BatchMultiAgentController runs in demo mode without errors."""
    toolkit, exceptions, _ = sample_multi_agent_toolkit_and_exceptions
    batch_5 = exceptions[:5]

    controller = BatchMultiAgentController(toolkit=toolkit, provider="demo")
    decisions, log = controller.investigate_batch(batch_5)

    assert len(decisions) == 5
    assert all(isinstance(d, AgentDecision) for d in decisions)
    assert log.batch_size == 5
    assert log.llm_interactions == 2


def test_batch_multi_agent_consensus_auto_resolved(sample_multi_agent_toolkit_and_exceptions):
    """Verifies consensus when both Investigator and Verifier agree on AUTO_RESOLVED."""
    toolkit, exceptions, _ = sample_multi_agent_toolkit_and_exceptions
    batch = [exceptions[0]]
    txn_id = batch[0]["transaction_id"]

    controller = BatchMultiAgentController(toolkit=toolkit, provider="demo")

    # Mock Investigator LLM
    mock_inv_llm = MagicMock(spec=LLMClient)
    mock_inv_resp = {
        "proposals": [
            {
                "transaction_id": txn_id,
                "proposed_resolution": "AUTO_RESOLVED",
                "exception_type": batch[0].get("reason", "UNKNOWN"),
                "resolution_type": "ADJUSTMENT_EXPLAINED",
                "resolved_difference": 50.0,
                "reason": "Documented fee adjustment matches discrepancy.",
                "evidence": ["Adjustment record matched."],
                "confidence": 0.95,
                "recommended_action": "Apply adjustment record.",
            }
        ]
    }
    mock_inv_llm.chat.return_value = MockResponse(MockMessage(json.dumps(mock_inv_resp)))

    # Mock Verifier LLM
    mock_ver_llm = MagicMock(spec=LLMClient)
    mock_ver_resp = {
        "verifications": [
            {
                "transaction_id": txn_id,
                "verified": True,
                "decision": "AUTO_RESOLVED",
                "reason": "Independent verification confirmed math matches.",
                "evidence_references": ["Adjusted settlement verified."],
                "contradictions": [],
                "confidence": 0.98,
            }
        ]
    }
    mock_ver_llm.chat.return_value = MockResponse(MockMessage(json.dumps(mock_ver_resp)))

    controller.investigator_llm = mock_inv_llm
    controller.verifier_llm = mock_ver_llm

    decisions, log = controller.investigate_batch(batch)

    assert len(decisions) == 1
    assert decisions[0].decision == "AUTO_RESOLVED"
    assert decisions[0].resolution_type == "ADJUSTMENT_EXPLAINED"
    assert decisions[0].confidence >= 0.95



def test_batch_multi_agent_verifier_escalation(sample_multi_agent_toolkit_and_exceptions):
    """Verifies escalation to HUMAN_REVIEW when Verifier rejects Investigator's AUTO_RESOLVED."""
    toolkit, exceptions, _ = sample_multi_agent_toolkit_and_exceptions
    # Select an exception without valid adjustments so deterministic proof doesn't auto-resolve
    unresolved_exc = next(e for e in exceptions if e.get("reason") == "MISSING_BANK_RECORD")
    batch = [unresolved_exc]
    txn_id = batch[0]["transaction_id"]

    controller = BatchMultiAgentController(toolkit=toolkit, provider="demo")

    mock_inv_llm = MagicMock(spec=LLMClient)
    mock_inv_resp = {
        "proposals": [
            {
                "transaction_id": txn_id,
                "proposed_resolution": "AUTO_RESOLVED",
                "exception_type": unresolved_exc.get("reason", "UNKNOWN"),
                "resolution_type": "ADJUSTMENT_EXPLAINED",
                "resolved_difference": 10.0,
                "reason": "Investigator claimed adjustment.",
                "evidence": ["Claimed adjustment."],
                "confidence": 0.8,
                "recommended_action": "Apply adjustment.",
            }
        ]
    }
    mock_inv_llm.chat.return_value = MockResponse(MockMessage(json.dumps(mock_inv_resp)))

    mock_ver_llm = MagicMock(spec=LLMClient)
    mock_ver_resp = {
        "verifications": [
            {
                "transaction_id": txn_id,
                "verified": False,
                "decision": "HUMAN_REVIEW",
                "reason": "Missing bank record cannot be resolved by adjustment.",
                "evidence_references": ["Bank statement missing."],
                "contradictions": ["No bank credit found."],
                "confidence": 0.95,
            }
        ]
    }
    mock_ver_llm.chat.return_value = MockResponse(MockMessage(json.dumps(mock_ver_resp)))

    controller.investigator_llm = mock_inv_llm
    controller.verifier_llm = mock_ver_llm

    decisions, log = controller.investigate_batch(batch)

    assert len(decisions) == 1
    assert decisions[0].decision == "HUMAN_REVIEW"
    assert "Verifier escalated to human review" in decisions[0].reason


def test_batch_multi_agent_deterministic_proof_override(sample_multi_agent_toolkit_and_exceptions):
    """Verifies that authoritative Python decimal proof overrides LLM hesitation."""
    toolkit, exceptions, _ = sample_multi_agent_toolkit_and_exceptions
    # Pick a case with valid adjustment
    adj_exc = next((e for e in exceptions if e.get("reason") == "BANK_AMOUNT_MISMATCH" and toolkit.get_adjustments(e.get("transaction_id")).get("adjustments")), exceptions[0])
    batch = [adj_exc]
    txn_id = batch[0]["transaction_id"]

    controller = BatchMultiAgentController(toolkit=toolkit, provider="demo")

    # Both LLMs hesitate or say HUMAN_REVIEW
    mock_inv_llm = MagicMock(spec=LLMClient)
    mock_inv_resp = {
        "proposals": [
            {
                "transaction_id": txn_id,
                "proposed_resolution": "HUMAN_REVIEW",
                "exception_type": adj_exc.get("reason", "UNKNOWN"),
                "reason": "Hesitant LLM proposal.",
                "confidence": 0.5,
            }
        ]
    }
    mock_inv_llm.chat.return_value = MockResponse(MockMessage(json.dumps(mock_inv_resp)))

    mock_ver_llm = MagicMock(spec=LLMClient)
    mock_ver_resp = {
        "verifications": [
            {
                "transaction_id": txn_id,
                "verified": False,
                "decision": "HUMAN_REVIEW",
                "reason": "Hesitant Verifier review.",
                "confidence": 0.5,
            }
        ]
    }
    mock_ver_llm.chat.return_value = MockResponse(MockMessage(json.dumps(mock_ver_resp)))

    controller.investigator_llm = mock_inv_llm
    controller.verifier_llm = mock_ver_llm

    decisions, log = controller.investigate_batch(batch)

    assert len(decisions) == 1
    # If the case has deterministic proof in toolkit, it overrides to AUTO_RESOLVED
    adjs = toolkit.get_adjustments(txn_id).get("adjustments", [])
    if adjs:
        assert decisions[0].decision == "AUTO_RESOLVED"
        assert decisions[0].confidence == 1.0
