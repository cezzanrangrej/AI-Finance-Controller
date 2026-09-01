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
    assert "run_completed" in event_types


def test_evaluation_sse_stream_payload_contract():
    """Test the exact SSE event contract over /api/evaluations/{group_id}/stream."""
    import json
    from datetime import datetime

    # 1. Start stream
    start_resp = client.post(
        "/api/evaluations/start",
        json={"provider": "demo", "cases_per_run": 5, "runs": 1, "batch_size": 5},
    )
    assert start_resp.status_code == 202
    group_id = start_resp.json()["evaluation_group_id"]

    # 2. Read live stream
    captured = {}
    with client.stream("GET", f"/api/evaluations/{group_id}/stream") as response:
        for line in response.iter_lines():
            if not line:
                continue
            if line.startswith("data:"):
                raw_data = line[5:].strip()
                parsed = json.loads(raw_data)
                ev = parsed.get("event")
                if ev:
                    captured[ev] = parsed
            if "run_completed" in captured:
                break

    assert "batch_completed" in captured
    assert "case_completed" in captured

    # Assert batch_completed contract
    bc = captured["batch_completed"]
    assert "results" in bc
    assert isinstance(bc["results"], list)
    assert len(bc["results"]) > 0
    first_res = bc["results"][0]
    assert "transaction_id" in first_res
    assert "decision" in first_res
    assert "reason" in first_res
    assert "confidence" in first_res
    assert "recommended_action" in first_res
    assert "timestamp" in bc
    # Verify ISO timestamp
    datetime.fromisoformat(bc["timestamp"].replace("Z", "+00:00"))

    # Assert case_completed contract
    cc = captured["case_completed"]
    assert "transaction_id" in cc
    assert "decision" in cc
    assert "reason" in cc
    assert "confidence" in cc


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


def test_evaluation_cases_default_resolution_and_iso_timestamps():
    """
    Asserts that:
    1. cases_per_run=None defaults to 100% of detected Phase 1 exceptions (30 cases).
    2. cases_per_run=0 also defaults to 100% of detected Phase 1 exceptions.
    3. All lifecycle boundary events emit standard ISO 8601 timestamps.
    """
    import json
    from datetime import datetime

    # 1. Test cases_per_run=None (full dataset coverage)
    resp_none = client.post(
        "/api/evaluations/start",
        json={"provider": "demo", "cases_per_run": None, "runs": 1, "batch_size": 5},
    )
    assert resp_none.status_code == 202
    group_none = resp_none.json()["evaluation_group_id"]

    captured_events = {}
    with client.stream("GET", f"/api/evaluations/{group_none}/stream") as response:
        for line in response.iter_lines():
            if not line or not line.startswith("data:"):
                continue
            parsed = json.loads(line[5:].strip())
            ev = parsed.get("event")
            if ev and ev not in captured_events:
                captured_events[ev] = parsed
            if "run_completed" in captured_events:
                break

    assert "phase1_started" in captured_events
    assert "phase1_completed" in captured_events
    assert "run_started" in captured_events
    assert "run_completed" in captured_events

    # Verify all 30 exceptions were evaluated
    run_started = captured_events["run_started"]
    assert run_started["total_cases"] == 30
    assert run_started["cases_per_run"] == 30

    # Verify lifecycle timestamps are valid ISO 8601 strings
    for ev_name in ("phase1_started", "phase1_completed", "run_started", "run_completed"):
        ts_val = captured_events[ev_name]["timestamp"]
        assert isinstance(ts_val, str), f"{ev_name} timestamp must be an ISO string, got {type(ts_val)}"
        datetime.fromisoformat(ts_val.replace("Z", "+00:00"))

    # 2. Test cases_per_run=0 also resolves to 100% coverage
    resp_zero = client.post(
        "/api/evaluations/start",
        json={"provider": "demo", "cases_per_run": 0, "runs": 1, "batch_size": 5},
    )
    assert resp_zero.status_code == 202
    group_zero = resp_zero.json()["evaluation_group_id"]

    with client.stream("GET", f"/api/evaluations/{group_zero}/stream") as response:
        for line in response.iter_lines():
            if not line or not line.startswith("data:"):
                continue
            parsed = json.loads(line[5:].strip())
            if parsed.get("event") == "run_started":
                assert parsed["total_cases"] == 30
                assert parsed["cases_per_run"] == 30
                break

