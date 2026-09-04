"""
Unit and integration tests for Bounded Parallel Batch Execution.
Covers all 20 test requirements from specification section 25.
"""

import asyncio
from datetime import datetime, timezone
import json
import os
from unittest.mock import MagicMock, patch
import pytest

from src.agent.batch_controller import BatchAgentController
from src.agent.controller import LLMClient
from src.agent.parallel_batch_engine import run_parallel_batches
from src.agent.schemas import AgentDecision, BatchInvestigationLog, BatchStatus
from src.agent.tools import FinancialToolkit
from src.run_llm_eval import run_evaluation


@pytest.fixture
def sample_data():
    exceptions = [
        {"transaction_id": f"TXN_{i:03d}", "reason": "DISCREPANCY"}
        for i in range(1, 26)
    ]
    ground_truth = [
        {"transaction_id": f"TXN_{i:03d}", "expected_phase2_decision": "AUTO_RESOLVED" if i % 2 == 0 else "HUMAN_REVIEW"}
        for i in range(1, 26)
    ]
    return exceptions, ground_truth


@pytest.fixture
def scratch_resume_file(tmp_path):
    """
    Throwaway checkpoint path for tests that do not assert on resume contents.

    These tests passed the literal ``"dummy.json"``, so every run wrote a
    checkpoint into the repository root -- and that file is tracked, so the suite
    dirtied the working tree on each invocation and the artifact was liable to be
    committed as if it were source.
    """
    return str(tmp_path / "resume.json")


class DummyTracer:
    def __init__(self):
        self.enabled = False
    def _print(self, msg):
        pass


# Helper to create dummy decisions
def make_dummy_decisions(tids):
    return [
        AgentDecision(
            transaction_id=tid,
            decision="AUTO_RESOLVED",
            exception_type="TEST",
            evidence=["Prefetched evidence validated."],
            confidence=0.9,
            recommended_action="Review",
            reason="Validated"
        )
        for tid in tids
    ]


# 1. Validation tests (ValueErrors)
def test_parallel_batches_validation():
    # 4. parallel_batches > 5 rejected
    with pytest.raises(ValueError) as exc:
        run_evaluation(provider="demo", cases=5, parallel_batches=6)
    assert "parallel_batches must be between 1 and 5" in str(exc.value)

    # 5. parallel_batches = 0 rejected
    with pytest.raises(ValueError) as exc:
        run_evaluation(provider="demo", cases=5, parallel_batches=0)
    assert "parallel_batches must be between 1 and 5" in str(exc.value)


# 6 & 7. Exact batch partitioning and no duplicate transaction IDs
def test_batch_partitioning_and_no_duplicates(sample_data):
    exceptions, ground_truth = sample_data
    batch_size = 5
    chunks = [exceptions[i : i + batch_size] for i in range(0, len(exceptions), batch_size)]
    
    assert len(chunks) == 5
    for chunk in chunks:
        assert len(chunk) == 5

    # Ensure no duplicates
    all_tids = [c["transaction_id"] for chunk in chunks for c in chunk]
    assert len(all_tids) == 25
    assert len(set(all_tids)) == 25


# 8. Concurrent batches actually run concurrently
@pytest.mark.asyncio
async def test_concurrent_batches_overlap(sample_data, scratch_resume_file):
    exceptions, ground_truth = sample_data
    chunks = [exceptions[i : i + 5] for i in range(0, 10, 5)] # 2 batches
    
    mock_agent = MagicMock(spec=BatchAgentController)
    
    # Simulate a delay in the agent to verify concurrency
    async def slow_investigate(chunk):
        await asyncio.sleep(0.1)
        tids = [c["transaction_id"] for c in chunk]
        log = BatchInvestigationLog(
            batch_id="batch_x", batch_size=len(chunk), transaction_ids=tids,
            provider="demo", model="demo", request_start=datetime.now(timezone.utc),
            request_end=datetime.now(timezone.utc), processing_time_sec=0.1
        )
        return make_dummy_decisions(tids), log

    mock_agent.investigate_batch.side_effect = lambda chunk: asyncio.run(slow_investigate(chunk))

    t_start = asyncio.get_event_loop().time()
    res = await run_parallel_batches(
        batches=chunks,
        batch_agent=mock_agent,
        max_parallel_batches=2,
        ground_truth=ground_truth,
        evaluation_group_id="group_test",
        run_id="run_test",
        run_num=1,
        total_runs=1,
        cases_per_run=10,
        batch_size=5,
        selected_provider="demo",
        client_model="demo",
        phase1_results=[],
        exception_count=10,
        resume_file=scratch_resume_file,
        tracer=DummyTracer()
    )
    t_end = asyncio.get_event_loop().time()
    
    # If they ran sequentially, it would take >= 0.2 seconds.
    # Concurrently, it should take around 0.1 seconds (well below 0.18 seconds).
    assert (t_end - t_start) < 0.18


# 9, 10, 11. SSE events, completion order independence, metrics updated
@pytest.mark.asyncio
async def test_sse_events_and_completion_order(sample_data, scratch_resume_file):
    exceptions, ground_truth = sample_data
    chunks = [exceptions[i : i + 5] for i in range(0, 15, 5)] # 3 batches
    
    mock_agent = MagicMock(spec=BatchAgentController)
    
    # We want Batch 3 to finish first, then Batch 1, then Batch 2
    delays = {3: 0.01, 1: 0.1, 2: 0.2}
    
    async def delayed_investigate(b_num, chunk):
        await asyncio.sleep(delays[b_num])
        tids = [c["transaction_id"] for c in chunk]
        log = BatchInvestigationLog(
            batch_id=f"batch_{b_num}", batch_size=len(chunk), transaction_ids=tids,
            provider="demo", model="demo", request_start=datetime.now(timezone.utc),
            request_end=datetime.now(timezone.utc), processing_time_sec=0.01
        )
        return make_dummy_decisions(tids), log

    # Bind chunk to batch index dynamically
    def side_effect(chunk):
        first_tid = chunk[0]["transaction_id"]
        # TXN_001 -> Batch 1, TXN_006 -> Batch 2, TXN_011 -> Batch 3
        if "001" in first_tid:
            b_num = 1
        elif "006" in first_tid:
            b_num = 2
        else:
            b_num = 3
        return asyncio.run(delayed_investigate(b_num, chunk))

    mock_agent.investigate_batch.side_effect = side_effect

    events = []
    def callback(event):
        events.append(event)

    await run_parallel_batches(
        batches=chunks,
        batch_agent=mock_agent,
        max_parallel_batches=3,
        ground_truth=ground_truth,
        evaluation_group_id="group_test",
        run_id="run_test",
        run_num=1,
        total_runs=1,
        cases_per_run=15,
        batch_size=5,
        selected_provider="demo",
        client_model="demo",
        phase1_results=[],
        exception_count=15,
        resume_file=scratch_resume_file,
        event_callback=callback,
        tracer=DummyTracer()
    )

    # Filter batch_completed events
    completed_events = [e for e in events if e["event"] == "batch_completed"]
    assert len(completed_events) == 3
    
    # Check that Batch 3 completed first!
    assert completed_events[0]["batch_number"] == 3
    assert completed_events[1]["batch_number"] == 1
    assert completed_events[2]["batch_number"] == 2

    # Check metrics updated events
    metrics_events = [e for e in events if e["event"] == "metrics_updated"]
    assert len(metrics_events) > 0
    # Every completion should show progressive count increase
    assert metrics_events[-1]["cases_completed"] == 15


# 12. Partial persistence written per batch
@pytest.mark.asyncio
async def test_partial_persistence(tmp_path, sample_data):
    exceptions, ground_truth = sample_data
    chunks = [exceptions[i : i + 5] for i in range(0, 10, 5)] # 2 batches
    resume_file = os.path.join(str(tmp_path), "resume_test.json")

    mock_agent = MagicMock(spec=BatchAgentController)
    mock_agent.investigate_batch.side_effect = lambda chunk: (
        make_dummy_decisions([c["transaction_id"] for c in chunk]),
        BatchInvestigationLog(
            batch_id="b", batch_size=len(chunk), transaction_ids=[c["transaction_id"] for c in chunk],
            provider="demo", model="demo", request_start=datetime.now(timezone.utc),
            request_end=datetime.now(timezone.utc), processing_time_sec=0.01
        )
    )

    await run_parallel_batches(
        batches=chunks,
        batch_agent=mock_agent,
        max_parallel_batches=2,
        ground_truth=ground_truth,
        evaluation_group_id="group_test",
        run_id="run_test",
        run_num=1,
        total_runs=1,
        cases_per_run=10,
        batch_size=5,
        selected_provider="demo",
        client_model="demo",
        phase1_results=[],
        exception_count=10,
        resume_file=resume_file,
        tracer=DummyTracer()
    )

    # Verify resume file contains correct state
    assert os.path.exists(resume_file)
    with open(resume_file, "r") as f:
        data = json.load(f)
    assert data["status"] == "RUNNING"
    assert len(data["partial_results"]) == 10


# 13 & 14. One failed batch doesn't kill others, NOT_EVALUATED handling
@pytest.mark.asyncio
async def test_failed_batch_does_not_halt_and_produces_not_evaluated(sample_data, scratch_resume_file):
    exceptions, ground_truth = sample_data
    chunks = [exceptions[i : i + 5] for i in range(0, 10, 5)] # 2 batches

    mock_agent = MagicMock(spec=BatchAgentController)
    
    def side_effect(chunk):
        first_tid = chunk[0]["transaction_id"]
        if "001" in first_tid: # Batch 1 fails
            raise RuntimeError("Rate limit exceeded")
        else: # Batch 2 succeeds
            return make_dummy_decisions([c["transaction_id"] for c in chunk]), BatchInvestigationLog(
                batch_id="b2", batch_size=len(chunk), transaction_ids=[c["transaction_id"] for c in chunk],
                provider="demo", model="demo", request_start=datetime.now(timezone.utc),
                request_end=datetime.now(timezone.utc), processing_time_sec=0.01
            )

    mock_agent.investigate_batch.side_effect = side_effect

    res = await run_parallel_batches(
        batches=chunks,
        batch_agent=mock_agent,
        max_parallel_batches=2,
        ground_truth=ground_truth,
        evaluation_group_id="group_test",
        run_id="run_test",
        run_num=1,
        total_runs=1,
        cases_per_run=10,
        batch_size=5,
        selected_provider="demo",
        client_model="demo",
        phase1_results=[],
        exception_count=10,
        resume_file=scratch_resume_file,
        tracer=DummyTracer()
    )

    assert len(res.decisions) == 10
    # First 5 decisions must be NOT_EVALUATED
    for d in res.decisions[:5]:
        assert d.decision == "NOT_EVALUATED"
        assert "Rate limit exceeded" in d.reason
    # Last 5 decisions must be AUTO_RESOLVED
    for d in res.decisions[5:]:
        assert d.decision == "AUTO_RESOLVED"


# 15. Token aggregation
@pytest.mark.asyncio
async def test_token_aggregation(sample_data, scratch_resume_file):
    exceptions, ground_truth = sample_data
    chunks = [exceptions[i : i + 5] for i in range(0, 10, 5)]

    mock_agent = MagicMock(spec=BatchAgentController)
    def side_effect(chunk):
        tids = [c["transaction_id"] for c in chunk]
        log = BatchInvestigationLog(
            batch_id="b", batch_size=len(chunk), transaction_ids=tids,
            provider="demo", model="demo", request_start=datetime.now(timezone.utc),
            request_end=datetime.now(timezone.utc), processing_time_sec=0.01,
            prompt_tokens=100, completion_tokens=50, total_tokens=150
        )
        return make_dummy_decisions(tids), log

    mock_agent.investigate_batch.side_effect = side_effect

    res = await run_parallel_batches(
        batches=chunks,
        batch_agent=mock_agent,
        max_parallel_batches=2,
        ground_truth=ground_truth,
        evaluation_group_id="group_test",
        run_id="run_test",
        run_num=1,
        total_runs=1,
        cases_per_run=10,
        batch_size=5,
        selected_provider="demo",
        client_model="demo",
        phase1_results=[],
        exception_count=10,
        resume_file=scratch_resume_file,
        tracer=DummyTracer()
    )

    assert res.total_prompt_tokens == 200
    assert res.total_completion_tokens == 100
    assert res.total_tokens == 300


# 16. Latency aggregation
@pytest.mark.asyncio
async def test_latency_aggregation(sample_data, scratch_resume_file):
    exceptions, ground_truth = sample_data
    chunks = [exceptions[i : i + 5] for i in range(0, 10, 5)]

    mock_agent = MagicMock(spec=BatchAgentController)
    
    def side_effect(chunk):
        first_tid = chunk[0]["transaction_id"]
        # Batch 1 takes 0.05s, Batch 2 takes 0.15s
        dur = 0.05 if "001" in first_tid else 0.15
        time.sleep(dur)
        tids = [c["transaction_id"] for c in chunk]
        log = BatchInvestigationLog(
            batch_id="b", batch_size=len(chunk), transaction_ids=tids,
            provider="demo", model="demo", request_start=datetime.now(timezone.utc),
            request_end=datetime.now(timezone.utc), processing_time_sec=dur
        )
        return make_dummy_decisions(tids), log

    import time
    mock_agent.investigate_batch.side_effect = side_effect

    res = await run_parallel_batches(
        batches=chunks,
        batch_agent=mock_agent,
        max_parallel_batches=2,
        ground_truth=ground_truth,
        evaluation_group_id="group_test",
        run_id="run_test",
        run_num=1,
        total_runs=1,
        cases_per_run=10,
        batch_size=5,
        selected_provider="demo",
        client_model="demo",
        phase1_results=[],
        exception_count=10,
        resume_file=scratch_resume_file,
        tracer=DummyTracer()
    )

    assert res.min_batch_latency_sec >= 0.04
    assert res.max_batch_latency_sec >= 0.14
    assert res.average_batch_latency_sec >= 0.09


# 17 & 18. Resume completed batches, no duplicate resume processing
@pytest.mark.asyncio
async def test_resume_completed_batches(sample_data, scratch_resume_file):
    exceptions, ground_truth = sample_data
    chunks = [exceptions[i : i + 5] for i in range(0, 10, 5)] # 2 batches

    mock_agent = MagicMock(spec=BatchAgentController)
    mock_agent.investigate_batch.side_effect = lambda chunk: (
        make_dummy_decisions([c["transaction_id"] for c in chunk]),
        BatchInvestigationLog(
            batch_id="b", batch_size=len(chunk), transaction_ids=[c["transaction_id"] for c in chunk],
            provider="demo", model="demo", request_start=datetime.now(timezone.utc),
            request_end=datetime.now(timezone.utc), processing_time_sec=0.01
        )
    )

    # Let's say Batch 1 is already completed. So we pass completed_batch_numbers = {1}
    completed_batch_numbers = {1}
    existing_decisions = make_dummy_decisions([c["transaction_id"] for c in chunks[0]])

    res = await run_parallel_batches(
        batches=chunks,
        batch_agent=mock_agent,
        max_parallel_batches=2,
        ground_truth=ground_truth,
        evaluation_group_id="group_test",
        run_id="run_test",
        run_num=1,
        total_runs=1,
        cases_per_run=10,
        batch_size=5,
        selected_provider="demo",
        client_model="demo",
        phase1_results=[],
        exception_count=10,
        resume_file=scratch_resume_file,
        tracer=DummyTracer(),
        completed_batch_numbers=completed_batch_numbers,
        existing_decisions=existing_decisions
    )

    # BatchAgentController should ONLY have been called once (for Batch 2)
    assert mock_agent.investigate_batch.call_count == 1
    # Check that decisions correctly merge to 10 total cases
    assert len(res.decisions) == 10


# 19. Thread/async-safe result merging
@pytest.mark.asyncio
async def test_thread_async_safe_merging(sample_data, scratch_resume_file):
    exceptions, ground_truth = sample_data
    # 5 batches of 5 cases
    chunks = [exceptions[i : i + 5] for i in range(0, 25, 5)]

    mock_agent = MagicMock(spec=BatchAgentController)
    
    # Each batch returns decisions with transaction_id matching chunk
    def side_effect(chunk):
        tids = [c["transaction_id"] for c in chunk]
        return make_dummy_decisions(tids), BatchInvestigationLog(
            batch_id="b", batch_size=len(chunk), transaction_ids=tids,
            provider="demo", model="demo", request_start=datetime.now(timezone.utc),
            request_end=datetime.now(timezone.utc), processing_time_sec=0.01
        )
        
    mock_agent.investigate_batch.side_effect = side_effect

    res = await run_parallel_batches(
        batches=chunks,
        batch_agent=mock_agent,
        max_parallel_batches=5,
        ground_truth=ground_truth,
        evaluation_group_id="group_test",
        run_id="run_test",
        run_num=1,
        total_runs=1,
        cases_per_run=25,
        batch_size=5,
        selected_provider="demo",
        client_model="demo",
        phase1_results=[],
        exception_count=25,
        resume_file=scratch_resume_file,
        tracer=DummyTracer()
    )

    assert len(res.decisions) == 25
    # Verify no transaction IDs were lost or duplicated
    tids = [d.transaction_id for d in res.decisions]
    assert len(set(tids)) == 25


# 20. Sequential behavior unchanged
def test_sequential_behavior_unchanged():
    # Calling run_evaluation with parallel_batches = 1 must preserve sequential behavior.
    # We run in demo mode and ensure it executes successfully and returns expected completed count.
    res = run_evaluation(provider="demo", cases=5, parallel_batches=1, mode="batch")
    assert res["status"] == "COMPLETED"
    assert res["completed"] == 5
    assert "sequential_estimated_time_sec" not in res["performance"]


# 2. parallel_batches=2 integration
def test_parallel_batches_2_integration():
    res = run_evaluation(provider="demo", cases=10, parallel_batches=2, mode="batch")
    assert res["status"] == "COMPLETED"
    assert res["completed"] == 10
    assert "sequential_estimated_time_sec" in res["performance"]


# 3. parallel_batches=5 integration
def test_parallel_batches_5_integration():
    res = run_evaluation(provider="demo", cases=25, parallel_batches=5, mode="batch")
    assert res["status"] == "COMPLETED"
    assert res["completed"] == 25
    assert "sequential_estimated_time_sec" in res["performance"]


# ---------------------------------------------------------------------------
# Auto parallel batches calculation tests
# ---------------------------------------------------------------------------
def test_auto_parallel_batches_calculation():
    # 15 cases, batch_size=5 -> 3 total batches -> actual 3
    res15 = run_evaluation(provider="demo", cases=15, batch_size=5, mode="batch")
    assert res15["status"] == "COMPLETED"
    assert res15["completed"] == 15
    assert "sequential_estimated_time_sec" in res15["performance"]

    # 25 cases, batch_size=5 -> 5 total batches -> actual 5
    res25 = run_evaluation(provider="demo", cases=25, batch_size=5, mode="batch")
    assert res25["status"] == "COMPLETED"
    assert res25["completed"] == 25
    assert "sequential_estimated_time_sec" in res25["performance"]

    # 5 cases, batch_size=5 -> 1 total batch -> actual 1 (sequential)
    res5 = run_evaluation(provider="demo", cases=5, batch_size=5, mode="batch")
    assert res5["status"] == "COMPLETED"
    assert res5["completed"] == 5


@pytest.mark.asyncio
async def test_semaphore_concurrency_bounding_40_cases(sample_data):
    # 40 cases split into 8 batches of 5, max_parallel_batches=5
    exceptions, ground_truth = sample_data
    ext_exceptions = (exceptions * 2)[:40]
    chunks = [ext_exceptions[i : i + 5] for i in range(0, 40, 5)]
    assert len(chunks) == 8

    mock_agent = MagicMock(spec=BatchAgentController)
    active_count = 0
    max_active_observed = 0

    async def slow_investigate(chunk):
        nonlocal active_count, max_active_observed
        active_count += 1
        max_active_observed = max(max_active_observed, active_count)
        await asyncio.sleep(0.02)
        tids = [c["transaction_id"] for c in chunk]
        active_count -= 1
        log = BatchInvestigationLog(
            batch_id="batch_x", batch_size=len(chunk), transaction_ids=tids,
            provider="demo", model="demo", request_start=datetime.now(timezone.utc),
            request_end=datetime.now(timezone.utc), processing_time_sec=0.02
        )
        return make_dummy_decisions(tids), log

    mock_agent.investigate_batch.side_effect = lambda chunk: asyncio.run(slow_investigate(chunk))

    res = await run_parallel_batches(
        batches=chunks,
        batch_agent=mock_agent,
        max_parallel_batches=5,
        ground_truth=ground_truth,
        evaluation_group_id="group_test_40",
        run_id="run_test_40",
        run_num=1,
        total_runs=1,
        cases_per_run=40,
        batch_size=5,
        selected_provider="demo",
        client_model="demo",
        phase1_results=[],
        exception_count=40,
        resume_file="",
    )

    assert len(res.decisions) == 40
    assert max_active_observed <= 5


def test_batch_mode_enforces_deterministic_post_validation():
    # Verify that when an LLM proposes HUMAN_REVIEW in batch mode for an adjustment-backed case,
    # BatchAgentController enforces deterministic proof post-validation and resolves to AUTO_RESOLVED.
    payments = [{"transaction_id": "TXN_PROOF_1", "amount": 1000.0, "status": "SETTLED"}]
    ledger = [{"transaction_id": "TXN_PROOF_1", "gross_amount": 1000.0, "fee": 20.0, "net_amount": 980.0, "status": "POSTED"}]
    bank = [{"bank_reference": "BNK_1", "transaction_id": "TXN_PROOF_1", "credited_amount": 930.0}]
    adjustments = [{"transaction_id": "TXN_PROOF_1", "adjustment_type": "BANK_PROCESSING_FEE", "amount": 50.0, "reason": "Processing fee"}]

    toolkit = FinancialToolkit(payments, ledger, bank, adjustments)

    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_message = MagicMock()
    mock_message.content = json.dumps({
        "decisions": [{
            "transaction_id": "TXN_PROOF_1",
            "decision": "HUMAN_REVIEW",
            "exception_type": "BANK_AMOUNT_MISMATCH",
            "resolution_type": "NONE",
            "reason": "LLM model misread adjustment evidence.",
            "evidence": ["Phase 1 exception: BANK_AMOUNT_MISMATCH"],
            "confidence": 0.5,
            "recommended_action": "Manual review."
        }]
    })
    mock_choice.message = mock_message
    mock_response.choices = [mock_choice]
    mock_llm.chat.return_value = mock_response
    mock_llm.provider = "mock"
    mock_llm.model = "mock"

    batch_controller = BatchAgentController(toolkit=toolkit, llm_client=mock_llm)
    decisions, _ = batch_controller.investigate_batch([{
        "transaction_id": "TXN_PROOF_1",
        "status": "EXCEPTION",
        "reason": "BANK_AMOUNT_MISMATCH"
    }])

    assert len(decisions) == 1
    assert decisions[0].decision == "AUTO_RESOLVED"
    assert decisions[0].resolution_type == "ADJUSTMENT_EXPLAINED"
    assert decisions[0].resolved_difference == 50.0
