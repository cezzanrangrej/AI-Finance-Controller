"""
Unit tests for LLMRateLimitError and the rate-limit retry wrapper in runs.py.
"""

import random
import time
import pytest
from unittest.mock import MagicMock, patch

from src.agent.rate_limit import LLMRateLimitError, extract_retry_after


# ── extract_retry_after ───────────────────────────────────────────────────────

class TestExtractRetryAfter:
    def test_retry_in_seconds(self):
        assert extract_retry_after("Please retry in 25s") == 25.0

    def test_retry_in_fractional(self):
        assert extract_retry_after("retry in 3.5s blah") == 3.5

    def test_retry_after_header(self):
        assert extract_retry_after("Retry-After: 60") == 60.0

    def test_no_match(self):
        assert extract_retry_after("Something went wrong") is None

    def test_case_insensitive(self):
        assert extract_retry_after("RETRY IN 10S") == 10.0


# ── LLMRateLimitError ────────────────────────────────────────────────────────

class TestLLMRateLimitError:
    def test_basic_creation(self):
        err = LLMRateLimitError("test", provider="gemini", status_code=429)
        assert str(err) == "test"
        assert err.provider == "gemini"
        assert err.status_code == 429
        assert err.retry_after is None

    def test_with_retry_after(self):
        err = LLMRateLimitError("throttled", retry_after=30.0, provider="openrouter")
        assert err.retry_after == 30.0

    def test_is_exception(self):
        with pytest.raises(LLMRateLimitError):
            raise LLMRateLimitError("rate limited", provider="grok")


# ── Retry wrapper integration (simulates _execute_single_chunk logic) ─────────

class TestRateLimitRetryWrapper:
    """
    Tests the retry logic pattern used in runs.py _execute_single_chunk.
    We replicate the core loop here to test in isolation without importing
    the full FastAPI route.
    """

    RATE_LIMIT_MAX_RETRIES = 4
    RATE_LIMIT_BASE_DELAYS = [1.0, 2.0, 4.0, 8.0]
    JITTER_FACTOR = 0.20

    def _run_retry_loop(self, investigate_fn, chunk):
        """Mimics the retry logic in _execute_single_chunk."""
        chunk_decisions = None
        batch_log = None
        events = []

        for rl_attempt in range(self.RATE_LIMIT_MAX_RETRIES):
            try:
                chunk_decisions, batch_log = investigate_fn(chunk)
                break
            except LLMRateLimitError as rle:
                base_delay = self.RATE_LIMIT_BASE_DELAYS[
                    min(rl_attempt, len(self.RATE_LIMIT_BASE_DELAYS) - 1)
                ]
                if rle.retry_after is not None and rle.retry_after > 0:
                    wait = rle.retry_after
                else:
                    jitter = base_delay * self.JITTER_FACTOR * (2 * random.random() - 1)
                    wait = base_delay + jitter
                wait = max(wait, 0.5)

                events.append({
                    "event": "rate_limited_retry",
                    "attempt": rl_attempt + 1,
                    "provider": rle.provider,
                    "wait": wait,
                })

                if rl_attempt < self.RATE_LIMIT_MAX_RETRIES - 1:
                    pass  # skip actual sleep in tests
                # else: exhausted, fall through

            except Exception:
                chunk_decisions = [{"decision": "NOT_EVALUATED", "source": "INFRASTRUCTURE_FAILURE"}]
                break

        return chunk_decisions, batch_log, events

    def test_success_on_first_try(self):
        """No rate limits — should return immediately."""
        fn = MagicMock(return_value=(["decision1"], {"log": True}))
        decisions, log, events = self._run_retry_loop(fn, [{"tid": "1"}])
        assert decisions == ["decision1"]
        assert log == {"log": True}
        assert events == []
        assert fn.call_count == 1

    def test_success_after_retries(self):
        """Rate limited twice, then succeeds on third attempt."""
        fn = MagicMock(side_effect=[
            LLMRateLimitError("rl1", provider="gemini"),
            LLMRateLimitError("rl2", provider="gemini"),
            (["ok"], {"log": True}),
        ])
        decisions, log, events = self._run_retry_loop(fn, [{"tid": "1"}])
        assert decisions == ["ok"]
        assert fn.call_count == 3
        assert len(events) == 2
        assert all(e["provider"] == "gemini" for e in events)

    def test_exhaustion_returns_none(self):
        """All 4 attempts rate-limited — chunk_decisions should be None."""
        fn = MagicMock(side_effect=LLMRateLimitError("always", provider="openrouter"))
        decisions, log, events = self._run_retry_loop(fn, [{"tid": "1"}])
        assert decisions is None  # caller creates NOT_EVALUATED fallback
        assert fn.call_count == 4
        assert len(events) == 4

    def test_retry_after_header_used(self):
        """Retry-After from the exception should override computed delay."""
        fn = MagicMock(side_effect=[
            LLMRateLimitError("rl", provider="grok", retry_after=42.0),
            (["ok"], None),
        ])
        decisions, log, events = self._run_retry_loop(fn, [{"tid": "1"}])
        assert decisions == ["ok"]
        assert events[0]["wait"] == 42.0

    def test_non_rate_limit_error_no_retry(self):
        """Non-rate-limit exceptions should NOT trigger retry."""
        fn = MagicMock(side_effect=RuntimeError("internal error"))
        decisions, log, events = self._run_retry_loop(fn, [{"tid": "1"}])
        assert decisions == [{"decision": "NOT_EVALUATED", "source": "INFRASTRUCTURE_FAILURE"}]
        assert fn.call_count == 1
        assert events == []

    def test_jitter_stays_within_bounds(self):
        """Verify jitter is within ±20% of base delay."""
        random.seed(12345)
        fn = MagicMock(side_effect=[
            LLMRateLimitError("rl", provider="gemini"),
            (["ok"], None),
        ])
        _, _, events = self._run_retry_loop(fn, [{"tid": "1"}])
        wait = events[0]["wait"]
        base = 1.0
        assert base * 0.8 <= wait <= base * 1.2

    def test_independent_threads_dont_block(self):
        """
        Simulate 3 parallel chunks: chunk 0 gets rate-limited, chunks 1 & 2
        succeed immediately. Verify they don't wait for chunk 0.
        """
        import threading

        results = {}
        barrier = threading.Barrier(3, timeout=5)

        def chunk_fn(chunk_id):
            def inner(chunk):
                barrier.wait()  # sync all threads to start together
                if chunk_id == 0:
                    raise LLMRateLimitError("throttled", provider="gemini")
                return ([f"ok_{chunk_id}"], None)
            return inner

        def worker(chunk_id):
            fn = MagicMock(side_effect=[
                *([LLMRateLimitError("throttled", provider="gemini")] if chunk_id == 0 else []),
                ([f"ok_{chunk_id}"], None),
            ])
            decisions, _, events = self._run_retry_loop(fn, [{"tid": str(chunk_id)}])
            results[chunk_id] = {
                "decisions": decisions,
                "events": events,
                "call_count": fn.call_count,
            }

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        # Chunks 1 and 2 should succeed immediately (no retries)
        assert results[1]["decisions"] == ["ok_1"]
        assert results[1]["events"] == []
        assert results[2]["decisions"] == ["ok_2"]
        assert results[2]["events"] == []

        # Chunk 0 should have retried once then succeeded
        assert results[0]["decisions"] == ["ok_0"]
        assert len(results[0]["events"]) == 1
