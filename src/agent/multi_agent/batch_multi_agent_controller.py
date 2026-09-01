"""
Batch Multi-Agent Investigation Controller for AI Finance Controller.

Executes unified Phase 2 reconciliation:
1. Prefetches deterministic evidence for all cases in a batch.
2. Invokes Investigator Agent in batch mode to formulate resolution proposals.
3. Enforces authoritative Python Decimal proof verification (`has_sufficient_resolution_evidence`).
4. Invokes Verifier Agent in batch mode to independently critique proposals against ground evidence.
5. Applies consensus and escalation policies to produce final AgentDecisions.
"""

from datetime import datetime, timezone
import json
import os
import re
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from src.agent.batch_controller import prefetch_case_evidence
from src.agent.controller import (
    AgentController,
    EvidenceState,
    LLMClient,
    build_proven_adjustment_resolution,
    has_sufficient_resolution_evidence,
)
from src.agent.multi_agent.orchestrator import MultiAgentOrchestrator
from src.agent.prompts import (
    BATCH_INVESTIGATOR_SYSTEM_PROMPT,
    BATCH_VERIFIER_SYSTEM_PROMPT,
    build_batch_investigator_prompt,
    build_batch_verifier_prompt,
)
from src.agent.schemas import (
    AgentDecision,
    BatchInvestigationCase,
    BatchInvestigationLog,
    BatchInvestigatorResponse,
    BatchVerifierResponse,
    InvestigationProposal,
    VerificationResult,
)
from src.agent.tools import FinancialToolkit
from src.agent.trace import AgentTracer, default_tracer


class BatchMultiAgentController:
    """
    Orchestrates unified batch multi-agent investigations combining
    Investigator Agent, Verifier Agent, and deterministic proof enforcement.
    """

    def __init__(
        self,
        toolkit: FinancialToolkit,
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        investigator_model: Optional[str] = None,
        verifier_model: Optional[str] = None,
        tracer: Optional[AgentTracer] = None,
    ) -> None:
        self.toolkit = toolkit
        self.tracer = tracer or default_tracer
        self.provider = (provider or os.getenv("LLM_PROVIDER") or "demo").strip().lower()
        self.api_key = api_key

        # Resolve role providers
        if self.provider == "demo":
            inv_provider = "demo"
            ver_provider = "demo"
        else:
            inv_provider = (os.getenv("INVESTIGATOR_PROVIDER") or self.provider or os.getenv("LLM_PROVIDER") or "demo").strip().lower()
            ver_provider = (os.getenv("VERIFIER_PROVIDER") or self.provider or os.getenv("LLM_PROVIDER") or "demo").strip().lower()

        # Resolve Investigator role configuration
        inv_key = (os.getenv("INVESTIGATOR_API_KEY") or (api_key if inv_provider == self.provider else None) or "").strip()
        if not inv_key:
            if inv_provider == "grok":
                inv_key = (os.getenv("GROK_API_KEY") or os.getenv("XAI_API_KEY") or "").strip()
            elif inv_provider == "gemini":
                inv_key = (os.getenv("GEMINI_API_KEY") or "").strip()
            elif inv_provider == "openrouter":
                inv_key = (os.getenv("OPENROUTER_API_KEY") or "").strip()

        inv_model = (investigator_model or os.getenv("INVESTIGATOR_MODEL") or "").strip()
        if not inv_model:
            if inv_provider == "grok":
                inv_model = (os.getenv("GROK_MODEL") or os.getenv("XAI_MODEL") or "grok-beta").strip()
            elif inv_provider == "gemini":
                inv_model = (os.getenv("GEMINI_MODEL") or "gemini-2.5-flash").strip()
            elif inv_provider == "openrouter":
                inv_model = (os.getenv("OPENROUTER_MODEL") or "").strip()
            elif inv_provider == "demo":
                inv_model = "demo"

        # Resolve Verifier role configuration
        ver_key = (os.getenv("VERIFIER_API_KEY") or (api_key if ver_provider == self.provider else None) or "").strip()
        if not ver_key:
            if ver_provider == "gemini":
                ver_key = (os.getenv("GEMINI_API_KEY") or "").strip()
            elif ver_provider == "grok":
                ver_key = (os.getenv("GROK_API_KEY") or os.getenv("XAI_API_KEY") or "").strip()
            elif ver_provider == "openrouter":
                ver_key = (os.getenv("OPENROUTER_API_KEY") or "").strip()

        ver_model = (verifier_model or os.getenv("VERIFIER_MODEL") or "").strip()
        if not ver_model:
            if ver_provider == "gemini":
                ver_model = (os.getenv("GEMINI_MODEL") or "gemini-2.5-flash").strip()
            elif ver_provider == "grok":
                ver_model = (os.getenv("GROK_MODEL") or os.getenv("XAI_MODEL") or "grok-beta").strip()
            elif ver_provider == "openrouter":
                ver_model = (os.getenv("OPENROUTER_MODEL") or "").strip()
            elif ver_provider == "demo":
                ver_model = "demo"

        self.investigator_llm = LLMClient(provider=inv_provider, api_key=inv_key, model=inv_model)
        self.verifier_llm = LLMClient(provider=ver_provider, api_key=ver_key, model=ver_model)
        self.fallback_orchestrator = MultiAgentOrchestrator(
            toolkit=toolkit,
            provider=provider,
            api_key=api_key,
            investigator_model=inv_model,
            verifier_model=ver_model,
            tracer=self.tracer,
        )

    def investigate_batch(
        self,
        batch_exceptions: List[Dict[str, Any]],
    ) -> Tuple[List[AgentDecision], BatchInvestigationLog]:
        """
        Investigates a batch of exception records using the unified multi-agent pipeline.
        """
        if not batch_exceptions:
            raise ValueError("batch_exceptions cannot be empty")

        batch_id = f"batch_ma_{uuid.uuid4().hex[:8]}"
        expected_txn_ids = [e.get("transaction_id", "UNKNOWN") for e in batch_exceptions]
        cases_map = {e.get("transaction_id", "UNKNOWN"): e for e in batch_exceptions}

        t_start = datetime.now(timezone.utc)
        perf_start = time.perf_counter()

        # Step 1: Deterministic Evidence Prefetch
        prefetched_cases: List[BatchInvestigationCase] = [
            prefetch_case_evidence(exc, self.toolkit) for exc in batch_exceptions
        ]

        # Step 2: Investigator Agent Batch Execution
        inv_messages: List[Dict[str, Any]] = [
            {"role": "system", "content": BATCH_INVESTIGATOR_SYSTEM_PROMPT},
            {"role": "user", "content": build_batch_investigator_prompt(prefetched_cases)},
        ]

        proposals_map: Dict[str, Dict[str, Any]] = {}
        fallback_txns: List[str] = []

        try:
            inv_resp = self.investigator_llm.chat(messages=inv_messages)
            inv_content = inv_resp.choices[0].message.content or ""
            cleaned_inv = self._clean_json(inv_content)
            parsed_inv = json.loads(cleaned_inv)

            raw_props = parsed_inv.get("proposals") or parsed_inv.get("decisions") or []
            for p in raw_props:
                tid = p.get("transaction_id")
                if tid in expected_txn_ids:
                    # Normalize resolution field
                    if "decision" in p and "proposed_resolution" not in p:
                        p["proposed_resolution"] = p["decision"]
                    proposals_map[tid] = p
        except Exception:
            pass

        # Step 3: Verifier Agent Batch Execution
        proposals_list = [
            proposals_map.get(tid, {
                "transaction_id": tid,
                "proposed_resolution": "HUMAN_REVIEW",
                "reason": "Default proposal",
            })
            for tid in expected_txn_ids
        ]

        ver_messages: List[Dict[str, Any]] = [
            {"role": "system", "content": BATCH_VERIFIER_SYSTEM_PROMPT},
            {"role": "user", "content": build_batch_verifier_prompt(prefetched_cases, proposals_list)},
        ]

        verifications_map: Dict[str, Dict[str, Any]] = {}
        try:
            ver_resp = self.verifier_llm.chat(messages=ver_messages)
            ver_content = ver_resp.choices[0].message.content or ""
            cleaned_ver = self._clean_json(ver_content)
            parsed_ver = json.loads(cleaned_ver)

            raw_vers = parsed_ver.get("verifications") or parsed_ver.get("decisions") or []
            for v in raw_vers:
                tid = v.get("transaction_id")
                if tid in expected_txn_ids:
                    verifications_map[tid] = v
        except Exception:
            pass

        # Step 4: Deterministic Proof Verification & Multi-Agent Consensus Resolution
        batch_decisions_map: Dict[str, AgentDecision] = {}

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

            # Authoritative deterministic proof check
            is_proven, proof_data = has_sufficient_resolution_evidence(state, exc_type)
            if is_proven and proof_data:
                batch_decisions_map[tid] = build_proven_adjustment_resolution(
                    txn_id=tid,
                    exception_type=exc_type,
                    evidence=[f"Phase 1 exception: {exc_type}"],
                    resolution_data=proof_data,
                )
                continue

            # Multi-Agent Consensus Policy
            inv_prop = proposals_map.get(tid)
            ver_res = verifications_map.get(tid)

            if not inv_prop or not ver_res:
                # Missing LLM output -> trigger fallback orchestrator for this case
                fallback_txns.append(tid)
                try:
                    fb_dec, _ = self.fallback_orchestrator.investigate_exception(exc_rec)
                    batch_decisions_map[tid] = fb_dec
                except Exception:
                    batch_decisions_map[tid] = AgentDecision(
                        transaction_id=tid,
                        decision="HUMAN_REVIEW",
                        exception_type=exc_type,
                        resolution_type="NONE",
                        reason="Multi-agent batch evaluation failed; escalated to human review.",
                        evidence=[f"Phase 1 exception: {exc_type}"],
                        confidence=0.5,
                        recommended_action="Manual review required.",
                    )
                continue

            inv_decision = inv_prop.get("proposed_resolution") or inv_prop.get("decision", "HUMAN_REVIEW")
            ver_decision = ver_res.get("decision", "HUMAN_REVIEW")
            inv_conf = float(inv_prop.get("confidence", 0.95))
            ver_conf = float(ver_res.get("confidence", 0.95))

            if inv_decision == "AUTO_RESOLVED" and ver_decision == "AUTO_RESOLVED":
                final_decision = "AUTO_RESOLVED"
                res_type = inv_prop.get("resolution_type", "ADJUSTMENT_EXPLAINED")
                res_diff = inv_prop.get("resolved_difference")
                reason = inv_prop.get("reason", "Multi-agent consensus resolved discrepancy.")
                action = inv_prop.get("recommended_action", "No action needed.")
                confidence = min(inv_conf, ver_conf)
            else:
                final_decision = "HUMAN_REVIEW"
                res_type = "NONE"
                res_diff = None
                if inv_decision == "AUTO_RESOLVED" and ver_decision == "HUMAN_REVIEW":
                    reason = f"Verifier escalated to human review: {ver_res.get('reason', 'Verification rejected')}"
                    confidence = ver_conf
                elif inv_decision == "HUMAN_REVIEW" and ver_decision == "AUTO_RESOLVED":
                    reason = "Disagreement safeguard: Investigator proposed human review."
                    confidence = 0.5
                else:
                    reason = inv_prop.get("reason") or ver_res.get("reason") or "Discrepancy requires manual review."
                    confidence = max(inv_conf, ver_conf)
                action = inv_prop.get("recommended_action") or "Review discrepancy with operations team."

            ev_list = inv_prop.get("evidence") or [f"Phase 1 exception: {exc_type}"]
            batch_decisions_map[tid] = AgentDecision(
                transaction_id=tid,
                decision=final_decision,
                exception_type=exc_type,
                resolution_type=res_type,
                resolved_difference=res_diff,
                reason=reason,
                evidence=ev_list,
                confidence=max(0.0, min(1.0, confidence)),
                recommended_action=action,
            )

        perf_end = time.perf_counter()
        t_end = datetime.now(timezone.utc)
        processing_time = max(perf_end - perf_start, 0.0001)

        # Token calculation from both agents
        inv_tok_total = getattr(self.investigator_llm, "cumulative_total_tokens", 0) or 0
        inv_tok_p = getattr(self.investigator_llm, "cumulative_prompt_tokens", 0) or 0
        inv_tok_c = getattr(self.investigator_llm, "cumulative_completion_tokens", 0) or 0

        ver_tok_total = getattr(self.verifier_llm, "cumulative_total_tokens", 0) or 0
        ver_tok_p = getattr(self.verifier_llm, "cumulative_prompt_tokens", 0) or 0
        ver_tok_c = getattr(self.verifier_llm, "cumulative_completion_tokens", 0) or 0

        total_tok = inv_tok_total + ver_tok_total
        total_p = inv_tok_p + ver_tok_p
        total_c = inv_tok_c + ver_tok_c

        ordered_decisions = [batch_decisions_map[tid] for tid in expected_txn_ids]

        model_name = getattr(self.investigator_llm, "model", "demo")

        log = BatchInvestigationLog(
            batch_id=batch_id,
            batch_size=len(batch_exceptions),
            transaction_ids=expected_txn_ids,
            provider=self.provider,
            model=model_name,
            request_start=t_start,
            request_end=t_end,
            processing_time_sec=processing_time,
            prompt_tokens=total_p,
            completion_tokens=total_c,
            total_tokens=total_tok,
            llm_interactions=2,
            fallback_count=len(fallback_txns),
            fallback_transaction_ids=fallback_txns,
            decisions=ordered_decisions,
            case_count=len(batch_exceptions),
        )

        return ordered_decisions, log

    @staticmethod
    def _clean_json(raw_content: str) -> str:
        """Strips markdown code fences and cleans JSON output."""
        cleaned = raw_content.strip()
        if "```" in cleaned:
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
            if match:
                cleaned = match.group(1)
        if "{" in cleaned and "}" in cleaned:
            start = cleaned.find("{")
            end = cleaned.rfind("}") + 1
            cleaned = cleaned[start:end]
        return cleaned
