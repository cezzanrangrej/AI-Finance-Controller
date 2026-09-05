"""
Unit and integration tests for Unified Batch Multi-Agent Mode (BatchMultiAgentController).
"""

import json
from unittest.mock import MagicMock
import pytest

from src.agent.multi_agent.batch_multi_agent_controller import BatchMultiAgentController
from src.agent.batch_partitioner import partition_exceptions_balanced
from src.agent.controller import LLMClient
from src.agent.pre_filter import prefilter_proven_exceptions
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


def test_provable_case_never_reaches_batch_controller(sample_multi_agent_toolkit_and_exceptions):
    """
    The deterministic pre-filter runs before batch partitioning, so an exception
    an adjustment record already explains is resolved in Python and is absent
    from every batch handed to the controller.

    This is the contract that removing the controller's post-LLM proof override
    depends on: if a provable case could still reach a batch, the override would
    still be needed.
    """
    toolkit, exceptions, _ = sample_multi_agent_toolkit_and_exceptions

    result = prefilter_proven_exceptions(exceptions, toolkit)

    assert result.pre_resolved_count > 0, "fixture must contain at least one provable exception"
    assert result.total == len(exceptions), "every exception must be accounted for exactly once"

    proven_ids = {d.transaction_id for d in result.proven_decisions}
    forwarded_ids = {e["transaction_id"] for e in result.ambiguous_exceptions}
    assert proven_ids.isdisjoint(forwarded_ids)

    batches = partition_exceptions_balanced(result.ambiguous_exceptions, batch_size=5)
    batched_ids = {c["transaction_id"] for b in batches for c in b}
    assert batched_ids == forwarded_ids
    assert proven_ids.isdisjoint(batched_ids)

    for d in result.proven_decisions:
        assert d.decision == "AUTO_RESOLVED"
        assert d.resolution_source == "DETERMINISTIC_PROOF"
        assert d.model_interactions == 0


def test_batch_controller_does_not_override_agents_with_proof(sample_multi_agent_toolkit_and_exceptions):
    """
    A provable case is forced through the controller anyway (which the pipeline
    never does) to pin the removal of the legacy Step 4 override: the agents'
    verdict now stands, unmodified by arithmetic.
    """
    toolkit, exceptions, _ = sample_multi_agent_toolkit_and_exceptions

    # Select a case the pre-filter proves, so the old override would have fired.
    pre_filter = prefilter_proven_exceptions(exceptions, toolkit)
    assert pre_filter.pre_resolved_count > 0
    proven_id = pre_filter.proven_decisions[0].transaction_id
    adj_exc = next(e for e in exceptions if e["transaction_id"] == proven_id)
    batch = [adj_exc]
    txn_id = proven_id

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
    # Arithmetic no longer speaks here: the agents agreed on HUMAN_REVIEW and that
    # is what comes out, even though the case is provable.
    assert decisions[0].decision == "HUMAN_REVIEW"
    assert decisions[0].resolution_source == "MULTI_AGENT_CONSENSUS"
    assert decisions[0].resolution_source != "DETERMINISTIC_PROOF"
