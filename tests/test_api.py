"""
Unit and integration tests for FastAPI REST endpoints and Database persistence (Phase 3.1).
"""

import os
import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.db.database import Base, SessionLocal, engine

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def setup_database():
    """Initialises database tables before running API tests."""
    Base.metadata.create_all(bind=engine)
    yield
    # Cleanup tables after test module completes
    Base.metadata.drop_all(bind=engine)


def test_health_check():
    """Test 1: Health check endpoint returns 200 OK."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_create_run_e2e_phase31():
    """Test 2: POST /api/runs executes pipeline, produces AUTO_RESOLVED & HUMAN_REVIEW decisions, and persists metrics."""
    response = client.post("/api/runs")
    assert response.status_code == 201

    data = response.json()
    assert "run_id" in data
    assert data["total_records"] == 100
    assert data["initial_reconciled"] == 70
    assert data["initial_exceptions"] == 30

    # Phase 3.1 requirement: Both AUTO_RESOLVED and HUMAN_REVIEW must be produced!
    assert data["ai_auto_resolved"] > 0
    assert data["human_review"] > 0
    assert data["ai_auto_resolved"] + data["human_review"] == 30

    assert data["phase1_accuracy"] == 100.0
    assert data["phase2_accuracy"] == 100.0
    assert data["auto_resolution_precision"] == 100.0
    assert data["auto_resolution_recall"] == 100.0

    assert data["phase1_time_sec"] >= 0
    assert data["phase2_time_sec"] >= 0
    assert data["end_to_end_time_sec"] >= 0


def test_list_runs():
    """Test 3: GET /api/runs lists recent execution runs."""
    response = client.get("/api/runs")
    assert response.status_code == 200
    runs = response.json()
    assert isinstance(runs, list)
    assert len(runs) >= 1
    assert "run_id" in runs[0]


def test_get_run_metrics():
    """Test 4: GET /api/runs/{run_id}/metrics returns Phase 3.1 metrics, precision, recall, & timing."""
    list_resp = client.get("/api/runs")
    run_id = list_resp.json()[0]["run_id"]

    response = client.get(f"/api/runs/{run_id}/metrics")
    assert response.status_code == 200

    metrics = response.json()
    assert metrics["run_id"] == run_id
    assert metrics["total_records"] == 100
    assert "exception_breakdown" in metrics
    assert metrics["phase1_accuracy"] == 100.0
    assert metrics["phase2_accuracy"] == 100.0
    assert metrics["auto_resolution_precision"] == 100.0
    assert metrics["auto_resolution_recall"] == 100.0


def test_get_run_exceptions_filtered_by_decision():
    """Test 5: GET /api/runs/{run_id}/exceptions filtered by AUTO_RESOLVED & HUMAN_REVIEW."""
    list_resp = client.get("/api/runs")
    run_id = list_resp.json()[0]["run_id"]

    # All exceptions
    resp_all = client.get(f"/api/runs/{run_id}/exceptions")
    assert resp_all.status_code == 200
    exceptions = resp_all.json()
    assert len(exceptions) == 30

    # Filter decision=AUTO_RESOLVED
    resp_auto = client.get(f"/api/runs/{run_id}/exceptions?decision=AUTO_RESOLVED")
    assert resp_auto.status_code == 200
    auto_cases = resp_auto.json()
    assert len(auto_cases) > 0

    # Filter decision=HUMAN_REVIEW
    resp_hr = client.get(f"/api/runs/{run_id}/exceptions?decision=HUMAN_REVIEW")
    assert resp_hr.status_code == 200
    hr_cases = resp_hr.json()
    assert len(hr_cases) > 0

    assert len(auto_cases) + len(hr_cases) == 30


def test_get_transactions_and_adjustments_detail():
    """Test 6: GET /api/runs/{run_id}/transactions/{transaction_id} returns adjustments list."""
    list_resp = client.get("/api/runs")
    run_id = list_resp.json()[0]["run_id"]

    resp_list = client.get(f"/api/runs/{run_id}/transactions")
    assert resp_list.status_code == 200
    txns = resp_list.json()
    assert len(txns) == 100

    # Test detail for single transaction
    sample_txn_id = txns[0]["transaction_id"]
    resp_detail = client.get(f"/api/runs/{run_id}/transactions/{sample_txn_id}")
    assert resp_detail.status_code == 200
    detail = resp_detail.json()
    assert detail["transaction_id"] == sample_txn_id
    assert "adjustments" in detail


def test_get_audit_trail():
    """Test 7: GET /api/runs/{run_id}/audit returns chronological events."""
    list_resp = client.get("/api/runs")
    run_id = list_resp.json()[0]["run_id"]

    response = client.get(f"/api/runs/{run_id}/audit")
    assert response.status_code == 200
    events = response.json()
    assert isinstance(events, list)
    assert len(events) >= 100


def test_invalid_run_id_404():
    """Test 8: 404 Error handling for non-existent run ID."""
    response = client.get("/api/runs/run_invalid_9999/metrics")
    assert response.status_code == 404


def test_invalid_transaction_id_404():
    """Test 9: 404 Error handling for non-existent transaction ID."""
    list_resp = client.get("/api/runs")
    run_id = list_resp.json()[0]["run_id"]

    response = client.get(f"/api/runs/{run_id}/transactions/TXN999999")
    assert response.status_code == 404
