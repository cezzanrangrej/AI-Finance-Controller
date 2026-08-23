"""
Shared pytest fixtures for AI Finance Controller test suite.
"""

import pytest
from src.agent.tools import FinancialToolkit


@pytest.fixture(autouse=True)
def set_demo_provider_for_tests(monkeypatch):
    """Ensures standard automated pytest unit tests execute deterministically in Demo mode."""
    monkeypatch.setenv("LLM_PROVIDER", "demo")


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
