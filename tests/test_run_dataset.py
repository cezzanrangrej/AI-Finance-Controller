"""
Unit and integration tests for dataset CLI runner (src/run_dataset.py).
"""

import os
import sys
from decimal import Decimal
from unittest.mock import MagicMock, patch
import pytest

from src.generator import SyntheticDataGenerator
from src.reconciliation import ReconciliationEngine
from scripts.run_dataset import (
    load_dataset,
    validate_dataset_dir,
    detect_source_type,
    main,
    REQUIRED_FILES,
    _CANONICAL_DATA_DIR,
)
from src.agent.schemas import AgentDecision, InvestigationLog


@pytest.fixture
def temp_dataset_dir(tmp_path):
    """Generates a valid four-file synthetic dataset in a temp directory."""
    data_dir = str(tmp_path / "dataset")
    generator = SyntheticDataGenerator(seed=42, total_transactions=100)
    p_path, l_path, b_path, a_path = generator.save_to_csv(data_dir)
    return data_dir, (p_path, l_path, b_path, a_path)


def make_test_decision(txn_id="TXN001", decision="AUTO_RESOLVED", resolution="ADJUSTMENT_EXPLAINED"):
    return AgentDecision(
        transaction_id=txn_id,
        decision=decision,
        exception_type="GROSS_AMOUNT_MISMATCH",
        resolution_type=resolution,
        resolved_difference=100.0,
        reason="Test reason",
        evidence=["Test evidence"],
        confidence=0.9,
        recommended_action="Test action",
    )


# ---------------------------------------------------------------------------
# Test 1: Valid four-file dataset
# ---------------------------------------------------------------------------
def test_valid_four_file_dataset(temp_dataset_dir):
    data_dir, paths = temp_dataset_dir
    file_map = validate_dataset_dir(data_dir)
    assert len(file_map) == 4
    for fname in REQUIRED_FILES:
        assert fname in file_map
        assert os.path.exists(file_map[fname])

    payments, ledger, bank, adjustments, ground_truth, _ = load_dataset(data_dir)
    assert len(payments) == 100
    assert len(ledger) > 0
    assert len(bank) > 0
    assert len(adjustments) >= 0


# ---------------------------------------------------------------------------
# Test 2: Missing payments.csv
# ---------------------------------------------------------------------------
def test_missing_payments_csv(temp_dataset_dir):
    data_dir, (p_path, _, _, _) = temp_dataset_dir
    os.remove(p_path)
    with pytest.raises(FileNotFoundError) as exc_info:
        validate_dataset_dir(data_dir)
    assert "payments.csv" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Test 3: Missing ledger.csv
# ---------------------------------------------------------------------------
def test_missing_ledger_csv(temp_dataset_dir):
    data_dir, (_, l_path, _, _) = temp_dataset_dir
    os.remove(l_path)
    with pytest.raises(FileNotFoundError) as exc_info:
        validate_dataset_dir(data_dir)
    assert "ledger.csv" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Test 4: Missing bank.csv
# ---------------------------------------------------------------------------
def test_missing_bank_csv(temp_dataset_dir):
    data_dir, (_, _, b_path, _) = temp_dataset_dir
    os.remove(b_path)
    with pytest.raises(FileNotFoundError) as exc_info:
        validate_dataset_dir(data_dir)
    assert "bank.csv" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Test 5: Missing adjustments.csv
# ---------------------------------------------------------------------------
def test_missing_adjustments_csv(temp_dataset_dir):
    data_dir, (_, _, _, a_path) = temp_dataset_dir
    os.remove(a_path)
    with pytest.raises(FileNotFoundError) as exc_info:
        validate_dataset_dir(data_dir)
    assert "adjustments.csv" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Test 6: Malformed CSV
# ---------------------------------------------------------------------------
def test_malformed_csv(tmp_path):
    bad_dir = tmp_path / "bad_dataset"
    bad_dir.mkdir()
    for fname in REQUIRED_FILES:
        (bad_dir / fname).write_text("invalid_header_1,invalid_header_2\n")

    payments, ledger, bank, adjustments, ground_truth, _ = load_dataset(str(bad_dir))
    results, metrics = ReconciliationEngine.reconcile_records(payments, ledger, bank)
    assert isinstance(results, list)
    assert isinstance(metrics, dict)


# ---------------------------------------------------------------------------
# Test 7: Dataset isolation (custom folder dataset does not touch canonical data)
# ---------------------------------------------------------------------------
def test_dataset_isolation(temp_dataset_dir):
    data_dir, _ = temp_dataset_dir
    canonical_payments = os.path.join(_CANONICAL_DATA_DIR, "payments.csv")
    if os.path.exists(canonical_payments):
        mtime_before = os.path.getmtime(canonical_payments)
    else:
        mtime_before = None

    exit_code = main(["--data-dir", data_dir, "--mode", "phase1"])
    assert exit_code == 0

    if mtime_before is not None:
        mtime_after = os.path.getmtime(canonical_payments)
        assert mtime_before == mtime_after, "Canonical data/payments.csv was modified!"


# ---------------------------------------------------------------------------
# Test 8: Decimal preservation
# ---------------------------------------------------------------------------
def test_decimal_preservation(tmp_path):
    dec_dir = tmp_path / "dec_dataset"
    dec_dir.mkdir()
    (dec_dir / "payments.csv").write_text("transaction_id,merchant_id,amount,date,status\nTXN001,M001,100.55,2026-01-01,SETTLED\n")
    (dec_dir / "ledger.csv").write_text("transaction_id,gross_amount,fee,net_amount,date,status\nTXN001,100.55,2.00,98.55,2026-01-01,POSTED\n")
    (dec_dir / "bank.csv").write_text("bank_reference,transaction_id,credited_amount,date\nBNK001,TXN001,98.55,2026-01-01\n")
    (dec_dir / "adjustments.csv").write_text("transaction_id,adjustment_type,amount,reason,date,reference\n")

    payments, ledger, bank, adjustments, ground_truth, _ = load_dataset(str(dec_dir))
    results, metrics = ReconciliationEngine.reconcile_records(payments, ledger, bank)

    assert len(results) == 1
    assert results[0]["status"] == "RECONCILED"
    assert ReconciliationEngine._safe_decimal("100.55") == Decimal("100.55")


# ---------------------------------------------------------------------------
# Test 9: Phase 1 result correctness
# ---------------------------------------------------------------------------
def test_phase1_result(temp_dataset_dir):
    data_dir, _ = temp_dataset_dir
    exit_code = main(["--data-dir", data_dir, "--mode", "phase1"])
    assert exit_code == 0

    payments, ledger, bank, adjustments, ground_truth, _ = load_dataset(data_dir)
    results, metrics = ReconciliationEngine.reconcile_records(payments, ledger, bank)
    assert metrics["total_records"] == 100
    assert metrics["reconciled_records"] + metrics["exception_records"] == 100
    assert "breakdown" in metrics


# ---------------------------------------------------------------------------
# Test 10: Batch mode integration (Mocked LLM)
# ---------------------------------------------------------------------------
def test_batch_mode_integration(temp_dataset_dir):
    data_dir, _ = temp_dataset_dir

    mock_decision = make_test_decision("TXN001", "AUTO_RESOLVED", "ADJUSTMENT_EXPLAINED")
    mock_log = MagicMock()
    mock_log.batch_size = 1
    mock_log.fallback_count = 0
    mock_log.llm_interactions = 2

    with patch("src.agent.multi_agent.batch_multi_agent_controller.BatchMultiAgentController") as mock_batch_cls:
        mock_instance = mock_batch_cls.return_value
        mock_instance.investigate_batch.return_value = ([mock_decision], mock_log)

        exit_code = main([
            "--data-dir", data_dir,
            "--mode", "batch",
            "--provider", "demo",
            "--cases", "1",
        ])
        assert exit_code == 0
        assert mock_instance.investigate_batch.called


# ---------------------------------------------------------------------------
# Test 11: Individual mode integration (Mocked LLM)
# ---------------------------------------------------------------------------
def test_individual_mode_integration(temp_dataset_dir):
    data_dir, _ = temp_dataset_dir

    mock_decision = make_test_decision("TXN001", "HUMAN_REVIEW", "NONE")
    mock_log = MagicMock(spec=InvestigationLog)

    with patch("scripts.run_dataset.AgentController") as mock_agent_cls:
        mock_instance = mock_agent_cls.return_value
        mock_instance.investigate_exception.return_value = (mock_decision, mock_log)

        exit_code = main([
            "--data-dir", data_dir,
            "--mode", "individual",
            "--provider", "demo",
            "--cases", "1",
        ])
        assert exit_code == 0
        assert mock_instance.investigate_exception.called


# ---------------------------------------------------------------------------
# Test 12: Multi-agent mode integration (Mocked Orchestrator)
# ---------------------------------------------------------------------------
def test_multi_agent_integration(temp_dataset_dir):
    data_dir, _ = temp_dataset_dir

    mock_decision = make_test_decision("TXN001", "AUTO_RESOLVED", "ADJUSTMENT_EXPLAINED")
    mock_log = MagicMock()
    mock_log.batch_size = 1
    mock_log.fallback_count = 0
    mock_log.llm_interactions = 2

    with patch("src.agent.multi_agent.batch_multi_agent_controller.BatchMultiAgentController") as mock_batch_cls:
        mock_instance = mock_batch_cls.return_value
        mock_instance.investigate_batch.return_value = ([mock_decision], mock_log)

        exit_code = main([
            "--data-dir", data_dir,
            "--mode", "multi-agent",
            "--provider", "demo",
            "--cases", "1",
        ])
        assert exit_code == 0
        assert mock_instance.investigate_batch.called


# ---------------------------------------------------------------------------
# Test 13: No canonical data modification
# ---------------------------------------------------------------------------
def test_no_canonical_data_modification(temp_dataset_dir):
    data_dir, _ = temp_dataset_dir
    canonical_files = ["payments.csv", "ledger.csv", "bank.csv", "adjustments.csv"]

    mtimes = {}
    for fname in canonical_files:
        fpath = os.path.join(_CANONICAL_DATA_DIR, fname)
        if os.path.exists(fpath):
            mtimes[fname] = os.path.getmtime(fpath)

    exit_code = main(["--data-dir", data_dir, "--mode", "phase1"])
    assert exit_code == 0

    for fname, mtime_before in mtimes.items():
        fpath = os.path.join(_CANONICAL_DATA_DIR, fname)
        assert os.path.getmtime(fpath) == mtime_before, f"Canonical {fname} was modified!"


# ---------------------------------------------------------------------------
# Test 14: Ground-truth transaction evaluation output when ground_truth.csv exists
# ---------------------------------------------------------------------------
def test_ground_truth_evaluation_output_when_present(temp_dataset_dir, capsys):
    data_dir, _ = temp_dataset_dir
    generator = SyntheticDataGenerator(seed=42, total_transactions=20)
    generator.save_ground_truth_csv(data_dir)

    mock_decision = make_test_decision("TXN003", "AUTO_RESOLVED", "ADJUSTMENT_EXPLAINED")
    mock_log = MagicMock()
    mock_log.batch_size = 1
    mock_log.fallback_count = 0
    mock_log.llm_interactions = 1

    with patch("scripts.run_dataset.BatchAgentController") as mock_batch_cls:
        mock_instance = mock_batch_cls.return_value
        mock_instance.investigate_batch.return_value = ([mock_decision], mock_log)

        exit_code = main([
            "--data-dir", data_dir,
            "--mode", "batch",
            "--provider", "demo",
            "--cases", "1",
        ])
        assert exit_code == 0
        captured = capsys.readouterr().out
        assert "TRANSACTION EVALUATION RESULTS" in captured
        assert "EVALUATION SUMMARY" in captured
        assert "Decision accuracy:" in captured
        assert "Ground-truth AUTO_RESOLVED:" in captured
