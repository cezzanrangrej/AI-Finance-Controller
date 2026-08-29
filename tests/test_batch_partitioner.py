"""
Comprehensive unit & integration tests for balanced batch partitioning in AI Finance Controller.
"""

from unittest.mock import MagicMock
import pytest
from src.agent.batch_partitioner import (
    compare_partition_strategies,
    compute_partition_metrics,
    partition_exceptions_balanced,
)
from src.run_llm_eval import run_evaluation


# ---------------------------------------------------------------------------
# Test Helpers
# ---------------------------------------------------------------------------
def make_exception(tid: str, exc_type: str) -> dict:
    return {
        "transaction_id": tid,
        "status": "EXCEPTION",
        "reason": exc_type,
        "exception_type": exc_type,
    }


# ---------------------------------------------------------------------------
# 1. 11 cases distributed across 3 batches
# ---------------------------------------------------------------------------
def test_11_cases_across_3_batches():
    cases = (
        [make_exception(f"TXN_LEDGER_{i}", "MISSING_LEDGER_RECORD") for i in range(2)]
        + [make_exception(f"TXN_BANK_{i}", "MISSING_BANK_RECORD") for i in range(2)]
        + [make_exception(f"TXN_MISMATCH_{i}", "BANK_AMOUNT_MISMATCH") for i in range(5)]
        + [make_exception(f"TXN_DUP_{i}", "DUPLICATE_BANK_RECORD") for i in range(2)]
    )
    batches = partition_exceptions_balanced(cases, batch_size=5)

    assert len(batches) == 3
    assert sum(len(b) for b in batches) == 11

    # Check max concentration of BANK_AMOUNT_MISMATCH
    bank_counts = [sum(1 for c in b if c["reason"] == "BANK_AMOUNT_MISMATCH") for b in batches]
    assert max(bank_counts) <= 2  # 5 BANK_AMOUNT_MISMATCH distributed across 3 batches: 2, 2, 1


# ---------------------------------------------------------------------------
# 2. 13 cases distributed across 3 batches
# ---------------------------------------------------------------------------
def test_13_cases_across_3_batches():
    cases = (
        [make_exception(f"TXN_MISMATCH_{i}", "BANK_AMOUNT_MISMATCH") for i in range(7)]
        + [make_exception(f"TXN_LEDGER_{i}", "MISSING_LEDGER_RECORD") for i in range(3)]
        + [make_exception(f"TXN_BANK_{i}", "MISSING_BANK_RECORD") for i in range(3)]
    )
    batches = partition_exceptions_balanced(cases, batch_size=5)

    assert len(batches) == 3
    assert sum(len(b) for b in batches) == 13
    assert all(len(b) <= 5 for b in batches)


# ---------------------------------------------------------------------------
# 3. 15 cases distributed across 3 batches
# ---------------------------------------------------------------------------
def test_15_cases_across_3_batches():
    cases = (
        [make_exception(f"TXN_MISMATCH_{i}", "BANK_AMOUNT_MISMATCH") for i in range(10)]
        + [make_exception(f"TXN_LEDGER_{i}", "MISSING_LEDGER_RECORD") for i in range(2)]
        + [make_exception(f"TXN_BANK_{i}", "MISSING_BANK_RECORD") for i in range(2)]
        + [make_exception(f"TXN_DUP_{i}", "DUPLICATE_BANK_RECORD") for i in range(1)]
    )
    batches = partition_exceptions_balanced(cases, batch_size=5)

    assert len(batches) == 3
    assert sum(len(b) for b in batches) == 15
    assert all(len(b) == 5 for b in batches)


# ---------------------------------------------------------------------------
# 4. Dominant exception type distributed across all possible batches
# ---------------------------------------------------------------------------
def test_dominant_exception_type_distributed():
    cases = (
        [make_exception(f"TXN_MISMATCH_{i}", "BANK_AMOUNT_MISMATCH") for i in range(8)]
        + [make_exception(f"TXN_LEDGER_{i}", "MISSING_LEDGER_RECORD") for i in range(2)]
    )
    batches = partition_exceptions_balanced(cases, batch_size=5)

    assert len(batches) == 2
    bank_counts = [sum(1 for c in b if c["reason"] == "BANK_AMOUNT_MISMATCH") for b in batches]
    # 8 BANK_AMOUNT_MISMATCH in 2 batches of size 5 -> 4 and 4
    assert bank_counts == [4, 4]


# ---------------------------------------------------------------------------
# 5. Small exception types distributed without duplication
# ---------------------------------------------------------------------------
def test_small_exception_types_no_duplication():
    cases = [
        make_exception("TXN_1", "TYPE_A"),
        make_exception("TXN_2", "TYPE_B"),
        make_exception("TXN_3", "TYPE_C"),
        make_exception("TXN_4", "TYPE_D"),
        make_exception("TXN_5", "TYPE_E"),
        make_exception("TXN_6", "TYPE_F"),
    ]
    batches = partition_exceptions_balanced(cases, batch_size=2)

    assert len(batches) == 3
    tids = [c["transaction_id"] for b in batches for c in b]
    assert len(tids) == 6
    assert len(set(tids)) == 6


# ---------------------------------------------------------------------------
# 6 & 7 & 8 & 9. Uniqueness, non-omission, total count, batch size <= batch_size
# ---------------------------------------------------------------------------
def test_partition_invariants():
    cases = (
        [make_exception(f"TXN_MISMATCH_{i}", "BANK_AMOUNT_MISMATCH") for i in range(12)]
        + [make_exception(f"TXN_LEDGER_{i}", "MISSING_LEDGER_RECORD") for i in range(5)]
        + [make_exception(f"TXN_BANK_{i}", "MISSING_BANK_RECORD") for i in range(3)]
    )
    batch_size = 5
    batches = partition_exceptions_balanced(cases, batch_size=batch_size)

    all_tids = [c["transaction_id"] for b in batches for c in b]
    input_tids = [c["transaction_id"] for c in cases]

    # No duplicate TIDs
    assert len(all_tids) == len(set(all_tids))
    # Non-omission
    assert set(all_tids) == set(input_tids)
    # Total count preserved
    assert len(all_tids) == len(cases)
    # Every batch size <= batch_size
    assert all(len(b) <= batch_size for b in batches)


# ---------------------------------------------------------------------------
# 10. Deterministic repeated partitioning produces identical result
# ---------------------------------------------------------------------------
def test_deterministic_repeated_partitioning():
    cases = (
        [make_exception(f"TXN_MISMATCH_{i}", "BANK_AMOUNT_MISMATCH") for i in range(9)]
        + [make_exception(f"TXN_LEDGER_{i}", "MISSING_LEDGER_RECORD") for i in range(4)]
    )
    b1 = partition_exceptions_balanced(cases, batch_size=5)
    b2 = partition_exceptions_balanced(cases, batch_size=5)

    assert [[c["transaction_id"] for c in chunk] for chunk in b1] == [
        [c["transaction_id"] for c in chunk] for chunk in b2
    ]


# ---------------------------------------------------------------------------
# 11. Type counts remain exact
# ---------------------------------------------------------------------------
def test_type_counts_remain_exact():
    cases = (
        [make_exception(f"TXN_MISMATCH_{i}", "BANK_AMOUNT_MISMATCH") for i in range(5)]
        + [make_exception(f"TXN_LEDGER_{i}", "MISSING_LEDGER_RECORD") for i in range(3)]
    )
    batches = partition_exceptions_balanced(cases, batch_size=4)

    total_mismatch = sum(
        sum(1 for c in b if c["reason"] == "BANK_AMOUNT_MISMATCH") for b in batches
    )
    total_ledger = sum(
        sum(1 for c in b if c["reason"] == "MISSING_LEDGER_RECORD") for b in batches
    )

    assert total_mismatch == 5
    assert total_ledger == 3


# ---------------------------------------------------------------------------
# 12. Balancing works when one type dominates
# ---------------------------------------------------------------------------
def test_one_type_dominates():
    cases = (
        [make_exception(f"TXN_DOMINANT_{i}", "DOMINANT_TYPE") for i in range(12)]
        + [make_exception("TXN_RARE_1", "RARE_TYPE")]
    )
    batches = partition_exceptions_balanced(cases, batch_size=5)

    assert len(batches) == 3
    dom_counts = [sum(1 for c in b if c["reason"] == "DOMINANT_TYPE") for b in batches]
    # 12 DOMINANT_TYPE cases across 3 batches -> 4, 4, 4
    assert dom_counts == [4, 4, 4]


# ---------------------------------------------------------------------------
# 13. Balancing works when all types are equally represented
# ---------------------------------------------------------------------------
def test_all_types_equally_represented():
    cases = (
        [make_exception(f"TXN_A_{i}", "TYPE_A") for i in range(3)]
        + [make_exception(f"TXN_B_{i}", "TYPE_B") for i in range(3)]
        + [make_exception(f"TXN_C_{i}", "TYPE_C") for i in range(3)]
    )
    batches = partition_exceptions_balanced(cases, batch_size=3)

    assert len(batches) == 3
    for b in batches:
        # Each batch of 3 receives 1 of each type!
        types_in_b = {c["reason"] for c in b}
        assert len(types_in_b) == 3


# ---------------------------------------------------------------------------
# 14. Balancing works with one exception type only
# ---------------------------------------------------------------------------
def test_one_exception_type_only():
    cases = [make_exception(f"TXN_SINGLE_{i}", "SINGLE_TYPE") for i in range(10)]
    batches = partition_exceptions_balanced(cases, batch_size=5)

    assert len(batches) == 2
    assert len(batches[0]) == 5
    assert len(batches[1]) == 5


# ---------------------------------------------------------------------------
# 15. Balancing works with fewer cases than batch_size
# ---------------------------------------------------------------------------
def test_fewer_cases_than_batch_size():
    cases = [
        make_exception("TXN_1", "TYPE_A"),
        make_exception("TXN_2", "TYPE_B"),
    ]
    batches = partition_exceptions_balanced(cases, batch_size=5)

    assert len(batches) == 1
    assert len(batches[0]) == 2


# ---------------------------------------------------------------------------
# 16. Final smaller batches allowed
# ---------------------------------------------------------------------------
def test_final_smaller_batches_allowed():
    cases = [make_exception(f"TXN_{i}", "TYPE_A") for i in range(13)]
    batches = partition_exceptions_balanced(cases, batch_size=5)

    assert len(batches) == 3
    sizes = [len(b) for b in batches]
    assert sum(sizes) == 13
    assert max(sizes) <= 5


# ---------------------------------------------------------------------------
# 17. Automatic concurrency unchanged
# ---------------------------------------------------------------------------
def test_automatic_concurrency_unchanged():
    res = run_evaluation(provider="demo", cases=15, batch_size=5, mode="batch")
    assert res["status"] == "COMPLETED"
    assert res["completed"] == 15


# ---------------------------------------------------------------------------
# 18. Diagnostic metrics & comparison helper
# ---------------------------------------------------------------------------
def test_partition_metrics_and_comparison():
    cases = (
        [make_exception(f"TXN_MISMATCH_{i}", "BANK_AMOUNT_MISMATCH") for i in range(6)]
        + [make_exception(f"TXN_LEDGER_{i}", "MISSING_LEDGER_RECORD") for i in range(2)]
    )
    comp = compare_partition_strategies(cases, batch_size=4)

    assert "sequential" in comp
    assert "balanced" in comp
    assert comp["balanced"]["metrics"]["total_cases"] == 8
    assert comp["balanced"]["metrics"]["total_batches"] == 2
