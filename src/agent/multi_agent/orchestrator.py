"""
Multi-Agent Orchestrator — coordinates exception routing, Investigator Agent,
Verifier Agent, deterministic arithmetic verification, and final safety policy execution.
"""

import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from src.agent.controller import (
    EvidenceState,
    LLMClient,
    build_proven_adjustment_resolution,
    has_sufficient_resolution_evidence,
)
from src.agent.multi_agent.investigator import InvestigatorAgent
from src.agent.multi_agent.verifier import VerifierAgent
from src.agent.schemas import (
    AgentDecision,
    InvestigationLog,
    InvestigationProposal,
    ToolCallTrace,
    VerificationResult,
)
from src.agent.tools import FinancialToolkit
from src.agent.trace import AgentTracer, default_tracer


class MultiAgentOrchestrator:
    """
    Coordinates multi-agent investigation workflow without performing authoritative mental arithmetic.
    Applies strict disagreement handling, deterministic proof enforcement, and safety policies.
    """

    def __init__(
        self,
        toolkit: FinancialToolkit,
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        investigator_model: Optional[str] = None,
        verifier_model: Optional[str] = None,
        max_tool_calls: int = 5,
        tracer: Optional[AgentTracer] = None,
    ) -> None:
        self.toolkit = toolkit
        self.tracer = tracer or default_tracer
        self.provider = (provider or os.getenv("LLM_PROVIDER") or "demo").strip().lower()
        self.api_key = api_key
        self.tracer = tracer or default_tracer

        # Resolve role providers
        if provider == "demo":
            inv_provider = "demo"
            ver_provider = "demo"
        else:
            inv_provider = (os.getenv("INVESTIGATOR_PROVIDER") or provider or os.getenv("LLM_PROVIDER") or "demo").strip().lower()
            ver_provider = (os.getenv("VERIFIER_PROVIDER") or provider or os.getenv("LLM_PROVIDER") or "demo").strip().lower()

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

        # Display Multi-Agent Configuration at startup
        print("\n========================================")
        print("Multi-Agent Configuration")
        print("Investigator:")
        print(f"  Provider: {inv_provider}")
        print(f"  Model: {inv_model}")
        print("Verifier:")
        print(f"  Provider: {ver_provider}")
        print(f"  Model: {ver_model}")
        print("========================================\n")

        # Instantiate role-specific LLM clients
        self.investigator_llm = LLMClient(provider=inv_provider, api_key=inv_key, model=inv_model)
        self.verifier_llm = LLMClient(provider=ver_provider, api_key=ver_key, model=ver_model)

        self.investigator = InvestigatorAgent(
            toolkit=self.toolkit,
            llm_client=self.investigator_llm,
            max_tool_calls=max_tool_calls,
            tracer=self.tracer,
        )
        self.verifier = VerifierAgent(
            llm_client=self.verifier_llm,
            toolkit=self.toolkit,
            tracer=self.tracer,
        )



    def should_route_to_multi_agent(self, exception_record: Dict[str, Any]) -> bool:
        """
        Determines whether an exception requires multi-agent investigation
        or can follow a fast deterministic path.
        """
        exc_type = exception_record.get("reason", "UNKNOWN")
        # Missing ledger records with no reconstructible records can follow deterministic path
        if exc_type == "MISSING_LEDGER_RECORD":
            txn_id = exception_record.get("transaction_id", "")
            # Check if adjustments or bank exists
            adjs = self.toolkit.get_adjustments(txn_id).get("adjustments", [])
            if not adjs:
                return False
        return True

    def investigate_exception(
        self, exception_record: Dict[str, Any]
    ) -> Tuple[AgentDecision, InvestigationLog]:
        """
        Runs the full controlled multi-agent investigation workflow.
        """
        t0 = time.time()
        txn_id = exception_record.get("transaction_id", "UNKNOWN")
        exception_type = exception_record.get("reason", "UNKNOWN")
        timestamp = datetime.now(timezone.utc)

        self.tracer.transaction_header(txn_id, exception_type)

        # Fast routing check
        if not self.should_route_to_multi_agent(exception_record):
            self.tracer.orchestrator_routing("Deterministic Fast Path", fast_path=True)
            decision = AgentDecision(
                transaction_id=txn_id,
                decision="HUMAN_REVIEW",
                exception_type=exception_type,
                resolution_type="NONE",
                reason=f"Payment captured but missing ledger entry in ERP. Deterministic routing applied.",
                evidence=[f"Phase 1 exception: {exception_type}", "Missing ERP ledger record."],
                confidence=0.95,
                recommended_action="Post missing ledger entry in ERP.",
            )
            self.tracer.final_decision(
                investigator_dec="HUMAN_REVIEW",
                verifier_dec="N/A",
                proof_pass=False,
                final_decision="HUMAN_REVIEW",
                resolution_type="NONE",
                resolution_source="DETERMINISTIC_ROUTING",
                reason=decision.reason,
            )
            self.tracer.transaction_summary(
                txn_id=txn_id,
                investigator_prov="N/A",
                verifier_prov="N/A",
                inv_calls=0,
                ver_calls=0,
                model_interactions=0,
                latency_sec=time.time() - t0,
                tokens=None,
                final_decision="HUMAN_REVIEW",
                resolution_source="DETERMINISTIC_ROUTING",
            )
            log = InvestigationLog(
                transaction_id=txn_id,
                initial_exception=exception_type,
                tools_used=[],
                evidence=decision.evidence,
                decision=decision.decision,
                resolution_type=decision.resolution_type,
                reason=decision.reason,
                confidence=decision.confidence,
                recommended_action=decision.recommended_action,
                timestamp=timestamp,
                tool_call_count=0,
                tool_traces=[],
                agent_mode="MULTI_AGENT",
                resolution_source="DETERMINISTIC_ROUTING",
                investigator_calls=0,
                verifier_calls=0,
                model_interactions=0,
            )
            return decision, log

        # -------------------------------------------------------------
        # Step 1: Investigator Agent explores records and collects evidence
        # -------------------------------------------------------------
        self.tracer.orchestrator_routing("Investigator")
        proposal, evidence, tool_traces, evidence_state, tool_calls_count = self.investigator.investigate(
            exception_record
        )
        self.tracer.orchestrator_step_completed("Investigator")
        investigator_calls = getattr(self.investigator, "last_successful_calls", 0)

        # Check for provider failure on investigator
        if proposal.confidence == 0.0 and "Provider" in (proposal.reason or ""):
            decision = AgentDecision(
                transaction_id=txn_id,
                decision="NOT_EVALUATED",
                exception_type=exception_type,
                resolution_type="NONE",
                reason=proposal.reason or "Provider request failed during investigation.",
                evidence=evidence or [f"Phase 1 exception: {exception_type}"],
                confidence=0.0,
                recommended_action=proposal.recommended_action or "Investigation not evaluated.",
            )
            log = InvestigationLog(
                transaction_id=txn_id,
                initial_exception=exception_type,
                tools_used=[t.tool_name for t in tool_traces],
                evidence=evidence or [f"Phase 1 exception: {exception_type}"],
                decision=decision.decision,
                resolution_type=decision.resolution_type,
                reason=decision.reason,
                confidence=decision.confidence,
                recommended_action=decision.recommended_action,
                timestamp=timestamp,
                tool_call_count=tool_calls_count,
                tool_traces=tool_traces,
                agent_mode="MULTI_AGENT",
                resolution_source="PROVIDER_ERROR",
                investigator_proposal=proposal.model_dump(),
                investigator_calls=investigator_calls,
                verifier_calls=0,
                model_interactions=investigator_calls,
            )
            return decision, log

        # -------------------------------------------------------------
        # Step 2: Deterministic Proof Check (Python/Decimal is Authoritative)
        # -------------------------------------------------------------
        is_proven, proof_data = has_sufficient_resolution_evidence(evidence_state, exception_type)

        # -------------------------------------------------------------
        # Step 3: Verifier Agent independently verifies proposal
        # -------------------------------------------------------------
        self.tracer.orchestrator_routing("Verifier")
        verification = self.verifier.verify(
            exception_record=exception_record,
            source_evidence=evidence,
            evidence_state=evidence_state,
            proposal=proposal,
        )
        self.tracer.orchestrator_step_completed("Verifier")
        verifier_calls = getattr(self.verifier, "last_successful_calls", 0)

        # Check for provider failure on verifier
        if verification.confidence == 0.0 and "Provider" in verification.reason:
            if is_proven and proof_data:
                # Deterministic proof overrides verifier technical error safely
                decision = build_proven_adjustment_resolution(txn_id, exception_type, evidence, proof_data)
                res_source = "DETERMINISTIC_EVIDENCE"
            else:
                decision = AgentDecision(
                    transaction_id=txn_id,
                    decision="NOT_EVALUATED",
                    exception_type=exception_type,
                    resolution_type="NONE",
                    reason=verification.reason,
                    evidence=evidence or [f"Phase 1 exception: {exception_type}"],
                    confidence=0.0,
                    recommended_action="Manual review required due to verifier API failure.",
                )
                res_source = "PROVIDER_ERROR"

            log = InvestigationLog(
                transaction_id=txn_id,
                initial_exception=exception_type,
                tools_used=[t.tool_name for t in tool_traces],
                evidence=evidence or [f"Phase 1 exception: {exception_type}"],
                decision=decision.decision,
                resolution_type=decision.resolution_type,
                reason=decision.reason,
                confidence=decision.confidence,
                recommended_action=decision.recommended_action,
                timestamp=timestamp,
                tool_call_count=tool_calls_count,
                tool_traces=tool_traces,
                agent_mode="MULTI_AGENT",
                resolution_source=res_source,
                investigator_proposal=proposal.model_dump(),
                verification_result=verification.model_dump(),
                investigator_calls=investigator_calls,
                verifier_calls=verifier_calls,
                model_interactions=investigator_calls + verifier_calls,
            )
            return decision, log

        # -------------------------------------------------------------
        # Step 4: Disagreement Policy & Final Controller Decision
        # -------------------------------------------------------------
        self.tracer.orchestrator_policy_start()
        inv_dec = proposal.proposed_resolution
        ver_dec = verification.decision
        disagreement = inv_dec != ver_dec

        final_decision_str: str
        resolution_type = "NONE"
        resolved_difference = None
        resolution_source: str
        final_reason: str
        final_action: str
        final_confidence: float

        # Deterministic proof is supreme for AUTO_RESOLVED
        if is_proven and proof_data:
            final_decision_str = "AUTO_RESOLVED"
            resolution_type = proof_data.get("resolution_type", "ADJUSTMENT_EXPLAINED")
            resolved_difference = proof_data.get("resolved_difference")
            resolution_source = "DETERMINISTIC_EVIDENCE"
            final_reason = proof_data.get("reason", proposal.reason or "Documented adjustments explain difference.")
            final_action = "No action needed; discrepancy fully accounted for by adjustment record."
            final_confidence = 1.0

        elif inv_dec == "AUTO_RESOLVED" and ver_dec == "AUTO_RESOLVED":
            # Both agree on AUTO_RESOLVED
            final_decision_str = "AUTO_RESOLVED"
            resolution_type = proposal.resolution_type or "ADJUSTMENT_EXPLAINED"
            resolved_difference = proposal.resolved_difference
            resolution_source = "MULTI_AGENT_CONSENSUS"
            final_reason = verification.reason or proposal.reason or "Multi-agent consensus confirmed adjustment resolution."
            final_action = proposal.recommended_action or "No action needed."
            final_confidence = min(proposal.confidence, verification.confidence)

        elif inv_dec == "AUTO_RESOLVED" and ver_dec == "HUMAN_REVIEW":
            # Disagreement: Conservative escalation
            final_decision_str = "HUMAN_REVIEW"
            resolution_type = "NONE"
            resolution_source = "VERIFIER_ESCALATION"
            final_reason = f"Verifier flagged insufficient proof: {verification.reason}"
            final_action = "Review transaction evidence manually."
            final_confidence = verification.confidence

        elif inv_dec == "HUMAN_REVIEW" and ver_dec == "AUTO_RESOLVED":
            # Disagreement: Verifier wants auto-resolve but investigator proposed human review
            # Without deterministic proof, default safely to HUMAN_REVIEW
            final_decision_str = "HUMAN_REVIEW"
            resolution_type = "NONE"
            resolution_source = "DISAGREEMENT_SAFEGUARD"
            final_reason = f"Disagreement between agents; defaulting to human review. (Verifier: {verification.reason})"
            final_action = "Manual review required due to conflicting agent assessments."
            final_confidence = 0.5

        else:
            # Both agree on HUMAN_REVIEW
            final_decision_str = "HUMAN_REVIEW"
            resolution_type = "NONE"
            resolution_source = "MULTI_AGENT_CONSENSUS"
            final_reason = proposal.reason or verification.reason or "Unexplained discrepancy requiring manual review."
            final_action = proposal.recommended_action or "Review transaction records."
            final_confidence = max(proposal.confidence, verification.confidence)

        self.tracer.final_decision(
            investigator_dec=inv_dec,
            verifier_dec=ver_dec,
            proof_pass=bool(is_proven),
            final_decision=final_decision_str,
            resolution_type=resolution_type,
            resolution_source=resolution_source,
            reason=final_reason,
        )

        inv_p = getattr(self.investigator_llm, "provider_name", getattr(self.investigator_llm, "provider", "DEMO"))
        ver_p = getattr(self.verifier_llm, "provider_name", getattr(self.verifier_llm, "provider", "DEMO"))
        inv_toks = getattr(self.investigator_llm, "cumulative_total_tokens", 0)
        ver_toks = getattr(self.verifier_llm, "cumulative_total_tokens", 0)
        toks = (inv_toks if isinstance(inv_toks, (int, float)) else 0) + (ver_toks if isinstance(ver_toks, (int, float)) else 0)

        self.tracer.transaction_summary(
            txn_id=txn_id,
            investigator_prov=inv_p,
            verifier_prov=ver_p,
            inv_calls=investigator_calls,
            ver_calls=verifier_calls,
            model_interactions=investigator_calls + verifier_calls,
            latency_sec=time.time() - t0,
            tokens=toks if toks > 0 else None,
            final_decision=final_decision_str,
            resolution_source=resolution_source,
        )

        decision = AgentDecision(
            transaction_id=txn_id,
            decision=final_decision_str,
            exception_type=exception_type,
            resolution_type=resolution_type,
            resolved_difference=resolved_difference,
            reason=final_reason,
            evidence=evidence or [f"Phase 1 exception: {exception_type}"],
            confidence=max(0.0, min(1.0, final_confidence)),
            recommended_action=final_action,
        )

        log = InvestigationLog(
            transaction_id=txn_id,
            initial_exception=exception_type,
            tools_used=[t.tool_name for t in tool_traces],
            evidence=evidence or [f"Phase 1 exception: {exception_type}"],
            decision=decision.decision,
            resolution_type=decision.resolution_type,
            resolved_difference=decision.resolved_difference,
            reason=decision.reason,
            confidence=decision.confidence,
            recommended_action=decision.recommended_action,
            timestamp=timestamp,
            tool_call_count=tool_calls_count,
            tool_traces=tool_traces,
            agent_mode="MULTI_AGENT",
            resolution_source=resolution_source,
            investigator_proposal=proposal.model_dump(),
            verification_result=verification.model_dump(),
            disagreement_detected=disagreement,
            investigator_calls=investigator_calls,
            verifier_calls=verifier_calls,
            model_interactions=investigator_calls + verifier_calls,
        )

        return decision, log
