"""
Unit tests for the LLM Provider abstraction layer (Gemini & Demo providers).
"""

import os
import pytest
from unittest.mock import MagicMock, patch

from src.agent.controller import AgentController, DemoLLMClient, LLMClient, MAX_TOOL_CALLS
from src.agent.gemini_client import GeminiLLMClient
from src.agent.schemas import AgentDecision


# 1. Demo provider initializes
def test_demo_provider_initialization():
    client = LLMClient(provider="demo")
    assert isinstance(client, DemoLLMClient)
    assert client.provider == "demo"
    assert client.mode == "DEMO"
    assert client.demo_mode is True


# 2. Gemini provider refuses to initialize without API key
def test_gemini_provider_refuses_without_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    with pytest.raises(ValueError) as excinfo:
        LLMClient(provider="gemini", api_key="")
    assert "GEMINI_API_KEY" in str(excinfo.value)


# 2b. Centralized config loader tests
def test_config_env_loading(monkeypatch):
    from src.config import get_gemini_api_key, get_llm_provider, get_gemini_model, is_gemini_key_configured
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test_secret_key_12345")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")

    assert get_llm_provider() == "gemini"
    assert get_gemini_api_key() == "test_secret_key_12345"
    assert get_gemini_model() == "gemini-2.5-flash"
    assert is_gemini_key_configured() is True


def test_secret_is_never_exposed_in_client_repr(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "secret_api_key_must_not_appear_in_logs")
    client = GeminiLLMClient(api_key="secret_api_key_must_not_appear_in_logs")
    representation = str(client) + repr(client)
    assert "secret_api_key_must_not_appear_in_logs" not in representation



# 3. Gemini provider reads model from environment
def test_gemini_provider_reads_model_from_env(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test_mock_key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash-test")
    client = LLMClient(provider="gemini", api_key="test_mock_key")
    assert isinstance(client, GeminiLLMClient)
    assert client.model == "gemini-2.5-flash-test"


# 4. Provider selection chooses Demo correctly
def test_provider_selection_chooses_demo(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "demo")
    client = LLMClient()
    assert isinstance(client, DemoLLMClient)
    assert client.provider == "demo"


# 5. Provider selection chooses Gemini correctly when key available
def test_provider_selection_chooses_gemini(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test_mock_key")
    client = LLMClient()
    assert isinstance(client, GeminiLLMClient)
    assert client.provider == "gemini"


# 6. Unknown provider produces a clear configuration error
def test_unknown_provider_raises_error():
    with pytest.raises(ValueError) as excinfo:
        LLMClient(provider="unsupported_llm_provider")
    assert "Unsupported LLM_PROVIDER" in str(excinfo.value)


# 7. Gemini failure returns NOT_EVALUATED at investigation level
def test_gemini_failure_returns_not_evaluated(sample_toolkit_data):
    mock_gemini = MagicMock(spec=GeminiLLMClient)
    mock_gemini.chat.side_effect = RuntimeError("Gemini API connection error")

    agent = AgentController(toolkit=sample_toolkit_data, llm_client=mock_gemini)
    exception_record = {
        "transaction_id": "TXN_FAIL_001",
        "status": "EXCEPTION",
        "reason": "BANK_AMOUNT_MISMATCH",
    }
    decision, log = agent.investigate_exception(exception_record)

    assert decision.decision == "NOT_EVALUATED"
    assert "Provider request failed" in decision.reason or "Gemini API connection error" in decision.reason
    assert log.decision == "NOT_EVALUATED"


# 8. Malformed Gemini response is rejected and produces HUMAN_REVIEW
def test_malformed_gemini_response_rejected(sample_toolkit_data):
    mock_gemini = MagicMock()
    mock_choice = MagicMock()
    mock_message = MagicMock()
    mock_message.content = "INVALID_NON_JSON_RESPONSE"
    mock_message.tool_calls = None
    mock_choice.message = mock_message
    mock_gemini.chat.return_value = MagicMock(choices=[mock_choice])

    agent = AgentController(toolkit=sample_toolkit_data, llm_client=mock_gemini)
    exception_record = {
        "transaction_id": "TXN_MALFORMED",
        "status": "EXCEPTION",
        "reason": "BANK_AMOUNT_MISMATCH",
    }
    decision, log = agent.investigate_exception(exception_record)

    assert decision.decision == "HUMAN_REVIEW"
    assert decision.confidence == 0.0
    assert "Agent output parse error" in decision.reason


# =========================================================================
# OpenRouter Provider Tests (Items 1-10 per requirements)
# =========================================================================

# 1. OpenRouter provider initialization
def test_openrouter_provider_initialization(monkeypatch):
    from src.agent.openrouter_client import OpenRouterLLMClient
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-key-12345")
    monkeypatch.setenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct")

    client = LLMClient(provider="openrouter")
    assert isinstance(client, OpenRouterLLMClient)
    assert client.provider == "openrouter"
    assert client.mode == "REAL_LLM"
    assert client.model == "meta-llama/llama-3.3-70b-instruct"
    assert client.demo_mode is False


# 2. Missing OPENROUTER_API_KEY raises ValueError
def test_openrouter_provider_refuses_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct")
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")

    with pytest.raises(ValueError) as excinfo:
        LLMClient(provider="openrouter", api_key="", model="meta-llama/llama-3.3-70b-instruct")
    assert "OPENROUTER_API_KEY" in str(excinfo.value)


# 3. Missing OPENROUTER_MODEL raises ValueError
def test_openrouter_provider_refuses_without_model(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-key")
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")

    with pytest.raises(ValueError) as excinfo:
        LLMClient(provider="openrouter", api_key="sk-or-test-key", model="")
    assert "OPENROUTER_MODEL" in str(excinfo.value)


# 4. Provider selection chooses OpenRouter correctly
def test_provider_selection_chooses_openrouter(monkeypatch):
    from src.agent.openrouter_client import OpenRouterLLMClient
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct")

    client = LLMClient()
    assert isinstance(client, OpenRouterLLMClient)
    assert client.provider == "openrouter"


# 4b. OpenRouter secret never exposed in repr/str
def test_openrouter_secret_not_exposed(monkeypatch):
    from src.agent.openrouter_client import OpenRouterLLMClient
    monkeypatch.setenv("OPENROUTER_API_KEY", "super_secret_or_key_must_not_leak")
    monkeypatch.setenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct")

    client = OpenRouterLLMClient(api_key="super_secret_or_key_must_not_leak", model="meta-llama/llama-3.3-70b-instruct")
    rep = repr(client) + str(client)
    assert "super_secret_or_key_must_not_leak" not in rep


# 4c. OpenRouter config helper functions
def test_config_openrouter_env_loading(monkeypatch):
    from src.config import (
        get_openrouter_api_key,
        get_openrouter_model,
        get_openrouter_base_url,
        is_openrouter_key_configured,
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "test_or_secret_123")
    monkeypatch.setenv("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet")
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://custom.openrouter.ai/v1")

    assert get_openrouter_api_key() == "test_or_secret_123"
    assert get_openrouter_model() == "anthropic/claude-3.5-sonnet"
    assert get_openrouter_base_url() == "https://custom.openrouter.ai/v1"
    assert is_openrouter_key_configured() is True


# 6. Tool-call parsing & execution with OpenRouter client
def test_mock_openrouter_tool_calling(sample_toolkit_data):
    from src.agent.openrouter_client import OpenRouterLLMClient
    mock_or = MagicMock(spec=OpenRouterLLMClient)

    class MockFn:
        name = "get_adjustments"
        arguments = '{"transaction_id": "TXN034"}'

    class MockTC:
        id = "call_or_1"
        function = MockFn()

    msg1 = MagicMock(content=None, tool_calls=[MockTC()])
    resp1 = MagicMock(choices=[MagicMock(message=msg1)])

    import json
    final_payload = {
        "transaction_id": "TXN034",
        "decision": "AUTO_RESOLVED",
        "exception_type": "BANK_AMOUNT_MISMATCH",
        "resolution_type": "ADJUSTMENT_EXPLAINED",
        "resolved_difference": 100.0,
        "reason": "Discrepancy explained by bank processing fee adjustment.",
        "evidence": ["Adjustment (BANK_PROCESSING_FEE): ₹100"],
        "confidence": 1.0,
        "recommended_action": "No action needed.",
    }
    msg2 = MagicMock(content=json.dumps(final_payload), tool_calls=None)
    resp2 = MagicMock(choices=[MagicMock(message=msg2)])

    mock_or.chat.side_effect = [resp1, resp2]

    agent = AgentController(toolkit=sample_toolkit_data, llm_client=mock_or)
    exception_record = {
        "transaction_id": "TXN034",
        "status": "EXCEPTION",
        "reason": "BANK_AMOUNT_MISMATCH",
        "difference": 100,
    }
    decision, log = agent.investigate_exception(exception_record)

    assert decision.decision == "AUTO_RESOLVED"
    assert decision.resolution_type == "ADJUSTMENT_EXPLAINED"
    assert log.tool_call_count == 1
    assert log.tool_traces[0].tool_name == "get_adjustments"


# 7. Structured decision validation
def test_openrouter_structured_decision_validation(sample_toolkit_data):
    mock_or = MagicMock()
    import json
    payload = {
        "transaction_id": "TXN050",
        "decision": "HUMAN_REVIEW",
        "exception_type": "MISSING_BANK_RECORD",
        "resolution_type": "NONE",
        "resolved_difference": None,
        "reason": "Bank statement is missing settlement record.",
        "evidence": ["0 bank records found"],
        "confidence": 0.95,
        "recommended_action": "Contact acquiring bank.",
    }
    msg = MagicMock(content=json.dumps(payload), tool_calls=None)
    mock_or.chat.return_value = MagicMock(choices=[MagicMock(message=msg)])

    agent = AgentController(toolkit=sample_toolkit_data, llm_client=mock_or)
    exception_record = {
        "transaction_id": "TXN050",
        "status": "EXCEPTION",
        "reason": "MISSING_BANK_RECORD",
    }
    decision, log = agent.investigate_exception(exception_record)

    assert isinstance(decision, AgentDecision)
    assert decision.decision == "HUMAN_REVIEW"
    assert decision.confidence == 0.95


# 8. API failure -> NOT_EVALUATED
def test_openrouter_api_failure_returns_not_evaluated(sample_toolkit_data):
    from src.agent.openrouter_client import OpenRouterLLMClient
    mock_or = MagicMock(spec=OpenRouterLLMClient)
    mock_or.chat.side_effect = RuntimeError("OpenRouter 502 Bad Gateway")

    agent = AgentController(toolkit=sample_toolkit_data, llm_client=mock_or)
    exception_record = {
        "transaction_id": "TXN_ERR_01",
        "status": "EXCEPTION",
        "reason": "BANK_AMOUNT_MISMATCH",
    }
    decision, log = agent.investigate_exception(exception_record)

    assert decision.decision == "NOT_EVALUATED"
    assert "Provider request failed" in decision.reason
    assert decision.confidence == 0.0
    assert log.decision == "NOT_EVALUATED"


# 9. Rate-limit failure -> NOT_EVALUATED
def test_openrouter_rate_limit_failure_returns_not_evaluated(sample_toolkit_data):
    from src.agent.openrouter_client import OpenRouterLLMClient
    mock_or = MagicMock(spec=OpenRouterLLMClient)
    mock_or.chat.side_effect = RuntimeError("OpenRouter 429 Too Many Requests: Rate limit exceeded")

    agent = AgentController(toolkit=sample_toolkit_data, llm_client=mock_or)
    exception_record = {
        "transaction_id": "TXN_ERR_02",
        "status": "EXCEPTION",
        "reason": "BANK_AMOUNT_MISMATCH",
    }
    decision, log = agent.investigate_exception(exception_record)

    assert decision.decision == "NOT_EVALUATED"
    assert "Rate limit" in decision.reason or "Provider request failed" in decision.reason
    assert log.decision == "NOT_EVALUATED"


# 10. Existing MAX_TOOL_CALLS = 5 applies with OpenRouter
def test_openrouter_tool_calling_safety_limit_applies(sample_toolkit_data):
    mock_or = MagicMock()

    class MockFn:
        name = "get_transaction"
        arguments = '{"transaction_id": "TXN001"}'

    class MockTC:
        id = "call_repeat_or"
        function = MockFn()

    msg = MagicMock(content=None, tool_calls=[MockTC()])
    mock_or.chat.return_value = MagicMock(choices=[MagicMock(message=msg)])

    agent = AgentController(toolkit=sample_toolkit_data, llm_client=mock_or)
    exception_record = {
        "transaction_id": "TXN001",
        "status": "EXCEPTION",
        "reason": "BANK_AMOUNT_MISMATCH",
    }
    decision, log = agent.investigate_exception(exception_record)

    assert decision.decision == "HUMAN_REVIEW"
    assert "MAX_TOOL_CALLS" in decision.reason
    assert log.tool_call_count == MAX_TOOL_CALLS
    assert len(log.tool_traces) == MAX_TOOL_CALLS



# 9. Tool-calling safety limit (5) still applies
def test_tool_calling_safety_limit_applies(sample_toolkit_data):
    mock_gemini = MagicMock()
    mock_choice = MagicMock()
    mock_message = MagicMock()
    mock_message.content = None

    class MockFunction:
        name = "get_transaction"
        arguments = '{"transaction_id": "TXN001"}'

    class MockToolCall:
        id = "call_repeat"
        function = MockFunction()

    mock_message.tool_calls = [MockToolCall()]
    mock_choice.message = mock_message
    mock_gemini.chat.return_value = MagicMock(choices=[mock_choice])

    agent = AgentController(toolkit=sample_toolkit_data, llm_client=mock_gemini)
    exception_record = {
        "transaction_id": "TXN001",
        "status": "EXCEPTION",
        "reason": "BANK_AMOUNT_MISMATCH",
    }
    decision, log = agent.investigate_exception(exception_record)

    assert decision.decision == "HUMAN_REVIEW"
    assert "MAX_TOOL_CALLS" in decision.reason
    assert log.tool_call_count == MAX_TOOL_CALLS
    assert len(log.tool_traces) == MAX_TOOL_CALLS


# 10. Case A — Adjustment-backed mismatch -> AUTO_RESOLVED
def test_mock_gemini_case_a_adjustment_backed(sample_toolkit_data):
    """Case A: Multi-turn tool calling discovers settlement adjustment and returns AUTO_RESOLVED."""
    mock_gemini = MagicMock()

    # Turn 1: Call get_adjustments
    class MockFn1:
        name = "get_adjustments"
        arguments = '{"transaction_id": "TXN034"}'

    class MockTC1:
        id = "tc1"
        function = MockFn1()

    msg1 = MagicMock(content=None, tool_calls=[MockTC1()])
    resp1 = MagicMock(choices=[MagicMock(message=msg1)])

    # Turn 2: Call calculate_adjusted_expected_settlement
    class MockFn2:
        name = "calculate_adjusted_expected_settlement"
        arguments = '{"transaction_id": "TXN034"}'

    class MockTC2:
        id = "tc2"
        function = MockFn2()

    msg2 = MagicMock(content=None, tool_calls=[MockTC2()])
    resp2 = MagicMock(choices=[MagicMock(message=msg2)])

    # Turn 3: Final AUTO_RESOLVED decision
    final_payload = {
        "transaction_id": "TXN034",
        "decision": "AUTO_RESOLVED",
        "exception_type": "BANK_AMOUNT_MISMATCH",
        "resolution_type": "ADJUSTMENT_EXPLAINED",
        "resolved_difference": 100.0,
        "reason": "Bank credit equals expected settlement minus documented adjustment of ₹100.",
        "evidence": ["Adjustment (BANK_PROCESSING_FEE): ₹100", "Settlement calculation: 10000 - 200 - 100 = 9700"],
        "confidence": 1.0,
        "recommended_action": "No action needed; discrepancy accounted for by adjustment.",
    }
    import json
    msg3 = MagicMock(content=json.dumps(final_payload), tool_calls=None)
    resp3 = MagicMock(choices=[MagicMock(message=msg3)])

    mock_gemini.chat.side_effect = [resp1, resp2, resp3]

    agent = AgentController(toolkit=sample_toolkit_data, llm_client=mock_gemini)
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
    assert decision.resolved_difference == 100.0
    assert decision.confidence == 1.0
    assert log.tool_call_count == 2
    assert len(log.tool_traces) == 2
    assert log.tool_traces[0].tool_name == "get_adjustments"
    assert log.tool_traces[1].tool_name == "calculate_adjusted_expected_settlement"


# 11. Case B — Unexplained mismatch -> HUMAN_REVIEW
def test_mock_gemini_case_b_unexplained_mismatch(sample_toolkit_data):
    """Case B: Investigation finds no adjustments and escalates to HUMAN_REVIEW."""
    mock_gemini = MagicMock()

    class MockFn1:
        name = "get_adjustments"
        arguments = '{"transaction_id": "TXN001"}'

    class MockTC1:
        id = "tc1"
        function = MockFn1()

    msg1 = MagicMock(content=None, tool_calls=[MockTC1()])
    resp1 = MagicMock(choices=[MagicMock(message=msg1)])

    import json
    final_payload = {
        "transaction_id": "TXN001",
        "decision": "HUMAN_REVIEW",
        "exception_type": "BANK_AMOUNT_MISMATCH",
        "resolution_type": "NONE",
        "reason": "Bank credit does not match expected settlement and no adjustment record exists.",
        "evidence": ["0 adjustments found"],
        "confidence": 0.95,
        "recommended_action": "Review bank statement and contact payment gateway.",
    }
    msg2 = MagicMock(content=json.dumps(final_payload), tool_calls=None)
    resp2 = MagicMock(choices=[MagicMock(message=msg2)])

    mock_gemini.chat.side_effect = [resp1, resp2]

    agent = AgentController(toolkit=sample_toolkit_data, llm_client=mock_gemini)
    exception_record = {
        "transaction_id": "TXN001",
        "status": "EXCEPTION",
        "reason": "BANK_AMOUNT_MISMATCH",
        "difference": 500,
    }
    decision, log = agent.investigate_exception(exception_record)

    assert decision.decision == "HUMAN_REVIEW"
    assert decision.resolution_type == "NONE"
    assert log.tool_call_count == 1
    assert len(log.tool_traces) == 1


# 12. Case C — Incorrect/partial adjustment amount -> HUMAN_REVIEW
def test_mock_gemini_case_c_partial_adjustment(sample_toolkit_data):
    """Case C: Documented adjustment does not fully explain difference -> HUMAN_REVIEW."""
    mock_gemini = MagicMock()

    class MockFn1:
        name = "get_adjustments"
        arguments = '{"transaction_id": "TXN034"}'

    class MockTC1:
        id = "tc1"
        function = MockFn1()

    msg1 = MagicMock(content=None, tool_calls=[MockTC1()])
    resp1 = MagicMock(choices=[MagicMock(message=msg1)])

    import json
    final_payload = {
        "transaction_id": "TXN034",
        "decision": "HUMAN_REVIEW",
        "exception_type": "BANK_AMOUNT_MISMATCH",
        "resolution_type": "NONE",
        "reason": "Difference is ₹500, but adjustment is only ₹100. Remaining gap of ₹400 is unexplained.",
        "evidence": ["Adjustment: ₹100", "Remaining gap: ₹400"],
        "confidence": 0.9,
        "recommended_action": "Investigate remaining ₹400 unexplained gap.",
    }
    msg2 = MagicMock(content=json.dumps(final_payload), tool_calls=None)
    resp2 = MagicMock(choices=[MagicMock(message=msg2)])

    mock_gemini.chat.side_effect = [resp1, resp2]

    agent = AgentController(toolkit=sample_toolkit_data, llm_client=mock_gemini)
    exception_record = {
        "transaction_id": "TXN034",
        "status": "EXCEPTION",
        "reason": "BANK_AMOUNT_MISMATCH",
        "difference": 500,
    }
    decision, log = agent.investigate_exception(exception_record)

    assert decision.decision == "HUMAN_REVIEW"
    assert "₹400" in decision.reason or "unexplained" in decision.reason


# 13. Case D — Contradictory evidence -> HUMAN_REVIEW
def test_mock_gemini_case_d_contradictory_evidence(sample_toolkit_data):
    """Case D: Duplicate bank records found -> HUMAN_REVIEW."""
    mock_gemini = MagicMock()

    class MockFn1:
        name = "check_for_duplicates"
        arguments = '{"transaction_id": "TXN002"}'

    class MockTC1:
        id = "tc1"
        function = MockFn1()

    msg1 = MagicMock(content=None, tool_calls=[MockTC1()])
    resp1 = MagicMock(choices=[MagicMock(message=msg1)])

    import json
    final_payload = {
        "transaction_id": "TXN002",
        "decision": "HUMAN_REVIEW",
        "exception_type": "DUPLICATE_BANK_RECORD",
        "resolution_type": "NONE",
        "reason": "Multiple bank records (2) detected for single transaction ID.",
        "evidence": ["Duplicate check: 2 bank record(s) found"],
        "confidence": 0.95,
        "recommended_action": "Contact acquiring bank regarding duplicate settlement credit.",
    }
    msg2 = MagicMock(content=json.dumps(final_payload), tool_calls=None)
    resp2 = MagicMock(choices=[MagicMock(message=msg2)])

    mock_gemini.chat.side_effect = [resp1, resp2]

    agent = AgentController(toolkit=sample_toolkit_data, llm_client=mock_gemini)
    exception_record = {
        "transaction_id": "TXN002",
        "status": "EXCEPTION",
        "reason": "DUPLICATE_BANK_RECORD",
    }
    decision, log = agent.investigate_exception(exception_record)

    assert decision.decision == "HUMAN_REVIEW"
    assert log.tool_call_count == 1
    assert log.tool_traces[0].tool_name == "check_for_duplicates"



# 14. Automatic function calling is disabled on every Gemini request
@pytest.mark.parametrize(
    "tools",
    [
        pytest.param(None, id="tool_free_call"),
        pytest.param(
            [
                {
                    "type": "function",
                    "function": {
                        "name": "get_payment_record",
                        "description": "Fetch the payment record.",
                        "parameters": {
                            "type": "object",
                            "properties": {"transaction_id": {"type": "string"}},
                            "required": ["transaction_id"],
                        },
                    },
                }
            ],
            id="tool_calling_call",
        ),
    ],
)
def test_gemini_request_always_disables_automatic_function_calling(tools):
    """google-genai must never execute tools on our behalf, tools declared or not.

    This client is a transport: the tool loop lives in AgentController /
    InvestigatorAgent, which is what writes the audit trail and enforces
    MAX_TOOL_CALLS. AFC was previously only disabled when function declarations
    were present, so tool-free requests (the Verifier, both batch controllers)
    were routed through the SDK's own remote-call loop and logged
    "Direct use of automatic function calling (AFC) in Models.generate_content
    is not recommended" on the first such call.
    """
    from google.genai import _extra_utils, types as genai_types

    client = GeminiLLMClient(api_key="fake_key_offline_test", model="gemini-2.5-flash")

    captured = {}

    def fake_generate_content(*, model, contents, config):
        captured["config"] = config
        return genai_types.GenerateContentResponse()

    with patch.object(client._client.models, "generate_content", side_effect=fake_generate_content):
        client.chat(
            messages=[
                {"role": "system", "content": "You are an auditor."},
                {"role": "user", "content": "Investigate TXN_001."},
            ],
            tools=tools,
            max_tokens=512,
        )

    config = captured["config"]
    assert config.automatic_function_calling is not None
    assert config.automatic_function_calling.disable is True
    # The SDK's own gate: True means generate_content returns before entering
    # (and warning about) the AFC loop.
    assert _extra_utils.should_disable_afc(config) is True
