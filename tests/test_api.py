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


def test_validate_csv_dataset():
    """Test 10: POST /api/runs/validate verifies CSV schema and row counts."""
    p_csv = "transaction_id,amount\nTXN101,5000\nTXN102,12000"
    l_csv = "transaction_id,gross_amount,fee,net_amount\nTXN101,5000,100,4900\nTXN102,12000,240,11760"
    b_csv = "transaction_id,credited_amount\nTXN101,4900\nTXN102,11760"

    files = {
        "payments": ("payments.csv", p_csv, "text/csv"),
        "ledger": ("ledger.csv", l_csv, "text/csv"),
        "bank": ("bank.csv", b_csv, "text/csv"),
    }
    response = client.post("/api/runs/validate", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is True
    assert data["sources"]["payments"]["records"] == 2
    assert data["sources"]["ledger"]["records"] == 2
    assert data["sources"]["bank"]["records"] == 2


def test_create_run_from_upload():
    """Test 11: POST /api/runs/upload runs end-to-end reconciliation on user CSVs."""
    p_csv = "transaction_id,amount\nTXN201,10000\nTXN202,25000"
    l_csv = "transaction_id,gross_amount,fee,net_amount\nTXN201,10000,200,9800\nTXN202,25000,500,24500"
    b_csv = "transaction_id,credited_amount\nTXN201,9800\nTXN202,24500"

    files = {
        "payments": ("payments.csv", p_csv, "text/csv"),
        "ledger": ("ledger.csv", l_csv, "text/csv"),
        "bank": ("bank.csv", b_csv, "text/csv"),
    }
    response = client.post("/api/runs/upload", files=files)
    assert response.status_code == 201
    data = response.json()
    assert data["total_records"] == 2
    assert data["initial_reconciled"] == 2
    assert data["initial_match_rate"] == 100.0


def test_validate_csv_missing_files():
    """Test 12: POST /api/runs/validate reports missing required sources."""
    p_csv = "transaction_id,amount\nTXN101,5000"
    files = {
        "payments": ("payments.csv", p_csv, "text/csv"),
    }
    response = client.post("/api/runs/validate", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert data["sources"]["payments"]["valid"] is True
    assert data["sources"]["ledger"]["valid"] is False
    assert data["sources"]["bank"]["valid"] is False


def test_validate_csv_malformed_headers():
    """Test 13: POST /api/runs/validate handles malformed CSV headers."""
    p_csv = "wrong_id_col,amount\nTXN101,5000"
    l_csv = "transaction_id,gross_amount,fee\nTXN101,5000,100"
    b_csv = "transaction_id,credited_amount\nTXN101,4900"

    files = {
        "payments": ("payments.csv", p_csv, "text/csv"),
        "ledger": ("ledger.csv", l_csv, "text/csv"),
        "bank": ("bank.csv", b_csv, "text/csv"),
    }
    response = client.post("/api/runs/validate", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert "missing required columns" in data["sources"]["payments"]["error"]


def test_upload_csv_missing_required_file():
    """Test 14: POST /api/runs/upload returns 422 if required file is omitted."""
    p_csv = "transaction_id,amount\nTXN101,5000"
    files = {
        "payments": ("payments.csv", p_csv, "text/csv"),
        # Missing ledger and bank
    }
    response = client.post("/api/runs/upload", files=files)
    assert response.status_code == 422


def test_upload_csv_malformed_headers():
    """Test 15: POST /api/runs/upload returns 400 for malformed CSV columns."""
    p_csv = "bad_col,amount\nTXN101,5000"
    l_csv = "transaction_id,gross_amount,fee\nTXN101,5000,100"
    b_csv = "transaction_id,credited_amount\nTXN101,4900"

    files = {
        "payments": ("payments.csv", p_csv, "text/csv"),
        "ledger": ("ledger.csv", l_csv, "text/csv"),
        "bank": ("bank.csv", b_csv, "text/csv"),
    }
    response = client.post("/api/runs/upload", files=files)
    assert response.status_code == 400
    assert "missing required columns" in response.json()["detail"]


def test_wrong_http_method_405():
    """Test 16: Wrong HTTP methods on upload/validate routes return 405 Method Not Allowed."""
    # GET on POST-only route /api/runs/upload
    resp_get_upload = client.get("/api/runs/upload")
    assert resp_get_upload.status_code == 405

    # GET on POST-only route /api/runs/validate
    resp_get_validate = client.get("/api/runs/validate")
    assert resp_get_validate.status_code == 405

    # PUT on POST-only route /api/runs/upload
    resp_put_upload = client.put("/api/runs/upload")
    assert resp_put_upload.status_code == 405


def test_direct_api_validate_and_upload_aliases():
    """Test 17: Direct /api/validate and /api/upload aliases work identically."""
    p_csv = "transaction_id,amount\nTXN301,8000"
    l_csv = "transaction_id,gross_amount,fee\nTXN301,8000,160"
    b_csv = "transaction_id,credited_amount\nTXN301,7840"

    files = {
        "payments": ("payments.csv", p_csv, "text/csv"),
        "ledger": ("ledger.csv", l_csv, "text/csv"),
        "bank": ("bank.csv", b_csv, "text/csv"),
    }
    # Test /api/validate alias
    val_resp = client.post("/api/validate", files=files)
    assert val_resp.status_code == 200
    assert val_resp.json()["valid"] is True

    # Test /api/upload alias
    files_upload = {
        "payments": ("payments.csv", p_csv, "text/csv"),
        "ledger": ("ledger.csv", l_csv, "text/csv"),
        "bank": ("bank.csv", b_csv, "text/csv"),
    }
    up_resp = client.post("/api/upload", files=files_upload)
    assert up_resp.status_code == 201
    assert up_resp.json()["total_records"] == 1


def test_export_run_transactions_csv():
    """Test 18: GET /api/runs/{run_id}/export/csv returns downloadable reconciliation ledger CSV."""
    list_resp = client.get("/api/runs")
    run_id = list_resp.json()[0]["run_id"]

    resp = client.get(f"/api/runs/{run_id}/export/csv")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers.get("content-disposition", "")
    assert f"reconciliation_ledger_{run_id}.csv" in resp.headers.get("content-disposition", "")

    csv_text = resp.text
    lines = csv_text.strip().split("\n")
    assert len(lines) >= 2  # Header + records
    assert "Transaction ID" in lines[0]
    assert "Status" in lines[0]
    assert "Bank Amount" in lines[0]



