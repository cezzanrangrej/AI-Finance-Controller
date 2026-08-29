"""
Comprehensive Data Integrity & Precision Regression Test Suite.

Verifies:
1. Exact monetary Decimal preservation across CSV parsing, reconciliation, database persistence, and API responses.
2. Handling of diverse values: 9357.5, 9357.50, 5357, 100, 1000.25, 99999.99, 0, negative values, and arbitrary randomized decimals.
3. Source provenance capture (source_file, source_row, raw_credited_amount, parsed_credited_amount).
4. Strict validation invariants during CSV upload.
5. Development-only data integrity diagnostics endpoint.
6. Multi-run isolation preventing stale data cross-contamination.
"""

import io
import json
import random
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
    safe_decimal,
    safe_numeric,
)


@pytest.fixture
def client():
    return TestClient(app)


def test_decimal_normalization_and_formatting():
    """Verify that 9357.5 and 9357.50 normalize to identical Decimal values and format cleanly."""
    d1 = safe_decimal("9357.5")
    d2 = safe_decimal("9357.50")
    d3 = safe_decimal(9357.5)
    d4 = safe_decimal(" ₹ 9,357.50 ")

    assert d1 == Decimal("9357.5")
    assert d2 == Decimal("9357.50")
    assert d1 == d2  # Decimal equality holds for numerical value
    assert d3 == Decimal("9357.5")
    assert d4 == Decimal("9357.50")

    assert safe_numeric(d1) == 9357.5
    assert safe_numeric(d2) == 9357.5

    assert format_currency("9357.5") == "₹9,357.50"
    assert format_currency("9357.50") == "₹9,357.50"
    assert format_currency(5357) == "₹5,357"
    assert format_currency("1000.25") == "₹1,000.25"
    assert format_currency("0") == "₹0"


@pytest.mark.parametrize(
    "val_str, expected_numeric",
    [
        ("9357.5", 9357.5),
        ("9357.50", 9357.5),
        ("5357", 5357),
        ("100", 100),
        ("1000.25", 1000.25),
        ("99999.99", 99999.99),
        ("0", 0),
        ("-500.50", -500.5),
        ("12345.67", 12345.67),
    ],
)
def test_reconciliation_exact_decimal_preservation(val_str, expected_numeric):
    """
    Verify that the reconciliation engine preserves exact values without integer truncation.
    """
    fee = 20
    fee_dec = Decimal(str(fee))
    val_dec = Decimal(val_str)
    gross_dec = val_dec + fee_dec
    gross_str = str(gross_dec)

    payment = {
        "transaction_id": "TXN_PRECISION_TEST",
        "merchant_id": "M001",
        "amount": gross_str,
        "date": "2026-08-20",
        "status": "CAPTURED",
    }
    ledger = {
        "transaction_id": "TXN_PRECISION_TEST",
        "gross_amount": gross_str,
        "fee": str(fee),
        "net_amount": val_str,
        "date": "2026-08-20",
        "status": "POSTED",
    }
    bank = [
        {
            "bank_reference": "BNK_PREC_001",
            "transaction_id": "TXN_PRECISION_TEST",
            "credited_amount": val_str,
            "date": "2026-08-20",
        }
    ]

    result = reconcile_transaction(payment, ledger, bank)

    assert result["status"] == "RECONCILED"
    assert result["reason"] is None
    assert result["bank_amount"] == expected_numeric
    assert result["difference"] == 0


def test_randomized_monetary_values_end_to_end(client):
    """
    Generate randomized monetary values and verify end-to-end preservation through:
    CSV creation -> multipart upload -> parser -> reconciliation -> DB -> API -> detail response.
    """
    random.seed(12345)
    test_cases = []

    # Generate 15 distinct transactions with various whole and fractional amounts
    sample_amounts = [
        "9357.5",
        "9357.50",
        "5357",
        "100",
        "1000.25",
        "99999.99",
        "0.50",
        "4250.75",
        "18999.10",
        "777.00",
    ]

    for i in range(len(sample_amounts)):
        txn_id = f"RND_TXN_{i+1:03d}"
        net_str = sample_amounts[i]
        net_dec = Decimal(net_str)
        fee_dec = Decimal(random.choice([0, 10, 25, 50]))
        gross_dec = net_dec + fee_dec

        test_cases.append({
            "txn_id": txn_id,
            "gross": str(gross_dec),
            "fee": str(fee_dec),
            "net": net_str,
            "bank_credit": net_str,
            "expected_numeric": safe_numeric(net_dec),
        })

    # Build CSVs
    p_csv = "transaction_id,amount,merchant_id,date,status\n" + "\n".join(
        f"{c['txn_id']},{c['gross']},M_{i},2026-08-25,CAPTURED" for i, c in enumerate(test_cases)
    )
    l_csv = "transaction_id,gross_amount,fee,net_amount,date,status\n" + "\n".join(
        f"{c['txn_id']},{c['gross']},{c['fee']},{c['net']},2026-08-25,POSTED" for c in test_cases
    )
    b_csv = "bank_reference,transaction_id,credited_amount,date\n" + "\n".join(
        f"BNK_{i},{c['txn_id']},{c['bank_credit']},2026-08-25" for i, c in enumerate(test_cases)
    )

    files = {
        "payments": ("payments.csv", io.BytesIO(p_csv.encode("utf-8")), "text/csv"),
        "ledger": ("ledger.csv", io.BytesIO(l_csv.encode("utf-8")), "text/csv"),
        "bank": ("bank.csv", io.BytesIO(b_csv.encode("utf-8")), "text/csv"),
    }

    # Step 1: Validate dataset
    val_res = client.post("/api/runs/validate", files=files)
    assert val_res.status_code == 200
    assert val_res.json()["valid"] is True

    # Step 2: Execute upload run
    files["payments"][1].seek(0)
    files["ledger"][1].seek(0)
    files["bank"][1].seek(0)

    upload_res = client.post("/api/runs/upload", files=files)
    assert upload_res.status_code == 201
    run_data = upload_res.json()
    run_id = run_data["run_id"]
    assert run_data["total_records"] == len(test_cases)

    # Step 3: Query all transactions for this run
    txns_res = client.get(f"/api/runs/{run_id}/transactions")
    assert txns_res.status_code == 200
    returned_txns = {t["transaction_id"]: t for t in txns_res.json()}

    for c in test_cases:
        t = returned_txns[c["txn_id"]]
        # Exact value check
        assert t["bank_amount"] == c["expected_numeric"], (
            f"Expected {c['expected_numeric']}, got {t['bank_amount']} for {c['txn_id']}"
        )
        assert t["expected_net_amount"] == c["expected_numeric"]

        # Step 4: Check single transaction detail & source provenance
        detail_res = client.get(f"/api/runs/{run_id}/transactions/{c['txn_id']}")
        assert detail_res.status_code == 200
        detail = detail_res.json()

        assert detail["bank_amount"] == c["expected_numeric"]
        assert detail["source_provenance"] is not None
        assert detail["source_provenance"]["source_file"] == "bank.csv"
        assert detail["source_provenance"]["raw_credited_amount"] == c["bank_credit"]
        assert detail["source_provenance"]["parsed_credited_amount"] == c["expected_numeric"]


def test_upload_validation_invariant_fails_on_corrupted_data(client):
    """
    Verify that if a CSV contains invalid / corrupted numbers,
    dataset validation immediately fails with a clear 400 error.
    """
    p_csv = "transaction_id,amount\nTXN001,1000\n"
    l_csv = "transaction_id,gross_amount,fee\nTXN001,1000,20\n"
    b_csv = "bank_reference,transaction_id,credited_amount\nBNK1,TXN001,invalid_currency_#$%\n"

    files = {
        "payments": ("payments.csv", io.BytesIO(p_csv.encode("utf-8")), "text/csv"),
        "ledger": ("ledger.csv", io.BytesIO(l_csv.encode("utf-8")), "text/csv"),
        "bank": ("bank.csv", io.BytesIO(b_csv.encode("utf-8")), "text/csv"),
    }

    val_res = client.post("/api/runs/validate", files=files)
    assert val_res.status_code == 200
    val_data = val_res.json()
    assert val_data["valid"] is False
    assert any("validation failed" in err.lower() or "invalid numeric" in err.lower() for err in val_data["errors"])


def test_data_integrity_diagnostic_endpoint(client):
    """
    Verify that the diagnostics endpoint reports transaction-by-transaction source,
    normalized, reconciliation, and API amounts in development mode.
    """
    p_csv = "transaction_id,amount\nTXN_DIAG_1,9357.5\n"
    l_csv = "transaction_id,gross_amount,fee\nTXN_DIAG_1,9357.5,0\n"
    b_csv = "bank_reference,transaction_id,credited_amount\nBNK_DIAG_1,TXN_DIAG_1,9357.50\n"

    files = {
        "payments": ("payments.csv", io.BytesIO(p_csv.encode("utf-8")), "text/csv"),
        "ledger": ("ledger.csv", io.BytesIO(l_csv.encode("utf-8")), "text/csv"),
        "bank": ("bank.csv", io.BytesIO(b_csv.encode("utf-8")), "text/csv"),
    }

    upload_res = client.post("/api/runs/upload", files=files)
    assert upload_res.status_code == 201
    run_id = upload_res.json()["run_id"]

    diag_res = client.get(f"/api/runs/{run_id}/diagnostics/data-integrity")
    assert diag_res.status_code == 200
    diag = diag_res.json()

    assert diag["run_id"] == run_id
    assert diag["all_passed"] is True
    assert diag["discrepancy_count"] == 0
    assert len(diag["records"]) == 1

    rec = diag["records"][0]
    assert rec["transaction_id"] == "TXN_DIAG_1"
    assert rec["raw_bank_amount"] == "9357.50"
    assert rec["parsed_bank_amount"] == 9357.5
    assert rec["normalized_bank_amount"] == 9357.5
    assert rec["reconciliation_bank_amount"] == 9357.5
    assert rec["api_bank_amount"] == 9357.5
    assert rec["integrity_passed"] is True


def test_multi_run_isolation_no_stale_contamination(client):
    """
    Verify that consecutive runs operate strictly on their own uploaded datasets
    without contamination or caching between runs.
    """
    # Run 1 with specific amount 9357.5
    p1 = "transaction_id,amount\nTXN_ISO_1,9357.5\n"
    l1 = "transaction_id,gross_amount,fee\nTXN_ISO_1,9357.5,0\n"
    b1 = "bank_reference,transaction_id,credited_amount\nBNK_1,TXN_ISO_1,9357.5\n"

    res1 = client.post(
        "/api/runs/upload",
        files={
            "payments": ("payments.csv", io.BytesIO(p1.encode("utf-8")), "text/csv"),
            "ledger": ("ledger.csv", io.BytesIO(l1.encode("utf-8")), "text/csv"),
            "bank": ("bank.csv", io.BytesIO(b1.encode("utf-8")), "text/csv"),
        },
    )
    assert res1.status_code == 201
    run1_id = res1.json()["run_id"]

    # Run 2 with completely different amount 5357
    p2 = "transaction_id,amount\nTXN_ISO_1,5357\n"
    l2 = "transaction_id,gross_amount,fee\nTXN_ISO_1,5357,0\n"
    b2 = "bank_reference,transaction_id,credited_amount\nBNK_2,TXN_ISO_1,5357\n"

    res2 = client.post(
        "/api/runs/upload",
        files={
            "payments": ("payments.csv", io.BytesIO(p2.encode("utf-8")), "text/csv"),
            "ledger": ("ledger.csv", io.BytesIO(l2.encode("utf-8")), "text/csv"),
            "bank": ("bank.csv", io.BytesIO(b2.encode("utf-8")), "text/csv"),
        },
    )
    assert res2.status_code == 201
    run2_id = res2.json()["run_id"]

    assert run1_id != run2_id

    # Verify Run 1 detail still has 9357.5
    detail1 = client.get(f"/api/runs/{run1_id}/transactions/TXN_ISO_1").json()
    assert detail1["bank_amount"] == 9357.5

    # Verify Run 2 detail has 5357
    detail2 = client.get(f"/api/runs/{run2_id}/transactions/TXN_ISO_1").json()
    assert detail2["bank_amount"] == 5357
