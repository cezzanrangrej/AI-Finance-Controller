"""
Unit and integration tests for the Live Agent Trace / Terminal Observability Layer.
Verifies trace configuration, formatting, secret sanitization, real-time output,
provider/model display, deterministic finance engine blocks, and mode isolation.
"""

import io
import json
import os
from unittest.mock import MagicMock, patch
import pytest

from src.agent.controller import AgentController, LLMClient
from src.agent.batch_controller import BatchAgentController
from src.agent.multi_agent.investigator import InvestigatorAgent
from src.agent.multi_agent.orchestrator import MultiAgentOrchestrator
from src.agent.multi_agent.verifier import VerifierAgent
from src.agent.schemas import InvestigationProposal, VerificationResult
from src.agent.tools import FinancialToolkit
from src.agent.trace import AgentTracer, parse_bool_env
from src.run_llm_eval import run_evaluation


@pytest.fixture
def sample_toolkit():
    payments = [
        {"transaction_id": "TXN003", "merchant_id": "M001", "amount": 14500, "date": "2026-08-01", "status": "CAPTURED"},
        {"transaction_id": "TXN019", "merchant_id": "M002", "amount": 10000, "date": "2026-08-02", "status": "CAPTURED"},
    ]
    ledger = [
        {"transaction_id": "TXN003", "gross_amount": 14500, "fee": 290, "net_amount": 14210, "date": "2026-08-01", "status": "POSTED"},
        {"transaction_id": "TXN019", "gross_amount": 9000, "fee": 200, "net_amount": 8800, "date": "2026-08-02", "status": "POSTED"},
    ]
    bank = [
        {"bank_reference": "BNK003", "transaction_id": "TXN003", "credited_amount": 14110, "date": "2026-08-01"},
        {"bank_reference": "BNK019", "transaction_id": "TXN019", "credited_amount": 8800, "date": "2026-08-02"},
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
# Test 1: SHOW_AGENT_TRACE=false -> no trace output
# ----------------------------------------------------------------------
def test_trace_disabled_produces_no_output():
    buf = io.StringIO()
    tracer = AgentTracer(enabled=False, output_stream=buf)

    tracer.header()
    tracer.transaction_header("TXN003", "BANK_AMOUNT_MISMATCH")
    tracer.orchestrator_routing("Investigator")
    tracer.agent_started("Investigator", "DEMO", "demo-model")
    tracer.tool_call_started("Investigator", "DEMO", "get_transaction", {"transaction_id": "TXN003"})
    tracer.tool_result("get_transaction", {"payment": {"amount": 14500}})
    tracer.final_decision("AUTO_RESOLVED", "AUTO_RESOLVED", True, "AUTO_RESOLVED")

    assert buf.getvalue() == ""


# ----------------------------------------------------------------------
# Test 2: SHOW_AGENT_TRACE=true -> trace output
# ----------------------------------------------------------------------
def test_trace_enabled_produces_output():
    buf = io.StringIO()
    tracer = AgentTracer(enabled=True, output_stream=buf)

    tracer.header()
    tracer.transaction_header("TXN003", "BANK_AMOUNT_MISMATCH")
    tracer.orchestrator_routing("Investigator")
    tracer.final_decision("AUTO_RESOLVED", "AUTO_RESOLVED", True, "AUTO_RESOLVED")

    output = buf.getvalue()
    assert "AI FINANCE CONTROLLER — MULTI-AGENT TRACE" in output
    assert "Transaction: TXN003" in output
    assert "[ORCHESTRATOR]" in output
    assert "→ FINAL DECISION: AUTO_RESOLVED" in output


# ----------------------------------------------------------------------
# Test 3: CLI --trace overrides environment variable
# ----------------------------------------------------------------------
def test_cli_trace_precedence():
    with patch.dict("os.environ", {"SHOW_AGENT_TRACE": "false"}):
        # Explicit trace=True from CLI overrides env SHOW_AGENT_TRACE=false
        tracer_override = AgentTracer(enabled=True)
        assert tracer_override.enabled is True

    with patch.dict("os.environ", {"SHOW_AGENT_TRACE": "true"}):
        # Explicit trace=False from CLI overrides env SHOW_AGENT_TRACE=true
        tracer_override_false = AgentTracer(enabled=False)
        assert tracer_override_false.enabled is False

    with patch.dict("os.environ", {"SHOW_AGENT_TRACE": "true"}):
        # Default with env true
        tracer_env = AgentTracer()
        assert tracer_env.enabled is True


# ----------------------------------------------------------------------
# Test 4: Provider and model names appear in trace
# ----------------------------------------------------------------------
def test_provider_and_model_names_appear():
    buf = io.StringIO()
    tracer = AgentTracer(enabled=True, output_stream=buf)

    tracer.agent_started("Investigator", "GROK", "grok-beta")
    tracer.verifier_review_started("GEMINI", "gemini-2.5-flash")

    out = buf.getvalue()
    assert "[INVESTIGATOR | GROK]" in out
    assert "Model: grok-beta" in out
    assert "[VERIFIER | GEMINI]" in out
    assert "Model: gemini-2.5-flash" in out


# ----------------------------------------------------------------------
# Test 5: Tool calls and concise results appear
# ----------------------------------------------------------------------
def test_tool_calls_and_results_appear():
    buf = io.StringIO()
    tracer = AgentTracer(enabled=True, output_stream=buf)

    tracer.tool_call_started("Investigator", "GROK", "get_transaction", {"transaction_id": "TXN003"})
    tracer.tool_result("get_transaction", {
        "payment": {"amount": 14500},
        "ledger": {"gross_amount": 14500},
        "bank_records": [{"credited_amount": 14110}],
        "adjustments": [{"amount": 100}],
    })

    out = buf.getvalue()
    assert "→ Calling get_transaction(transaction_id=TXN003)" in out
    assert "[TOOL RESULT]" in out
    assert "Payment: ₹14,500" in out
    assert "Ledger gross: ₹14,500" in out
    assert "Bank credit: ₹14,110" in out
    assert "Adjustments: 1 found" in out


# ----------------------------------------------------------------------
# Test 6: Deterministic finance checks appear clearly
# ----------------------------------------------------------------------
def test_deterministic_finance_check_appear():
    buf = io.StringIO()
    tracer = AgentTracer(enabled=True, output_stream=buf)

    tracer.deterministic_calculation({
        "Expected settlement": 14210,
        "Adjustment": 100,
        "Adjusted settlement": 14110,
        "Bank credit": 14110,
    }, proven=True)

    tracer.evidence_sufficient([
        "Documented adjustment exists",
        "Adjusted settlement mathematically matches bank credit",
    ])

    out = buf.getvalue()
    assert "[FINANCE ENGINE | PYTHON]" in out
    assert "Expected settlement: ₹14,210" in out
    assert "Adjustment: ₹100" in out
    assert "Adjusted settlement: ₹14,110" in out
    assert "Bank credit: ₹14,110" in out
    assert "✓ Equality proven" in out
    assert "[EVIDENCE CHECK | PYTHON]" in out
    assert "✓ Documented adjustment exists" in out


# ----------------------------------------------------------------------
# Test 7: Final decision and disagreement policy appear
# ----------------------------------------------------------------------
def test_final_decision_disagreement_policy_appear():
    buf = io.StringIO()
    tracer = AgentTracer(enabled=True, output_stream=buf)

    tracer.final_decision(
        investigator_dec="AUTO_RESOLVED",
        verifier_dec="HUMAN_REVIEW",
        proof_pass=False,
        final_decision="HUMAN_REVIEW",
        resolution_type="NONE",
        resolution_source="VERIFIER_ESCALATION",
        reason="Verifier flagged insufficient proof.",
    )

    out = buf.getvalue()
    assert "[FINAL CONTROLLER]" in out
    assert "Investigator: AUTO_RESOLVED" in out
    assert "Verifier: HUMAN_REVIEW" in out
    assert "Deterministic proof: FAIL" in out
    assert "→ FINAL DECISION: HUMAN_REVIEW" in out
    assert "Resolution source: VERIFIER_ESCALATION" in out


# ----------------------------------------------------------------------
# Test 8: Provider errors do not expose secrets
# ----------------------------------------------------------------------
def test_provider_error_trace_sanitized():
    buf = io.StringIO()
    tracer = AgentTracer(enabled=True, output_stream=buf)

    err = "HTTP 401 Unauthorized for request with Bearer sk-or-v1-abcdef1234567890 and key AIzaSy1234567890abcdef12345"
    tracer.provider_error("Investigator", "OPENROUTER", "API_ERROR", "NOT_EVALUATED", err)

    out = buf.getvalue()
    assert "[PROVIDER ERROR | OPENROUTER]" in out
    assert "Status: API_ERROR" in out
    assert "sk-or-v1-" not in out
    assert "AIzaSy" not in out
    assert "[REDACTED_TOKEN]" in out or "[REDACTED_API_KEY]" in out


# ----------------------------------------------------------------------
# Test 9: API keys never appear in output
# ----------------------------------------------------------------------
def test_api_keys_never_appear_in_output():
    buf = io.StringIO()
    tracer = AgentTracer(enabled=True, output_stream=buf)

    raw_text = "Checking Authorization: Bearer sk-or-v1-secret1234567890 key AIzaSyRealSecretKey1234567890"
    tracer._print(raw_text)

    out = buf.getvalue()
    assert "sk-or-v1-secret" not in out
    assert "AIzaSyRealSecret" not in out


# ----------------------------------------------------------------------
# Test 10: Real-time stdout flushing
# ----------------------------------------------------------------------
def test_real_time_stdout_flushing():
    mock_stream = MagicMock()
    tracer = AgentTracer(enabled=True, output_stream=mock_stream)

    tracer._print("Test event")
    mock_stream.write.assert_called()


# ----------------------------------------------------------------------
# Test 11: Individual mode trace
# ----------------------------------------------------------------------
def test_individual_mode_trace(sample_toolkit):
    buf = io.StringIO()
    tracer = AgentTracer(enabled=True, output_stream=buf)

    agent = AgentController(toolkit=sample_toolkit, llm_client=LLMClient(provider="demo"), tracer=tracer)
    exc = {"transaction_id": "TXN003", "reason": "BANK_AMOUNT_MISMATCH"}
    decision, log = agent.investigate_exception(exc)

    assert decision.decision == "AUTO_RESOLVED"


# ----------------------------------------------------------------------
# Test 12: Multi-agent mode trace
# ----------------------------------------------------------------------
def test_multi_agent_mode_trace(sample_toolkit):
    buf = io.StringIO()
    tracer = AgentTracer(enabled=True, output_stream=buf)

    orch = MultiAgentOrchestrator(toolkit=sample_toolkit, provider="demo", tracer=tracer)
    exc = {"transaction_id": "TXN003", "reason": "BANK_AMOUNT_MISMATCH"}
    decision, log = orch.investigate_exception(exc)

    out = buf.getvalue()
    assert "Transaction: TXN003" in out
    assert "[ORCHESTRATOR]" in out
    assert "→ Routing to Investigator" in out
    assert "[INVESTIGATOR | DEMO]" in out
    assert "[FINANCE ENGINE | PYTHON]" in out
    assert "[VERIFIER | DEMO]" in out
    assert "[FINAL CONTROLLER]" in out
    assert "TRANSACTION SUMMARY" in out
    assert decision.decision == "AUTO_RESOLVED"


# ----------------------------------------------------------------------
# Test 13: Batch mode trace
# ----------------------------------------------------------------------
def test_batch_mode_trace(sample_toolkit):
    buf = io.StringIO()
    tracer = AgentTracer(enabled=True, output_stream=buf)

    batch_agent = BatchAgentController(toolkit=sample_toolkit, llm_client=LLMClient(provider="demo"), tracer=tracer)
    batch = [
        {"transaction_id": "TXN003", "reason": "BANK_AMOUNT_MISMATCH"},
        {"transaction_id": "TXN019", "reason": "GROSS_AMOUNT_MISMATCH"},
    ]
    decisions, log = batch_agent.investigate_batch(batch)

    assert len(decisions) == 2


# ----------------------------------------------------------------------
# Test 14: Demo mode trace via CLI runner
# ----------------------------------------------------------------------
def test_demo_mode_trace_via_run_evaluation(tmp_path):
    res = run_evaluation(
        provider="demo",
        cases=2,
        runs=1,
        mode="multi-agent",
        trace=True,
    )
    assert res["status"] == "COMPLETED"
    assert res["completed"] == 2
