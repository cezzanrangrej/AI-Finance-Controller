"""
Regression and formatting test suite for AI Finance Controller.

Verifies:
1. Safe formatting across types (int, float, Decimal, str, None, negative, zero, large).
2. TEST3_004 regression test (integer and string CSV inputs).
3. Generic adjustment-backed resolution fixture.
4. Generic unresolved-case fixture.
5. End-to-end API upload workflow with string CSV data.
"""

import io
import json
import pytest
from decimal import Decimal
from fastapi.testclient import TestClient

from src.agent.controller import AgentController, LLMClient
from src.agent.tools import FinancialToolkit
from src.api.main import app
from src.reconciliation import ReconciliationEngine, reconcile_transaction
from src.utils.formatters import (
    format_amount,
    format_currency,
    format_decimal_currency,
    safe_float,
    safe_int,
)


def test_safe_int_and_float_conversion():
    """Verify safe_int and safe_float handle diverse data types without errors."""
    assert safe_int(3000) == 3000
    assert safe_int(3000.0) == 3000
    assert safe_int(Decimal("3000")) == 3000
    assert safe_int("3000") == 3000
    assert safe_int("3,000") == 3000
    assert safe_int("₹3,000") == 3000
    assert safe_int("  ₹ 3,000  ") == 3000
    assert safe_int(0) == 0
    assert safe_int("0") == 0
    assert safe_int(-500) == -500
    assert safe_int("-500") == -500
    assert safe_int(None) is None
    assert safe_int("") is None
    assert safe_int("N/A") is None
    assert safe_int(False) is None
    assert safe_int({"amt": 100}) is None

    assert safe_float(3000) == 3000.0
    assert safe_float(3000.5) == 3000.5
    assert safe_float(Decimal("3000.75")) == 3000.75
    assert safe_float("3000.50") == 3000.5
    assert safe_float("₹3,000.50") == 3000.5
    assert safe_float(None) is None
    assert safe_float("") is None
    assert safe_float("invalid") is None


def test_format_amount_and_currency():
    """Verify format_amount and format_currency formatting across all types."""
    assert format_currency(3000) == "₹3,000"
    assert format_currency("3000") == "₹3,000"
    assert format_currency(0) == "₹0"
    assert format_currency("0") == "₹0"
    assert format_currency(None) == "N/A"
    assert format_currency("", default="—") == "—"
    assert format_currency(100000000) == "₹100,000,000"
    assert format_currency("₹3,000") == "₹3,000"

    # Floating point currency formatting
    assert format_decimal_currency(2940.50) == "₹2,940.50"
    assert format_decimal_currency("2940.50") == "₹2,940.50"
    assert format_decimal_currency(None) == "N/A"

    # Number amount formatting without currency symbol
    assert format_amount(3000) == "3,000"
    assert format_amount("3000") == "3,000"
    assert format_amount(0) == "0"
    assert format_amount(None) == "N/A"


def test_test3_004_regression():
    """
    Verify TEST3_004 specific financial case:
    Payment = 3000, Ledger Gross = 3000, Fee = 60, Net = 2940,
    Adjustment = 100, Bank Credit = 2840.
    Proof: 3000 - 60 - 100 = 2840.
    Expected: AUTO_RESOLVED, ADJUSTMENT_EXPLAINED, confidence = 1.0.
    """
    payment = {
        "transaction_id": "TEST3_004",
        "merchant_id": "M001",
        "amount": 3000,
        "date": "2026-08-10",
        "status": "CAPTURED",
    }
    ledger = {
        "transaction_id": "TEST3_004",
        "gross_amount": 3000,
        "fee": 60,
        "net_amount": 2940,
        "date": "2026-08-10",
        "status": "POSTED",
    }
    bank = [
        {
            "bank_reference": "BNK_TEST3_004",
            "transaction_id": "TEST3_004",
            "credited_amount": 2840,
            "date": "2026-08-10",
        }
    ]
    adjustments = [
        {
            "transaction_id": "TEST3_004",
            "adjustment_type": "SETTLEMENT_ADJUSTMENT",
            "amount": 100,
            "reason": "Standard settlement adjustment charge",
            "date": "2026-08-10",
            "reference": "ADJ_004",
        }
    ]

    # Phase 1 verification
    p1_result = reconcile_transaction(payment, ledger, bank)
    assert p1_result["status"] == "EXCEPTION"
    assert p1_result["reason"] == "BANK_AMOUNT_MISMATCH"
    assert p1_result["difference"] == 100  # expected_net (2940) - bank (2840)

    # Phase 2 Agent Investigation
    toolkit = FinancialToolkit([payment], [ledger], bank, adjustments)
    agent = AgentController(toolkit=toolkit, llm_client=LLMClient())

    decision, log = agent.investigate_exception(p1_result)

    assert decision.decision == "AUTO_RESOLVED"
    assert decision.resolution_type == "ADJUSTMENT_EXPLAINED"
    assert decision.confidence == 1.0
    assert decision.resolved_difference == 100.0
    assert "Agent error" not in decision.reason
    assert "Cannot specify" not in decision.reason
    assert "100" in decision.reason
    assert "2,840" in decision.reason or "2840" in decision.reason


def test_test3_004_with_raw_string_csv_inputs():
    """Verify TEST3_004 when records contain raw string numbers directly parsed from CSV."""
    payment = {
        "transaction_id": "TEST3_004",
        "merchant_id": "M001",
        "amount": "3000",
        "date": "2026-08-10",
        "status": "CAPTURED",
    }
    ledger = {
        "transaction_id": "TEST3_004",
        "gross_amount": "3000",
        "fee": "60",
        "net_amount": "2940",
        "date": "2026-08-10",
        "status": "POSTED",
    }
    bank = [
        {
            "bank_reference": "BNK_TEST3_004",
            "transaction_id": "TEST3_004",
            "credited_amount": "2840",
            "date": "2026-08-10",
        }
    ]
    adjustments = [
        {
            "transaction_id": "TEST3_004",
            "adjustment_type": "SETTLEMENT_ADJUSTMENT",
            "amount": "100",
            "reason": "Standard settlement adjustment charge",
            "date": "2026-08-10",
            "reference": "ADJ_004",
        }
    ]

    toolkit = FinancialToolkit([payment], [ledger], bank, adjustments)
    agent = AgentController(toolkit=toolkit, llm_client=LLMClient())

    exc = {
        "transaction_id": "TEST3_004",
        "status": "EXCEPTION",
        "reason": "BANK_AMOUNT_MISMATCH",
        "payment_amount": "3000",
        "gross_amount": "3000",
        "fee": "60",
        "expected_net_amount": "2940",
        "bank_amount": "2840",
        "difference": "100",
    }

    decision, log = agent.investigate_exception(exc)

    assert decision.decision == "AUTO_RESOLVED"
    assert decision.resolution_type == "ADJUSTMENT_EXPLAINED"
    assert decision.confidence == 1.0
    assert decision.resolved_difference == 100.0
    assert "Cannot specify" not in decision.reason
    assert "Agent error" not in decision.reason


def test_generic_adjustment_backed_resolution_fixture():
    """Verify generic adjustment-backed resolution with arbitrary randomized amounts."""
    gross = 18500
    fee = 370
    expected_net = gross - fee  # 18130
    adj_amt = 400
    credited = expected_net - adj_amt  # 17730

    payment = {"transaction_id": "GEN_001", "merchant_id": "M99", "amount": gross, "date": "2026-08-15", "status": "CAPTURED"}
    ledger = {"transaction_id": "GEN_001", "gross_amount": gross, "fee": fee, "net_amount": expected_net, "date": "2026-08-15", "status": "POSTED"}
    bank = [{"bank_reference": "BNK_GEN_001", "transaction_id": "GEN_001", "credited_amount": credited, "date": "2026-08-15"}]
    adjustments = [{"transaction_id": "GEN_001", "adjustment_type": "BANK_PROCESSING_FEE", "amount": adj_amt, "reason": "Bank fee charge", "date": "2026-08-15", "reference": "ADJ_GEN"}]

    toolkit = FinancialToolkit([payment], [ledger], bank, adjustments)
    agent = AgentController(toolkit=toolkit, llm_client=LLMClient())

    exc = {"transaction_id": "GEN_001", "status": "EXCEPTION", "reason": "BANK_AMOUNT_MISMATCH"}
    decision, log = agent.investigate_exception(exc)

    assert decision.decision == "AUTO_RESOLVED"
    assert decision.resolution_type == "ADJUSTMENT_EXPLAINED"
    assert decision.confidence == 1.0
    assert decision.resolved_difference == float(adj_amt)


def test_generic_unresolved_case_fixture():
    """Verify that an unexplained discrepancy correctly remains HUMAN_REVIEW."""
    gross = 20000
    fee = 400
    expected_net = 19600
    credited = 19000  # 600 mismatch without adjustment

    payment = {"transaction_id": "GEN_UNRES", "merchant_id": "M99", "amount": gross, "date": "2026-08-15", "status": "CAPTURED"}
    ledger = {"transaction_id": "GEN_UNRES", "gross_amount": gross, "fee": fee, "net_amount": expected_net, "date": "2026-08-15", "status": "POSTED"}
    bank = [{"bank_reference": "BNK_GEN_UNRES", "transaction_id": "GEN_UNRES", "credited_amount": credited, "date": "2026-08-15"}]
    adjustments = []

    toolkit = FinancialToolkit([payment], [ledger], bank, adjustments)
    agent = AgentController(toolkit=toolkit, llm_client=LLMClient())

    exc = {"transaction_id": "GEN_UNRES", "status": "EXCEPTION", "reason": "BANK_AMOUNT_MISMATCH"}
    decision, log = agent.investigate_exception(exc)

    assert decision.decision == "HUMAN_REVIEW"
    assert decision.resolution_type == "NONE"
    assert decision.confidence == 0.95


def test_api_upload_workflow_end_to_end():
    """Verify uploaded CSV files run through /api/runs/upload without formatting errors."""
    client = TestClient(app)

    payments_csv = "transaction_id,merchant_id,amount,date,status\nTEST3_004,M001,3000,2026-08-10,CAPTURED\nTXN_MATCH,M002,5000,2026-08-10,CAPTURED\n"
    ledger_csv = "transaction_id,gross_amount,fee,net_amount,date,status\nTEST3_004,3000,60,2940,2026-08-10,POSTED\nTXN_MATCH,5000,100,4900,2026-08-10,POSTED\n"
    bank_csv = "bank_reference,transaction_id,credited_amount,date\nBNK_004,TEST3_004,2840,2026-08-10\nBNK_MATCH,TXN_MATCH,4900,2026-08-10\n"
    adjustments_csv = "transaction_id,adjustment_type,amount,reason,date,reference\nTEST3_004,SETTLEMENT_ADJUSTMENT,100,Settlement adjustment,2026-08-10,ADJ001\n"

    files = {
        "payments": ("payments.csv", io.BytesIO(payments_csv.encode("utf-8")), "text/csv"),
        "ledger": ("ledger.csv", io.BytesIO(ledger_csv.encode("utf-8")), "text/csv"),
        "bank": ("bank.csv", io.BytesIO(bank_csv.encode("utf-8")), "text/csv"),
        "adjustments": ("adjustments.csv", io.BytesIO(adjustments_csv.encode("utf-8")), "text/csv"),
    }

    response = client.post("/api/runs/upload", files=files)
    assert response.status_code == 201, response.text
    data = response.json()

    assert data["total_records"] == 2
    assert data["initial_reconciled"] == 1
    assert data["initial_exceptions"] == 1
    assert data["ai_auto_resolved"] == 1
    assert data["human_review"] == 0
    assert data["final_resolved"] == 2

    # Check exceptions endpoint for this run
    run_id = data["run_id"]
    exc_resp = client.get(f"/api/runs/{run_id}/exceptions")
    assert exc_resp.status_code == 200
    exc_list = exc_resp.json()
    assert len(exc_list) == 1
    exc_item = exc_list[0]
    assert exc_item["transaction_id"] == "TEST3_004"
    assert exc_item["decision"] == "AUTO_RESOLVED"
    assert exc_item["resolution_type"] == "ADJUSTMENT_EXPLAINED"
    assert "Agent error" not in (exc_item.get("reason") or "")
    assert "Cannot specify" not in (exc_item.get("reason") or "")
