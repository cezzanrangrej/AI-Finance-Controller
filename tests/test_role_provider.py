"""
Unit tests for Role-Specific Provider Routing, Configuration Validation,
Sanitized Observability, and Model Interaction Counters.
"""

import io
import os
from unittest.mock import MagicMock, patch
import pytest

from src.agent.controller import AgentController, LLMClient, create_llm_client, validate_model_not_key
from src.agent.multi_agent.orchestrator import MultiAgentOrchestrator
from src.agent.multi_agent.investigator import InvestigatorAgent
from src.agent.multi_agent.verifier import VerifierAgent
from src.agent.schemas import InvestigationProposal, VerificationResult
from src.agent.tools import FinancialToolkit
from src.agent.trace import AgentTracer
from src.agent.grok_client import GrokLLMClient
from src.agent.gemini_client import GeminiLLMClient
from src.agent.openrouter_client import OpenRouterLLMClient


@pytest.fixture
def sample_toolkit():
    payments = [
        {"transaction_id": "TXN003", "merchant_id": "M001", "amount": 14500, "date": "2026-08-01", "status": "CAPTURED"},
    ]
    ledger = [
        {"transaction_id": "TXN003", "gross_amount": 14500, "fee": 290, "net_amount": 14210, "date": "2026-08-01", "status": "POSTED"},
    ]
    bank = [
        {"bank_reference": "BNK003", "transaction_id": "TXN003", "credited_amount": 14110, "date": "2026-08-01"},
    ]
    adjustments = [
        {
            "transaction_id": "TXN003",
            "adjustment_type": "SETTLEMENT_ADJUSTMENT",
            "amount": 100,
            "reason": "Adjustment charge",
            "date": "2026-08-01",
            "reference": "ADJ003",
        }
    ]
    return FinancialToolkit(payments, ledger, bank, adjustments)


# ----------------------------------------------------------------------
# Test 1: Investigator uses Grok
# ----------------------------------------------------------------------
def test_investigator_uses_grok(sample_toolkit):
    with patch.dict(os.environ, {
        "LLM_PROVIDER": "openrouter",
        "INVESTIGATOR_PROVIDER": "grok",
        "INVESTIGATOR_API_KEY": "xai-dummy-key-12345678901234567890",
        "INVESTIGATOR_MODEL": "grok-2-latest",
        "VERIFIER_PROVIDER": "demo",
    }):
        orch = MultiAgentOrchestrator(toolkit=sample_toolkit, provider="openrouter")
        assert isinstance(orch.investigator_llm, GrokLLMClient)
        assert orch.investigator_llm.model == "grok-2-latest"


# ----------------------------------------------------------------------
# Test 2: Verifier uses Gemini
# ----------------------------------------------------------------------
def test_verifier_uses_gemini(sample_toolkit):
    with patch.dict(os.environ, {
        "LLM_PROVIDER": "openrouter",
        "INVESTIGATOR_PROVIDER": "demo",
        "VERIFIER_PROVIDER": "gemini",
        "VERIFIER_API_KEY": "AIzaSyDummyKey12345678901234567890",
        "VERIFIER_MODEL": "gemini-2.5-flash",
    }):
        orch = MultiAgentOrchestrator(toolkit=sample_toolkit, provider="openrouter")
        assert isinstance(orch.verifier_llm, GeminiLLMClient)
        assert orch.verifier_llm.model == "gemini-2.5-flash"


# ----------------------------------------------------------------------
# Test 3: OpenRouter remains available for single-agent mode
# ----------------------------------------------------------------------
def test_openrouter_single_agent_mode(sample_toolkit):
    with patch.dict(os.environ, {
        "LLM_PROVIDER": "openrouter",
        "OPENROUTER_API_KEY": "sk-or-v1-dummykey12345678901234567890",
        "OPENROUTER_MODEL": "meta-llama/llama-3.3-70b-instruct",
    }):
        client = create_llm_client()
        assert isinstance(client, OpenRouterLLMClient)
        assert client.model == "meta-llama/llama-3.3-70b-instruct"


# ----------------------------------------------------------------------
# Test 4: Role-specific provider overrides default provider
# ----------------------------------------------------------------------
def test_role_specific_provider_overrides_default(sample_toolkit):
    with patch.dict(os.environ, {
        "LLM_PROVIDER": "openrouter",
        "OPENROUTER_API_KEY": "sk-or-v1-dummykey12345678901234567890",
        "OPENROUTER_MODEL": "meta-llama/llama-3.3-70b-instruct",
        "INVESTIGATOR_PROVIDER": "grok",
        "INVESTIGATOR_API_KEY": "xai-dummykey12345678901234567890",
        "INVESTIGATOR_MODEL": "grok-beta",
        "VERIFIER_PROVIDER": "gemini",
        "VERIFIER_API_KEY": "AIzaSyDummyKey12345678901234567890",
        "VERIFIER_MODEL": "gemini-2.5-flash",
    }):
        orch = MultiAgentOrchestrator(toolkit=sample_toolkit, provider="openrouter")
        assert isinstance(orch.investigator_llm, GrokLLMClient)
        assert isinstance(orch.verifier_llm, GeminiLLMClient)


# ----------------------------------------------------------------------
# Test 5: Missing Grok key fails clearly
# ----------------------------------------------------------------------
def test_missing_grok_key_raises():
    with patch.dict(os.environ, {
        "INVESTIGATOR_PROVIDER": "grok",
        "INVESTIGATOR_API_KEY": "",
        "GROK_API_KEY": "",
        "XAI_API_KEY": "",
        "INVESTIGATOR_MODEL": "grok-2-latest",
    }, clear=True):
        with pytest.raises(ValueError, match="INVESTIGATOR_API_KEY / GROK_API_KEY / XAI_API_KEY environment variable is missing"):
            GrokLLMClient()


# ----------------------------------------------------------------------
# Test 6: Missing Gemini key fails clearly
# ----------------------------------------------------------------------
def test_missing_gemini_key_raises():
    with patch.dict(os.environ, {
        "GEMINI_API_KEY": "",
    }, clear=True):
        with pytest.raises(ValueError, match="GEMINI_API_KEY environment variable is missing"):
            GeminiLLMClient(api_key="")


# ----------------------------------------------------------------------
# Test 7: Missing role model fails clearly
# ----------------------------------------------------------------------
def test_missing_role_model_raises():
    with patch.dict(os.environ, {
        "OPENROUTER_API_KEY": "sk-or-v1-dummy",
        "OPENROUTER_MODEL": "",
    }, clear=True):
        with pytest.raises(ValueError, match="OPENROUTER_MODEL is missing"):
            LLMClient(provider="openrouter", api_key="sk-or-v1-dummy", model="")


# ----------------------------------------------------------------------
# Test 8: API key cannot be used as model ID
# ----------------------------------------------------------------------
def test_api_key_as_model_id_raises_configuration_error():
    with pytest.raises(ValueError, match="ConfigurationError: GROK_MODEL appears to contain a credential"):
        validate_model_not_key("grok", "xai-0000000000000000000000000000000000000000000000000000000000000000")

    with pytest.raises(ValueError, match="ConfigurationError: GEMINI_MODEL appears to contain a credential"):
        validate_model_not_key("gemini", "AQ.0000000000000000000000000000000000000000000000000000000000000000")


# ----------------------------------------------------------------------
# Test 9: API key never appears in trace
# ----------------------------------------------------------------------
def test_api_key_never_appears_in_trace():
    buf = io.StringIO()
    tracer = AgentTracer(enabled=True, output_stream=buf)

    tracer.agent_started("Investigator", "GROK", "grok-2-latest")
    tracer._print("Trace logging with key sk-or-v1-secret1234567890 and xai-secret12345678901234567890")

    output = buf.getvalue()
    assert "sk-or-v1-secret" not in output
    assert "xai-secret" not in output
    assert "[REDACTED_API_KEY]" in output


# ----------------------------------------------------------------------
# Test 10: Provider error is sanitized
# ----------------------------------------------------------------------
def test_provider_error_is_sanitized():
    buf = io.StringIO()
    tracer = AgentTracer(enabled=True, output_stream=buf)

    tracer.provider_error("Investigator", "OPENROUTER", "400", "NOT_EVALUATED", error_type="INVALID_MODEL")

    out = buf.getvalue()
    assert "[PROVIDER ERROR | OPENROUTER]" in out
    assert "Status: 400" in out
    assert "Type: INVALID_MODEL" in out
    assert "Action: NOT_EVALUATED" in out


# ----------------------------------------------------------------------
# Test 11 & 12: Successful model interaction counter & failure handling
# ----------------------------------------------------------------------
def test_model_interaction_counter_success_and_failure(sample_toolkit):
    mock_llm_success = MagicMock()
    mock_llm_success.provider_name = "grok"
    mock_llm_success.model = "grok-2-latest"

    # Mock success chat response
    mock_msg = MagicMock()
    mock_msg.content = '{"proposed_resolution": "HUMAN_REVIEW"}'
    mock_msg.tool_calls = None
    mock_choice = MagicMock()
    mock_choice.message = mock_msg
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_llm_success.chat.return_value = mock_resp

    tracer = AgentTracer(enabled=False)
    inv = InvestigatorAgent(toolkit=sample_toolkit, llm_client=mock_llm_success, tracer=tracer)
    prop, ev, traces, state, tool_calls = inv.investigate({"transaction_id": "TXN003", "reason": "TEST"})

    assert inv.last_successful_calls == 1

    # Mock failing chat response
    mock_llm_fail = MagicMock()
    mock_llm_fail.provider_name = "grok"
    mock_llm_fail.model = "grok-2-latest"
    mock_llm_fail.chat.side_effect = RuntimeError("HTTP 400 Bad Request")

    inv_fail = InvestigatorAgent(toolkit=sample_toolkit, llm_client=mock_llm_fail, tracer=tracer)
    prop_f, ev_f, traces_f, state_f, tool_calls_f = inv_fail.investigate({"transaction_id": "TXN003", "reason": "TEST"})

    assert inv_fail.last_successful_calls == 0


# ----------------------------------------------------------------------
# Test 13: NOT_EVALUATED metrics formatting
# ----------------------------------------------------------------------
def test_not_evaluated_metrics_formatting():
    from src.agent.evaluator import compute_aggregate_metrics
    summary = {
        "cases_selected": 2,
        "cases_completed": 0,
        "cases_not_evaluated": 2,
        "correct_decisions": 0,
        "auto_resolved": 0,
        "human_review": 0,
        "phase2_time_sec": 0.0,
        "total_tokens": 0,
    }
    agg = compute_aggregate_metrics([summary])
    assert agg["total_selected"] == 2
    assert agg["total_completed"] == 0
    assert agg["total_not_evaluated"] == 2


# ----------------------------------------------------------------------
# Test 14: No verifier call when investigator provider fails
# ----------------------------------------------------------------------
def test_no_verifier_call_when_investigator_fails(sample_toolkit):
    mock_inv_llm = MagicMock()
    mock_inv_llm.provider_name = "grok"
    mock_inv_llm.model = "grok-2-latest"
    mock_inv_llm.chat.side_effect = RuntimeError("API key invalid")

    mock_ver_llm = MagicMock()
    mock_ver_llm.provider_name = "gemini"
    mock_ver_llm.model = "gemini-2.5-flash"

    with patch.dict(os.environ, {
        "INVESTIGATOR_PROVIDER": "grok",
        "VERIFIER_PROVIDER": "gemini",
    }):
        orch = MultiAgentOrchestrator(toolkit=sample_toolkit, provider="openrouter")
        orch.investigator_llm = mock_inv_llm
        orch.investigator.llm = mock_inv_llm
        orch.verifier_llm = mock_ver_llm
        orch.verifier.llm = mock_ver_llm

        decision, log = orch.investigate_exception({"transaction_id": "TXN003", "reason": "BANK_AMOUNT_MISMATCH"})

        assert decision.decision == "NOT_EVALUATED"
        assert log.verifier_calls == 0
        mock_ver_llm.chat.assert_not_called()


# ----------------------------------------------------------------------
# Test 15: Existing individual/batch modes remain functional
# ----------------------------------------------------------------------
def test_individual_and_batch_modes_unaffected(sample_toolkit):
    from src.agent.controller import AgentController, LLMClient
    from src.agent.batch_controller import BatchAgentController

    agent = AgentController(toolkit=sample_toolkit, llm_client=LLMClient(provider="demo"))
    decision, log = agent.investigate_exception({"transaction_id": "TXN003", "reason": "BANK_AMOUNT_MISMATCH"})
    assert decision.decision in ("AUTO_RESOLVED", "HUMAN_REVIEW")

    batch_agent = BatchAgentController(toolkit=sample_toolkit, llm_client=LLMClient(provider="demo"))
    decisions, b_log = batch_agent.investigate_batch([{"transaction_id": "TXN003", "reason": "BANK_AMOUNT_MISMATCH"}])
    assert len(decisions) == 1
