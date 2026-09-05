"""
Pre-batch deterministic pre-filter for Phase 2.

Phase 1 raises an exception from double-entry rules alone, so some of what it
raises is already fully explained by a documented adjustment record -- and the
proof is pure ``Decimal`` arithmetic (see
:func:`src.agent.controller.has_sufficient_resolution_evidence`).

Those cases used to be batched, sent to the Investigator and the Verifier, and
then have the LLM's answer overridden by that same arithmetic afterwards. The
override was correct but the tokens were wasted, the latency was real, and the
audit trail credited an agent for a resolution no agent made.

This module runs the proof *before* batch partitioning, so:

* mathematically proven exceptions resolve in Python memory, at zero token cost;
* only genuinely ambiguous exceptions are partitioned and sent to the agents;
* the agent controllers need no post-hoc override, because every case that
  reaches them is already known to be unprovable by arithmetic.

Both entry points (the API pipeline in ``src/api/routes/runs.py`` and the CLI in
``scripts/run_dataset.py``) call :func:`prefilter_proven_exceptions` and the two
printers here, so the terminal output and the resolution semantics cannot drift
apart between them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from src.agent.batch_controller import prefetch_case_evidence
from src.agent.controller import (
    EvidenceState,
    build_proven_adjustment_resolution,
    has_sufficient_resolution_evidence,
)
from src.agent.schemas import AgentDecision, BatchInvestigationCase
from src.agent.tools import FinancialToolkit

#: Recorded on decisions produced here. No agent ran, so neither agent mode
#: would be an honest label.
PRE_FILTER_AGENT_MODE = "DETERMINISTIC_PRE_FILTER"

#: Recorded on decisions produced here, matching the value the removed post-LLM
#: override used, so historical runs and new runs read the same way.
PRE_FILTER_RESOLUTION_SOURCE = "DETERMINISTIC_PROOF"


@dataclass
class PreFilterResult:
    """Outcome of the deterministic pass over Phase 1 exceptions."""

    #: AUTO_RESOLVED decisions backed by an arithmetic proof. These never
    #: reached an LLM, so their call counters are zero.
    proven_decisions: List[AgentDecision] = field(default_factory=list)

    #: Exception records arithmetic could not settle. Only these are partitioned
    #: into batches and sent to the agents.
    ambiguous_exceptions: List[Dict[str, Any]] = field(default_factory=list)

    #: transaction_id -> toolkit methods actually invoked while gathering the
    #: evidence for a proven case, so the audit trail reports real provenance.
    tool_provenance: Dict[str, List[str]] = field(default_factory=dict)

    @property
    def total(self) -> int:
        """Phase 1 exceptions considered."""
        return len(self.proven_decisions) + len(self.ambiguous_exceptions)

    @property
    def pre_resolved_count(self) -> int:
        """Exceptions closed by arithmetic, without any LLM call."""
        return len(self.proven_decisions)

    @property
    def remaining_count(self) -> int:
        """Exceptions forwarded to the AI multi-agent pipeline."""
        return len(self.ambiguous_exceptions)


def build_evidence_state(case: BatchInvestigationCase) -> EvidenceState:
    """
    Projects prefetched batch evidence onto the ``EvidenceState`` the
    deterministic proof reads.

    ``prefetch_case_evidence`` never calls ``verify_discrepancy``, so
    ``discrepancy_verification`` stays unset and the proof is decided by the
    arithmetic identities rather than by that tool's fast path. This mirrors
    exactly what the batch controller used to do post-LLM.
    """
    state = EvidenceState(case.transaction_id)
    state.payment = case.payment
    state.ledger = case.ledger
    state.bank_records = case.bank_records
    state.adjustments = case.adjustments
    state.duplicate_check = case.duplicate_check
    state.expected_settlement = case.expected_settlement
    state.adjusted_expected_settlement = case.adjusted_expected_settlement
    return state


def prefilter_proven_exceptions(
    exceptions: List[Dict[str, Any]],
    toolkit: FinancialToolkit,
) -> PreFilterResult:
    """
    Splits Phase 1 exceptions into those an arithmetic proof already resolves
    and those that genuinely need agent investigation.

    Original exception order is preserved within both output lists, so a run is
    reproducible.
    """
    result = PreFilterResult()
    if not exceptions:
        return result

    for exc in exceptions:
        txn_id = exc.get("transaction_id", "UNKNOWN")
        exc_type = exc.get("reason", "UNKNOWN")

        case = prefetch_case_evidence(exc, toolkit)
        is_proven, proof_data = has_sufficient_resolution_evidence(
            build_evidence_state(case), exc_type
        )

        if not (is_proven and proof_data):
            result.ambiguous_exceptions.append(exc)
            continue

        decision = build_proven_adjustment_resolution(
            txn_id=txn_id,
            exception_type=exc_type,
            evidence=[f"Phase 1 exception: {exc_type}"],
            resolution_data=proof_data,
        )
        # A Decimal proof decided this, not a model. Record that honestly:
        # ``build_proven_adjustment_resolution`` sets neither the mode nor the
        # source nor the call counters, so they are set here.
        decision.agent_mode = PRE_FILTER_AGENT_MODE
        decision.resolution_source = PRE_FILTER_RESOLUTION_SOURCE
        decision.investigator_calls = 0
        decision.verifier_calls = 0
        decision.model_interactions = 0

        result.proven_decisions.append(decision)
        result.tool_provenance[txn_id] = list(case.tools_invoked)

    return result


def print_pre_filter_header() -> None:
    """Announces the deterministic pass before it runs."""
    print("\n>>> [PRE-FILTER] Evaluating Deterministic Adjustment Proofs...", flush=True)


def print_pre_filter_summary(result: PreFilterResult) -> None:
    """Reports the split. Identical in the API terminal and the CLI by design."""
    print(
        f"    -> Pre-Resolved (Decimal Proof): {result.pre_resolved_count} case(s) "
        f"[0 LLM Tokens, Instant]",
        flush=True,
    )
    print(
        f"    -> Forwarded to AI Multi-Agent:  {result.remaining_count} case(s)\n",
        flush=True,
    )
