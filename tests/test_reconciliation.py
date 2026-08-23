"""
Unit and batch tests for Finance Reconciliation Engine.
"""

import os
import pytest
from src.generator import SyntheticDataGenerator
from src.reconciliation import ReconciliationEngine, reconcile_transaction


@pytest.fixture
def sample_data():
    """Provides standard valid record dictionaries for unit testing."""
    payment = {
        "transaction_id": "TXN001",
        "merchant_id": "M001",
        "amount": 10000,
        "date": "2026-08-01",
        "status": "CAPTURED",
    }
    ledger = {
        "transaction_id": "TXN001",
        "gross_amount": 10000,
        "fee": 200,
        "net_amount": 9800,
        "date": "2026-08-01",
        "status": "POSTED",
    }
    bank = {
        "bank_reference": "BNK_REF_0001",
        "transaction_id": "TXN001",
        "credited_amount": 9800,
        "date": "2026-08-01",
    }
    return payment, ledger, bank


def test_successful_reconciliation(sample_data):
    """Test 1: Successful reconciliation when all 3 sources match perfectly."""
    payment, ledger, bank = sample_data
    result = reconcile_transaction(payment, ledger, bank)

    assert result["status"] == "RECONCILED"
    assert result["reason"] is None
    assert result["payment_amount"] == 10000
    assert result["gross_amount"] == 10000
    assert result["fee"] == 200
    assert result["expected_net_amount"] == 9800
    assert result["bank_amount"] == 9800
    assert result["difference"] == 0


def test_missing_ledger(sample_data):
    """Test 2: Rule 1 - Missing ledger record."""
    payment, _, bank = sample_data
    result = reconcile_transaction(payment, None, bank)

    assert result["status"] == "EXCEPTION"
    assert result["reason"] == "MISSING_LEDGER_RECORD"
    assert result["payment_amount"] == 10000
    assert result["gross_amount"] is None


def test_gross_amount_mismatch(sample_data):
    """Test 3: Rule 2 - Gross amount in ledger differs from payment amount."""
    payment, ledger, bank = sample_data
    ledger["gross_amount"] = 9500
    ledger["net_amount"] = 9300

    result = reconcile_transaction(payment, ledger, bank)

    assert result["status"] == "EXCEPTION"
    assert result["reason"] == "GROSS_AMOUNT_MISMATCH"
    assert result["payment_amount"] == 10000
    assert result["gross_amount"] == 9500


def test_ledger_calculation_error(sample_data):
    """Test 4: Rule 3 - Ledger net != gross - fee."""
    payment, ledger, bank = sample_data
    ledger["net_amount"] = 9000  # Should be 9800

    result = reconcile_transaction(payment, ledger, bank)

    assert result["status"] == "EXCEPTION"
    assert result["reason"] == "LEDGER_CALCULATION_ERROR"


def test_missing_bank_record(sample_data):
    """Test 5: Rule 4 - Missing bank statement record."""
    payment, ledger, _ = sample_data
    result = reconcile_transaction(payment, ledger, [])

    assert result["status"] == "EXCEPTION"
    assert result["reason"] == "MISSING_BANK_RECORD"


def test_bank_amount_mismatch(sample_data):
    """Test 6: Rule 5 - Bank credited amount differs from expected net amount."""
    payment, ledger, bank = sample_data
    bank["credited_amount"] = 9000  # Expected 9800

    result = reconcile_transaction(payment, ledger, bank)

    assert result["status"] == "EXCEPTION"
    assert result["reason"] == "BANK_AMOUNT_MISMATCH"
    assert result["difference"] == 800


def test_duplicate_bank_record(sample_data):
    """Test 7: Rule 6 - Multiple bank records for the same transaction ID."""
    payment, ledger, bank = sample_data
    bank_duplicate = {
        "bank_reference": "BNK_REF_0002",
        "transaction_id": "TXN001",
        "credited_amount": 9800,
        "date": "2026-08-01",
    }

    result = reconcile_transaction(payment, ledger, [bank, bank_duplicate])

    assert result["status"] == "EXCEPTION"
    assert result["reason"] == "DUPLICATE_BANK_RECORD"


def test_batch_reconciliation_processing(tmp_path):
    """Test 8: Batch reconciliation processes exactly 100 transactions without errors."""
    data_dir = str(tmp_path)
    generator = SyntheticDataGenerator(seed=42, total_transactions=100)
    p_path, l_path, b_path, *_ = generator.save_to_csv(data_dir)

    results, metrics = ReconciliationEngine.reconcile_batch(p_path, l_path, b_path)

    assert len(results) == 100
    assert metrics["total_records"] == 100
    assert metrics["reconciled_records"] + metrics["exception_records"] == 100
    assert metrics["match_rate"] > 0
    assert metrics["exception_rate"] > 0
    assert "breakdown" in metrics
    assert len(metrics["breakdown"]) > 0


def test_ground_truth_accuracy():
    """Test 9: Verify 100% agreement between deterministic reconciliation and generator ground truth."""
    generator = SyntheticDataGenerator(seed=42, total_transactions=100)
    payments, ledger_records, bank_records, adjustments, ground_truth = generator.generate()

    # Index records
    ledger_index = {row["transaction_id"]: row for row in ledger_records}
    bank_index = {}
    for row in bank_records:
        bank_index.setdefault(row["transaction_id"], []).append(row)

    gt_index = {row["transaction_id"]: row for row in ground_truth}

    for payment in payments:
        txn_id = payment["transaction_id"]
        ledger_entry = ledger_index.get(txn_id)
        bank_entries = bank_index.get(txn_id, [])

        result = reconcile_transaction(payment, ledger_entry, bank_entries)
        gt = gt_index[txn_id]

        assert result["status"] == gt["expected_status"], f"Status mismatch on {txn_id}"
        assert result["reason"] == gt["expected_exception"], f"Exception reason mismatch on {txn_id}"

