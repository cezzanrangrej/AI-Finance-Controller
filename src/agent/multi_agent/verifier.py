"""
Verifier Agent — independently and conservatively evaluates whether the Investigator's
proposed resolution is supported by the collected evidence and deterministic calculations.
"""

import json
import re
from typing import Any, Dict, List, Optional

from src.agent.controller import EvidenceState, LLMClient
from src.agent.prompts import VERIFIER_SYSTEM_PROMPT, build_verifier_prompt
from src.agent.schemas import InvestigationProposal, VerificationResult
from src.agent.tools import FinancialToolkit
from src.agent.trace import AgentTracer, default_tracer
from src.utils.formatters import format_currency, safe_decimal, safe_numeric


class VerifierAgent:
    """
    Independently verifies investigation findings against objective financial facts
    and deterministic calculations.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        toolkit: Optional[FinancialToolkit] = None,
        tracer: Optional[AgentTracer] = None,
    ) -> None:
        self.llm = llm_client
        self.toolkit = toolkit
        self.tracer = tracer or default_tracer

    def verify(
        self,
        exception_record: Dict[str, Any],
        source_evidence: List[str],
        evidence_state: EvidenceState,
        proposal: InvestigationProposal,
    ) -> VerificationResult:
        """
        Executes independent verification of the proposal.

        Returns:
            VerificationResult with verified status, decision, and evidence references.
        """
        txn_id = exception_record.get("transaction_id", "UNKNOWN")
        prov_name = getattr(self.llm, "provider_name", getattr(self.llm, "provider", "DEMO"))
        model_name = getattr(self.llm, "model", None)

        self.tracer.verifier_review_started(prov_name, model_name)

        # Compile deterministic calculations summary from evidence_state / exception
        deterministic_calculations = self._compile_deterministic_calcs(exception_record, evidence_state)

        messages = [
            {"role": "system", "content": VERIFIER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": build_verifier_prompt(
                    exception_record=exception_record,
                    source_evidence=source_evidence,
                    deterministic_calculations=deterministic_calculations,
                    proposal=proposal.model_dump(),
                ),
            },
        ]

        self.last_successful_calls = 0
        try:
            response = self.llm.chat(messages=messages, max_tokens=250)
            choice = response.choices[0]
            content = choice.message.content or ""
            res = self._parse_verification(content, txn_id, proposal)
            self.tracer.verifier_review_result(prov_name, res.verified, res.decision, res.reason, res.contradictions)
            self.last_successful_calls = 1
            return res
        except Exception as e:
            self.tracer.provider_error("Verifier", prov_name, "API_ERROR", "NOT_EVALUATED", str(e))
            self.last_successful_calls = 0
            # Conservative failure fallback
            return VerificationResult(
                transaction_id=txn_id,
                verified=False,
                decision="HUMAN_REVIEW",
                reason=f"Verifier provider request failed: {str(e)[:200]}",
                evidence_references=[],
                contradictions=[f"Verification failed due to provider error: {str(e)[:200]}"],
                confidence=0.0,
            )

    def _compile_deterministic_calcs(
        self,
        exception_record: Dict[str, Any],
        state: EvidenceState,
    ) -> Dict[str, Any]:
        """Summarizes known deterministic calculations for the verifier."""
        calcs: Dict[str, Any] = {
            "transaction_id": state.transaction_id,
            "exception_type": exception_record.get("reason", "UNKNOWN"),
        }

        if state.expected_settlement:
            calcs["expected_settlement"] = state.expected_settlement
        elif state.ledger:
            g = safe_decimal(state.ledger.get("gross_amount"))
            f = safe_decimal(state.ledger.get("fee")) or 0
            if g is not None:
                calcs["expected_settlement"] = {
                    "gross_amount": safe_numeric(g),
                    "fee": safe_numeric(f),
                    "expected_net": safe_numeric(g - f),
                    "calculation": f"{safe_numeric(g)} - {safe_numeric(f)} = {safe_numeric(g - f)}",
                }

        if state.adjusted_expected_settlement:
            calcs["adjusted_expected_settlement"] = state.adjusted_expected_settlement

        if state.adjustments:
            total_adj = sum((safe_decimal(a.get("amount")) or 0) for a in state.adjustments)
            calcs["adjustments_total"] = safe_numeric(total_adj)
            calcs["adjustments_count"] = len(state.adjustments)

        if state.duplicate_check:
            calcs["duplicate_check"] = state.duplicate_check
        elif state.bank_records:
            calcs["bank_records_count"] = len(state.bank_records)
            calcs["is_duplicate"] = len(state.bank_records) > 1

        return calcs

    def _parse_verification(
        self,
        content: str,
        txn_id: str,
        proposal: InvestigationProposal,
    ) -> VerificationResult:
        """Parses and validates LLM response into a VerificationResult."""
        try:
            cleaned = content.strip()
            if "```" in cleaned:
                match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
                if match:
                    cleaned = match.group(1)
            if "{" in cleaned and "}" in cleaned:
                start = cleaned.find("{")
                end = cleaned.rfind("}") + 1
                cleaned = cleaned[start:end]

            data = json.loads(cleaned)
            data.setdefault("transaction_id", txn_id)

            if "verified" not in data:
                data["verified"] = data.get("decision") == proposal.proposed_resolution

            if "confidence" in data and isinstance(data["confidence"], (int, float)):
                data["confidence"] = max(0.0, min(1.0, float(data["confidence"])))

            return VerificationResult(**data)
        except Exception as e:
            return VerificationResult(
                transaction_id=txn_id,
                verified=False,
                decision="HUMAN_REVIEW",
                reason=f"Verifier output parse error: {str(e)[:200]}",
                evidence_references=[],
                contradictions=["Verifier output could not be validated as structured JSON."],
                confidence=0.0,
            )
