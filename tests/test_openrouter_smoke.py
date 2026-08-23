"""
Opt-in live smoke test for OpenRouter API integration.

This test ONLY runs when explicitly requested via RUN_OPENROUTER_SMOKE_TEST=1,
a valid OPENROUTER_API_KEY, and OPENROUTER_MODEL.
It makes a live API call to OpenRouter to investigate one exception and verifies structured decision output.
"""

import os
import pytest

from src.agent.controller import AgentController
from src.agent.openrouter_client import OpenRouterLLMClient
from src.agent.schemas import AgentDecision
from src.agent.tools import FinancialToolkit

RUN_SMOKE = os.getenv("RUN_OPENROUTER_SMOKE_TEST") in ("1", "true", "TRUE")
HAS_KEY = bool(os.getenv("OPENROUTER_API_KEY"))
HAS_MODEL = bool(os.getenv("OPENROUTER_MODEL"))


@pytest.mark.skipif(
    not (RUN_SMOKE and HAS_KEY and HAS_MODEL),
    reason="Opt-in OpenRouter live smoke test (requires RUN_OPENROUTER_SMOKE_TEST=1, OPENROUTER_API_KEY, and OPENROUTER_MODEL)",
)
def test_live_openrouter_smoke():
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

    openrouter_client = OpenRouterLLMClient()
    agent = AgentController(toolkit=toolkit, llm_client=openrouter_client)

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
