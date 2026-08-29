"""
Deterministic Balanced Batch Partitioner for AI Finance Controller.

Distributes exception records across parallel batches to achieve balanced
exception-type diversification without sacrificing batch-size bounds, transaction
uniqueness, or deterministic reproducibility.
"""

from collections import Counter
import math
from typing import Any, Dict, List, Tuple


def partition_exceptions_balanced(
    exceptions: List[Dict[str, Any]],
    batch_size: int = 5,
) -> List[List[Dict[str, Any]]]:
    """
    Partition selected exception records into balanced batches based on exception_type
    diversification.

    Args:
        exceptions: List of Phase 1 exception dicts selected for evaluation.
        batch_size: Maximum records per batch (1..10, default 5).

    Returns:
        List of batches, where each batch is a list of exception dicts.
    """
    if not exceptions:
        return []

    if batch_size < 1 or batch_size > 10:
        raise ValueError(f"batch_size must be between 1 and 10, got {batch_size}")

    total_cases = len(exceptions)
    total_batches = math.ceil(total_cases / batch_size)

    # 1. Group exceptions by exception_type, preserving input order within each group
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for exc in exceptions:
        etype = exc.get("reason") or exc.get("exception_type") or exc.get("initial_exception") or "UNKNOWN"
        grouped.setdefault(etype, []).append(exc)

    # 2. Sort exception types deterministically:
    # Priority: descending count (most dominant types first), then ascending type name
    sorted_types = sorted(
        grouped.keys(),
        key=lambda k: (-len(grouped[k]), str(k))
    )

    batches: List[List[Dict[str, Any]]] = [[] for _ in range(total_batches)]

    # Helper to get current count of a specific exception type in a batch
    def get_type_count(batch: List[Dict[str, Any]], target_type: str) -> int:
        return sum(
            1 for c in batch
            if (c.get("reason") or c.get("exception_type") or c.get("initial_exception") or "UNKNOWN") == target_type
        )

    # 3. Distribute each exception type across available batches
    for etype in sorted_types:
        cases_of_type = grouped[etype]
        for case in cases_of_type:
            # Find candidate batches with capacity < batch_size
            candidate_indices = [i for i in range(total_batches) if len(batches[i]) < batch_size]
            if not candidate_indices:
                candidate_indices = list(range(total_batches))

            # Select batch minimizing:
            # 1) count of this etype in batch
            # 2) total size of batch
            # 3) batch index (determinism tie-break)
            best_b_idx = min(
                candidate_indices,
                key=lambda b_idx: (
                    get_type_count(batches[b_idx], etype),
                    len(batches[b_idx]),
                    b_idx,
                )
            )

            batches[best_b_idx].append(case)

    # Remove any empty batches if total_cases was 0 (already handled)
    return [b for b in batches if b]


def compute_partition_metrics(batches: List[List[Dict[str, Any]]]) -> Dict[str, Any]:
    """
    Computes diagnostic balance quality metrics for a partition.
    """
    if not batches:
        return {
            "total_cases": 0,
            "total_batches": 0,
            "max_batch_size": 0,
            "batch_sizes": [],
            "exception_type_counts_per_batch": [],
            "max_type_concentration_per_batch": [],
            "overall_max_type_concentration": 0,
        }

    total_cases = sum(len(b) for b in batches)
    batch_sizes = [len(b) for b in batches]
    max_batch_size = max(batch_sizes) if batch_sizes else 0

    type_counts_per_batch = []
    max_conc_per_batch = []

    for b in batches:
        counts: Dict[str, int] = {}
        for c in b:
            etype = c.get("reason") or c.get("exception_type") or c.get("initial_exception") or "UNKNOWN"
            counts[etype] = counts.get(etype, 0) + 1
        type_counts_per_batch.append(counts)
        max_c = max(counts.values()) if counts else 0
        max_conc_per_batch.append(max_c)

    overall_max_conc = max(max_conc_per_batch) if max_conc_per_batch else 0

    return {
        "total_cases": total_cases,
        "total_batches": len(batches),
        "max_batch_size": max_batch_size,
        "batch_sizes": batch_sizes,
        "exception_type_counts_per_batch": type_counts_per_batch,
        "max_type_concentration_per_batch": max_conc_per_batch,
        "overall_max_type_concentration": overall_max_conc,
    }


def compare_partition_strategies(
    exceptions: List[Dict[str, Any]],
    batch_size: int = 5,
) -> Dict[str, Any]:
    """
    Deterministic comparison helper between sequential partitioning and balanced-type partitioning.
    """
    if not exceptions:
        return {}

    # Sequential partitioning
    seq_chunks = [exceptions[i : i + batch_size] for i in range(0, len(exceptions), batch_size)]
    seq_metrics = compute_partition_metrics(seq_chunks)

    # Balanced partitioning
    bal_chunks = partition_exceptions_balanced(exceptions, batch_size)
    bal_metrics = compute_partition_metrics(bal_chunks)

    return {
        "sequential": {
            "strategy": "sequential",
            "metrics": seq_metrics,
        },
        "balanced": {
            "strategy": "balanced_exception_type",
            "metrics": bal_metrics,
        },
    }
