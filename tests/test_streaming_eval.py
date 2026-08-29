"""
Unit and integration tests for progressive streaming batch evaluations.
"""

import time
import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.run_llm_eval import run_evaluation

client = TestClient(app)


def test_evaluation_streaming_callbacks():
    """Test that run_evaluation triggers all progressive event callbacks."""
    events_received = []

    def callback(evt):
        events_received.append(evt)

    result = run_evaluation(
        provider="demo",
        cases=5,
        runs=1,
        batch_size=2,
        mode="batch",
        event_callback=callback,
    )

    assert result["status"] == "COMPLETED"
    assert "performance" in result
    perf = result["performance"]
    assert "time_to_first_batch_sec" in perf
    assert "total_processing_time_sec" in perf
    assert "average_batch_latency_sec" in perf
    assert perf["time_to_first_batch_sec"] > 0

    event_types = [e["event"] for e in events_received]
    assert "run_started" in event_types
    assert "batch_started" in event_types
    assert "case_completed" in event_types
    assert "batch_completed" in event_types
    assert "metrics_updated" in event_types
    assert "run_completed" in event_types


def test_evaluation_start_and_status_api():
    """Test POST /api/evaluations/start and GET /api/evaluations/{group_id}/status."""
    resp = client.post(
        "/api/evaluations/start",
        json={"provider": "demo", "cases_per_run": 5, "runs": 1},
    )

    assert resp.status_code == 202
    data = resp.json()
    assert "evaluation_group_id" in data
    assert data["status"] == "STARTED"
    assert "stream_url" in data

    group_id = data["evaluation_group_id"]

    # Allow worker thread a moment to finish demo run
    time.sleep(1.5)

    # Check status endpoint
    status_resp = client.get(f"/api/evaluations/{group_id}/status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["evaluation_group_id"] == group_id
    assert status_data["status"] in ("RUNNING", "COMPLETED")
