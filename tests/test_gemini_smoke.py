"""
Opt-in live smoke test for Google Gemini API integration.

This test ONLY runs when explicitly requested via RUN_GEMINI_SMOKE_TEST=1 and a valid GEMINI_API_KEY.
It makes a live API call to Gemini to investigate one exception and verifies structured decision output.
"""

import os
import pytest

from src.agent.controller import AgentController
from src.agent.gemini_client import GeminiLLMClient
from src.agent.schemas import AgentDecision
from src.agent.tools import FinancialToolkit

RUN_SMOKE = os.getenv("RUN_GEMINI_SMOKE_TEST") in ("1", "true", "TRUE")
HAS_KEY = bool(os.getenv("GEMINI_API_KEY"))


@pytest.mark.skipif(
    not (RUN_SMOKE and HAS_KEY),
    reason="Opt-in Gemini live smoke test (requires RUN_GEMINI_SMOKE_TEST=1 and GEMINI_API_KEY)",
)
def test_live_gemini_smoke():
    payments = [
        {"transaction_id": "TXN034", "merchant_id": "M003", "amount": 10000, "date": "2026-08-03", "status": "CAPTURED"}
    ]
    ledger = [
        {"transaction_id": "TXN034", "gross_amount": 10000, "fee": 200, "net_amount": 9800, "date": "2026-08-03", "status": "POSTED"}
    ]
    bank = [
        {"bank_reference": "BNK034", "transaction_id": "TXN034", "credited_amount": 9700, "date": "2026-08-03"}
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
    toolkit = FinancialToolkit(payments, ledger, bank, adjustments)

    gemini_client = GeminiLLMClient()
    agent = AgentController(toolkit=toolkit, llm_client=gemini_client)

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

    assert isinstance(decision, AgentDecision)
    assert decision.transaction_id == "TXN034"
    assert decision.decision in ("AUTO_RESOLVED", "HUMAN_REVIEW")
    assert 0.0 <= decision.confidence <= 1.0
    assert len(decision.evidence) > 0
