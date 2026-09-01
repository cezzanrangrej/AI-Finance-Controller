"""
Tests for reporting module and CLI script.
"""

import json
import subprocess
import sys
import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.db.database import Base, SessionLocal, engine
from src.reporting.exception_report import build_exception_report, format_as_markdown

import uuid
from src.db.repository import FinanceRepository
from src.db.models import RunModel


@pytest.fixture(scope="module", autouse=True)
def setup_test_run():
    """Initializes DB and creates a sample reconciliation run directly."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    run_id = f"test_run_report_{uuid.uuid4().hex[:8]}"

    run_data = {
        "id": run_id,
        "total_records": 10,
        "initial_reconciled": 7,
        "initial_exceptions": 3,
        "ai_auto_resolved": 1,
        "human_review": 2,
        "final_resolved": 8,
        "final_unresolved": 2,
        "initial_match_rate": 70.0,
        "agent_resolution_rate": 33.3,
        "final_resolution_rate": 80.0,
        "llm_provider": "demo",
        "llm_mode": "DEMO",
        "llm_model": "demo-v1",
        "prompt_tokens": 500,
        "completion_tokens": 200,
        "total_tokens": 700,
        "phase1_time_sec": 0.005,
        "phase2_time_sec": 0.05,
        "end_to_end_time_sec": 0.06,
        "total_processing_time_sec": 0.06,
        "records_per_second": 166.7,
    }
    FinanceRepository.create_run(db, run_data)

    txns = [
        {"transaction_id": "TXN001", "status": "RECONCILED", "payment_amount": 1000, "expected_net_amount": 980, "bank_amount": 980},
        {"transaction_id": "TXN002", "status": "EXCEPTION", "exception_type": "BANK_AMOUNT_MISMATCH", "payment_amount": 2000, "expected_net_amount": 1960, "bank_amount": 1860, "difference": -100},
        {"transaction_id": "TXN003", "status": "EXCEPTION", "exception_type": "MISSING_LEDGER_RECORD", "payment_amount": 3000, "expected_net_amount": None, "bank_amount": 2940, "difference": 2940},
        {"transaction_id": "TXN004", "status": "EXCEPTION", "exception_type": "BANK_AMOUNT_MISMATCH", "payment_amount": 4000, "expected_net_amount": 3920, "bank_amount": 3000, "difference": -920},
    ]
    FinanceRepository.save_transaction_results(db, run_id, txns)

    adjs = [
        {"transaction_id": "TXN002", "adjustment_type": "FEE_DISPUTE", "amount": 100.0, "reason": "Processing fee rebate", "reference": "ADJ01", "date": "2026-08-15"}
    ]
    FinanceRepository.save_adjustments(db, run_id, adjs)

    investigations = [
        {
            "transaction_id": "TXN002",
            "initial_exception": "BANK_AMOUNT_MISMATCH",
            "decision": "AUTO_RESOLVED",
            "resolution_type": "ADJUSTMENT_EXPLAINED",
            "resolved_difference": -100.0,
            "reason": "Difference of 100 explained by fee adjustment.",
            "recommended_action": "Post adjustment to general ledger.",
            "confidence": 1.0,
            "evidence": ["Adjustment ADJ01 found for 100"],
            "tools_used": ["get_adjustments", "calculate_settlement"],
        },
        {
            "transaction_id": "TXN003",
            "initial_exception": "MISSING_LEDGER_RECORD",
            "decision": "HUMAN_REVIEW",
            "resolution_type": "NONE",
            "resolved_difference": None,
            "reason": "Ledger entry missing for captured payment.",
            "recommended_action": "Manual booking in ERP ledger required.",
            "confidence": 0.0,
            "evidence": ["Payment CAPTURED but ledger empty"],
            "tools_used": ["get_payment", "get_ledger"],
        },
        {
            "transaction_id": "TXN004",
            "initial_exception": "BANK_AMOUNT_MISMATCH",
            "decision": "HUMAN_REVIEW",
            "resolution_type": "NONE",
            "resolved_difference": None,
            "reason": "Unexplained shortfall of 920 without adjustment records.",
            "recommended_action": "Contact acquiring bank settlement desk.",
            "confidence": 0.0,
            "evidence": ["No adjustments found"],
            "tools_used": ["get_adjustments"],
        },
    ]
    FinanceRepository.save_agent_investigations(db, run_id, investigations)
    db.close()

    yield run_id
    Base.metadata.drop_all(bind=engine)


def test_build_exception_report(setup_test_run):
    run_id = setup_test_run
    db = SessionLocal()
    try:
        report = build_exception_report(db, run_id)
        assert report.run_id == run_id
        assert report.summary["total_records"] == 10
        assert report.summary["initial_exceptions"] == 3
        assert len(report.auto_resolved_cases) == 1
        assert len(report.human_review_cases) == 2
        assert len(report.exceptions_breakdown) > 0

        as_dict = report.as_dict()
        assert isinstance(as_dict, dict)
        assert as_dict["run_id"] == run_id
        assert "summary" in as_dict
        assert "auto_resolved_cases" in as_dict
        assert "human_review_cases" in as_dict
    finally:
        db.close()


def test_build_exception_report_not_found():
    db = SessionLocal()
    try:
        with pytest.raises(ValueError, match="Run 'non_existent_run' not found"):
            build_exception_report(db, "non_existent_run")
    finally:
        db.close()


def test_format_as_markdown(setup_test_run):
    run_id = setup_test_run
    db = SessionLocal()
    try:
        report = build_exception_report(db, run_id)
        md = format_as_markdown(report)
        assert "# Financial Reconciliation Exception Report" in md
        assert run_id in md
        assert "Executive Summary" in md
        assert "Exception Breakdown by Category" in md
        assert "Auto-Resolved Discrepancies" in md
        assert "Human Review Escalations" in md
    finally:
        db.close()


def test_cli_generate_report_markdown(setup_test_run, monkeypatch, capsys):
    from scripts.generate_report import main
    run_id = setup_test_run
    monkeypatch.setattr(sys, "argv", ["generate_report.py", "--run-id", run_id])
    ret = main()
    assert ret == 0
    captured = capsys.readouterr()
    assert "# Financial Reconciliation Exception Report" in captured.out
    assert run_id in captured.out


def test_cli_generate_report_json(setup_test_run, monkeypatch, capsys):
    from scripts.generate_report import main
    run_id = setup_test_run
    monkeypatch.setattr(sys, "argv", ["generate_report.py", "--run-id", run_id, "--format", "json"])
    ret = main()
    assert ret == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["run_id"] == run_id
    assert "summary" in data


def test_cli_generate_report_file_out(setup_test_run, monkeypatch, capsys, tmp_path):
    from scripts.generate_report import main
    run_id = setup_test_run
    out_file = str(tmp_path / "test_report.md")
    monkeypatch.setattr(sys, "argv", ["generate_report.py", "--run-id", run_id, "--out", out_file])
    ret = main()
    assert ret == 0
    with open(out_file, "r", encoding="utf-8") as f:
        content = f.read()
    assert "# Financial Reconciliation Exception Report" in content
    assert run_id in content


def test_cli_generate_report_not_found(monkeypatch, capsys):
    from scripts.generate_report import main
    monkeypatch.setattr(sys, "argv", ["generate_report.py", "--run-id", "missing_run_id"])
    ret = main()
    assert ret == 1
    captured = capsys.readouterr()
    assert "Error: Run 'missing_run_id' not found." in captured.err
