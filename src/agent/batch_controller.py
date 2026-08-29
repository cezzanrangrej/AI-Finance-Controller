"""
Batch Investigation Controller for AI Finance Controller.

Evaluates 5–10 finance exceptions in a single structured LLM interaction using
deterministic evidence prefetching, strict JSON response validation, and automatic
per-case fallback to individual agent investigation if batch parsing fails.
"""

from datetime import datetime, timezone
import json
import re
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from src.agent.controller import (
    AgentController,
    EvidenceState,
    LLMClient,
    build_proven_adjustment_resolution,
    has_sufficient_resolution_evidence,
)
from src.agent.prompts import BATCH_SYSTEM_PROMPT, build_batch_investigation_prompt
from src.agent.schemas import (
    AgentDecision,
    BatchAgentResponse,
    BatchInvestigationCase,
    BatchInvestigationLog,
)
from src.agent.tools import FinancialToolkit


def prefetch_case_evidence(
    exception_record: Dict[str, Any],
    toolkit: FinancialToolkit,
) -> BatchInvestigationCase:
    """
    Deterministically gathers all relevant financial records and calculations
    for a single exception prior to batch LLM invocation.
    """
    txn_id = exception_record.get("transaction_id", "UNKNOWN")
    exc_type = exception_record.get("reason", "UNKNOWN")

    payment = toolkit.get_payment_record(txn_id)
    if "error" in payment:
        payment = None

    ledger = toolkit.get_ledger_record(txn_id)
    if "error" in ledger:
        ledger = None

    bank_info = toolkit.get_bank_records(txn_id)
    bank_records = bank_info.get("bank_records", []) if "error" not in bank_info else []

    adj_info = toolkit.get_adjustments(txn_id)
    adjustments = adj_info.get("adjustments", []) if "error" not in adj_info else []

    dup_info = toolkit.check_for_duplicates(txn_id)
    dup_check = dup_info if "error" not in dup_info else None

    exp_settle = None
    if ledger and ledger.get("gross_amount") is not None:
        exp_res = toolkit.calculate_expected_settlement(txn_id)
        if "error" not in exp_res:
            exp_settle = exp_res

    adj_settle = None
    if ledger and ledger.get("gross_amount") is not None and adjustments:
        adj_res = toolkit.calculate_adjusted_expected_settlement(txn_id)
        if "error" not in adj_res:
            adj_settle = adj_res

    return BatchInvestigationCase(
        transaction_id=txn_id,
        initial_exception=exc_type,
        payment=payment,
        ledger=ledger,
        bank_records=bank_records,
        adjustments=adjustments,
        duplicate_check=dup_check,
        expected_settlement=exp_settle,
        adjusted_expected_settlement=adj_settle,
    )


class BatchAgentController:
    """
    Orchestrates batch exception investigations with deterministic prefetching
    and resilient individual agent fallback.
    """

    def __init__(
        self,
        toolkit: FinancialToolkit,
        llm_client: LLMClient,
        tracer: Optional[Any] = None,
    ) -> None:
        self.toolkit = toolkit
        self.llm = llm_client
        from src.agent.trace import AgentTracer, default_tracer
        self.tracer = tracer or default_tracer
        self.fallback_agent = AgentController(toolkit=toolkit, llm_client=llm_client, tracer=self.tracer)


    def investigate_batch(
        self,
        batch_exceptions: List[Dict[str, Any]],
    ) -> Tuple[List[AgentDecision], BatchInvestigationLog]:
        """
        Investigates a single batch of exception records (typically 5–10 cases)
        in a single LLM call, falling back to individual agent investigation
        only for transactions that fail batch validation.
        """
        if not batch_exceptions:
            raise ValueError("batch_exceptions cannot be empty")

        batch_id = f"batch_{uuid.uuid4().hex[:8]}"
        expected_txn_ids = [e.get("transaction_id", "UNKNOWN") for e in batch_exceptions]
        cases_map = {e.get("transaction_id", "UNKNOWN"): e for e in batch_exceptions}

        # Step 1: Deterministic Evidence Prefetch for all cases in the batch
        prefetched_cases: List[BatchInvestigationCase] = [
            prefetch_case_evidence(exc, self.toolkit) for exc in batch_exceptions
        ]

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": BATCH_SYSTEM_PROMPT},
            {"role": "user", "content": build_batch_investigation_prompt(prefetched_cases)},
        ]

        t_start = datetime.now(timezone.utc)
        perf_start = time.perf_counter()

        raw_content = ""
        batch_decisions_map: Dict[str, AgentDecision] = {}
        fallback_txns: List[str] = []

        tb_tot = getattr(self.llm, "cumulative_total_tokens", 0)
        tb_p = getattr(self.llm, "cumulative_prompt_tokens", 0)
        tb_c = getattr(self.llm, "cumulative_completion_tokens", 0)

        tokens_before = tb_tot if isinstance(tb_tot, (int, float)) else 0
        prompt_toks_before = tb_p if isinstance(tb_p, (int, float)) else 0
        comp_toks_before = tb_c if isinstance(tb_c, (int, float)) else 0

        try:
            response = self.llm.chat(messages=messages)
            choice = response.choices[0]
            raw_content = choice.message.content or ""

            cleaned = raw_content.strip()
            if "```" in cleaned:
                match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
                if match:
                    cleaned = match.group(1)
            if "{" in cleaned and "}" in cleaned:
                start = cleaned.find("{")
                end = cleaned.rfind("}") + 1
                cleaned = cleaned[start:end]

            parsed_data = json.loads(cleaned)
            if isinstance(parsed_data, dict) and "decisions" in parsed_data:
                for d in parsed_data.get("decisions", []):
                    if isinstance(d, dict) and not d.get("evidence"):
                        d["evidence"] = [f"Phase 1 exception: {d.get('exception_type', 'UNKNOWN')}"]
            batch_resp = BatchAgentResponse.model_validate(parsed_data)

            # Check that decisions correspond to expected transactions
            for dec in batch_resp.decisions:
                tid = dec.transaction_id
                if tid in expected_txn_ids and tid not in batch_decisions_map:
                    # Clamp confidence to [0, 1]
                    dec.confidence = max(0.0, min(1.0, float(dec.confidence)))
                    batch_decisions_map[tid] = dec

        except Exception:
            # Batch call failed or produced malformed JSON; all transactions fall back
            pass

        # Step 2: Check for missing transactions and execute individual fallback
        for tid in expected_txn_ids:
            if tid not in batch_decisions_map:
                fallback_txns.append(tid)
                exc_rec = cases_map.get(tid)
                if exc_rec:
                    fallback_decision, _ = self.fallback_agent.investigate_exception(exc_rec)
                    batch_decisions_map[tid] = fallback_decision
                else:
                    batch_decisions_map[tid] = AgentDecision(
                        transaction_id=tid,
                        decision="HUMAN_REVIEW",
                        exception_type="UNKNOWN",
                        resolution_type="NONE",
                        reason="Batch case evaluation failed and could not be recovered.",
                        evidence=["Batch evaluation failed."],
                        confidence=0.0,
                        recommended_action="Manual review required.",
                    )

        # Step 3: Deterministic Proof Enforcement (Python/Decimal is Authoritative)
        for case in prefetched_cases:
            tid = case.transaction_id
            exc_rec = cases_map.get(tid, {})
            exc_type = exc_rec.get("reason", "UNKNOWN")

            state = EvidenceState(tid)
            state.payment = case.payment
            state.ledger = case.ledger
            state.bank_records = case.bank_records
            state.adjustments = case.adjustments
            state.duplicate_check = case.duplicate_check
            state.expected_settlement = case.expected_settlement
            state.adjusted_expected_settlement = case.adjusted_expected_settlement

            is_proven, proof_data = has_sufficient_resolution_evidence(state, exc_type)
            if is_proven and proof_data:
                current_dec = batch_decisions_map.get(tid)
                evidence_list = current_dec.evidence if current_dec and current_dec.evidence else [f"Phase 1 exception: {exc_type}"]
                batch_decisions_map[tid] = build_proven_adjustment_resolution(
                    txn_id=tid,
                    exception_type=exc_type,
                    evidence=evidence_list,
                    resolution_data=proof_data,
                )

        perf_end = time.perf_counter()
        t_end = datetime.now(timezone.utc)
        processing_time = max(perf_end - perf_start, 0.0001)

        tok_total = getattr(self.llm, "cumulative_total_tokens", 0)
        tok_prompt = getattr(self.llm, "cumulative_prompt_tokens", 0)
        tok_comp = getattr(self.llm, "cumulative_completion_tokens", 0)

        tokens_after = tok_total if isinstance(tok_total, (int, float)) else 0
        prompt_toks_after = tok_prompt if isinstance(tok_prompt, (int, float)) else 0
        comp_toks_after = tok_comp if isinstance(tok_comp, (int, float)) else 0

        delta_total = max(tokens_after - tokens_before, 0)
        if delta_total == 0 and tokens_after > 0:
            delta_total = tokens_after
        delta_prompt = max(prompt_toks_after - prompt_toks_before, 0)
        if delta_prompt == 0 and prompt_toks_after > 0:
            delta_prompt = prompt_toks_after
        delta_comp = max(comp_toks_after - comp_toks_before, 0)
        if delta_comp == 0 and comp_toks_after > 0:
            delta_comp = comp_toks_after


        # Assemble decisions in input order
        ordered_decisions = [batch_decisions_map[tid] for tid in expected_txn_ids]

        provider_name = getattr(self.llm, "provider", "demo")
        model_name = getattr(self.llm, "model", "demo")

        type_counts: Dict[str, int] = {}
        for c in batch_exceptions:
            etype = c.get("reason") or c.get("exception_type") or c.get("initial_exception") or "UNKNOWN"
            type_counts[etype] = type_counts.get(etype, 0) + 1

        log = BatchInvestigationLog(
            batch_id=batch_id,
            batch_size=len(batch_exceptions),
            transaction_ids=expected_txn_ids,
            provider=provider_name,
            model=model_name,
            request_start=t_start,
            request_end=t_end,
            processing_time_sec=round(processing_time, 4),
            prompt_tokens=delta_prompt if delta_prompt > 0 else None,
            completion_tokens=delta_comp if delta_comp > 0 else None,
            total_tokens=delta_total if delta_total > 0 else None,
            llm_interactions=1 + len(fallback_txns),
            fallback_count=len(fallback_txns),
            fallback_transaction_ids=fallback_txns,
            decisions=ordered_decisions,
            partition_strategy="balanced_exception_type",
            case_count=len(batch_exceptions),
            exception_type_counts=type_counts,
        )

        return ordered_decisions, log

    def investigate_exceptions_batch(
        self,
        exceptions: List[Dict[str, Any]],
        batch_size: int = 5,
    ) -> Tuple[List[AgentDecision], List[BatchInvestigationLog]]:
        """
        Splits exceptions into batches of size `batch_size` (5–10) and investigates
        each batch sequentially.
        """
        if batch_size < 1 or batch_size > 10:
            raise ValueError(f"batch_size must be between 1 and 10, got {batch_size}")

        if not exceptions:
            return [], []

        from src.agent.batch_partitioner import partition_exceptions_balanced

        all_decisions: List[AgentDecision] = []
        batch_logs: List[BatchInvestigationLog] = []

        chunks = partition_exceptions_balanced(exceptions, batch_size=batch_size)
        for chunk in chunks:
            decisions, log = self.investigate_batch(chunk)
            all_decisions.extend(decisions)
            batch_logs.append(log)

        return all_decisions, batch_logs
