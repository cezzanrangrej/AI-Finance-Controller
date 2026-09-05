"""
Agent Controller — orchestrates the full investigation workflow.

Sends Phase 1 exceptions to the LLM or executes deterministic Demo Mode,
dispatches tool calls, enforces MAX_TOOL_CALLS safety limit, validates
structured output, and produces auditable InvestigationLog records.
"""

import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

# Ensure project root on path
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.abspath(os.path.join(_current_dir, "..", ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from decimal import Decimal
from src.agent.json_utils import repair_and_parse_json
from src.agent.prompts import SYSTEM_PROMPT, build_investigation_prompt
from src.config import settings
from src.agent.schemas import AgentDecision, InvestigationLog, ToolCallTrace
from src.agent.tools import FinancialToolkit
from src.utils.formatters import format_amount, format_currency, safe_decimal, safe_float, safe_int, safe_numeric

# Maximum number of tool calls per investigation before auto-escalation
MAX_TOOL_CALLS = 5


class DemoLLMClient:
    """
    Deterministic Demo / Mock mode client implementation.
    Allows full offline execution and testing without network calls or API keys.
    """

    def __init__(self, model: Optional[str] = None) -> None:
        self.model = model or "demo"
        self.provider = "demo"
        self.mode = "DEMO"
        self.demo_mode = True
        self.last_prompt_tokens = None
        self.last_completion_tokens = None
        self.last_total_tokens = None

    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: str = "auto",
        max_tokens: Optional[int] = None,
    ) -> Any:
        """Executes deterministic Demo Mode chat."""
        return self._demo_chat(messages, tools)

    def _demo_chat(self, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]]) -> Any:
        """Deterministic demo mode chat implementation for offline / key-less runs."""
        # Check if this is a batch investigation request
        is_batch = False
        user_content = ""
        for m in messages:
            content = m.get("content") or ""
            if "BATCH INVESTIGATION MODE" in content:
                is_batch = True
            if m.get("role") == "user":
                user_content = content
                if "### Case" in user_content:
                    is_batch = True


        if is_batch:
            # Parse cases from batch user prompt
            import re
            case_blocks = re.findall(r"### Case \d+: \[([^\]]+)\] \(([^)]+)\)(.*?)(?=(?:### Case|\Z))", user_content, re.DOTALL)
            batch_decisions = []

            for txn_id, exc_type, block in case_blocks:
                txn_id = txn_id.strip()
                exc_type = exc_type.strip()

                # Extract details from block text
                has_dup = "is_duplicate = True" in block or "Multiple (2)" in block
                is_missing_ledger = "Ledger: Gross = None" in block or "MISSING_LEDGER_RECORD" in exc_type
                is_missing_bank = "Bank Records: None" in block or "MISSING_BANK_RECORD" in exc_type

                adj_match = re.search(r"Adjustments: (.*?)(?=\n- Duplicate Check|\Z)", block, re.DOTALL)
                adj_text = adj_match.group(1).strip() if adj_match else "None"
                has_adj = adj_text != "None" and "₹" in adj_text

                # Extract calculated amounts
                exp_match = re.search(r"Expected net = ₹([\d,]+(?:\.\d+)?)", block)
                adj_exp_match = re.search(r"Adjusted net = ₹([\d,]+(?:\.\d+)?)", block)
                bank_match = re.search(r"credited ₹([\d,]+(?:\.\d+)?)", block)

                exp_net = safe_numeric(exp_match.group(1)) if exp_match else None
                adj_exp_net = safe_numeric(adj_exp_match.group(1)) if adj_exp_match else None
                bank_amt = safe_numeric(bank_match.group(1)) if bank_match else None

                # Extract adjustment amount
                adj_amt = None
                if has_adj:
                    adj_amt_match = re.search(r"₹([\d,]+(?:\.\d+)?)", adj_text)
                    if adj_amt_match:
                        adj_amt = safe_numeric(adj_amt_match.group(1))

                if is_missing_ledger:
                    dec = "HUMAN_REVIEW"
                    res_type = "NONE"
                    reason = "Payment captured but missing corresponding ledger entry in ERP."
                    action = "Post missing ledger entry in ERP."
                    diff = None
                    conf = 0.95
                elif is_missing_bank:
                    dec = "HUMAN_REVIEW"
                    res_type = "NONE"
                    reason = f"Expected settlement {format_currency(exp_net)} missing from bank statements." if exp_net else "Settlement missing from bank statement."
                    action = "Contact acquiring bank."
                    diff = None
                    conf = 0.95
                elif has_dup:
                    dec = "HUMAN_REVIEW"
                    res_type = "NONE"
                    reason = "Multiple bank settlement records found for single transaction."
                    action = "Review bank statement for potential duplicate credit."
                    diff = None
                    conf = 0.95
                elif has_adj and adj_exp_net is not None and bank_amt is not None and adj_exp_net == bank_amt and adj_amt:
                    dec = "AUTO_RESOLVED"
                    res_type = "ADJUSTMENT_EXPLAINED"
                    reason = f"Bank credit ({format_currency(bank_amt)}) equals expected settlement minus documented adjustment of {format_currency(adj_amt)}."
                    action = "No action needed; discrepancy fully accounted for by adjustment record."
                    diff = float(adj_amt)
                    conf = 1.0
                elif has_adj and "GROSS_AMOUNT_MISMATCH" in exc_type and adj_amt:
                    dec = "AUTO_RESOLVED"
                    res_type = "ADJUSTMENT_EXPLAINED"
                    reason = f"Gross amount discrepancy of {format_currency(adj_amt)} is explicitly accounted for by adjustment reference."
                    action = "No action needed; gross amount adjustment verified."
                    diff = float(adj_amt)
                    conf = 1.0
                else:
                    dec = "HUMAN_REVIEW"
                    res_type = "NONE"
                    reason = "Unexplained discrepancy with no valid adjustment record."
                    action = "Review settlement details."
                    diff = None
                    conf = 0.95

                batch_decisions.append({
                    "transaction_id": txn_id,
                    "decision": dec,
                    "proposed_resolution": dec,
                    "exception_type": exc_type,
                    "resolution_type": res_type,
                    "resolved_difference": diff,
                    "reason": reason,
                    "evidence": [f"Evaluated in batch mode ({exc_type})."],
                    "confidence": conf,
                    "recommended_action": action,
                })

            # Check if this is a batch verification or batch investigator request
            is_batch_verifier = any("BATCH VERIFICATION MODE" in (m.get("content") or "") for m in messages)
            is_batch_investigator = any("proposals" in (m.get("content") or "") for m in messages)

            if is_batch_verifier:
                batch_verifications = []
                for d in batch_decisions:
                    batch_verifications.append({
                        "transaction_id": d["transaction_id"],
                        "verified": True,
                        "decision": d["decision"],
                        "reason": f"Independent batch verification confirmed: {d['reason']}",
                        "evidence_references": ["Deterministic calculation and prefetched evidence verified."],
                        "contradictions": [],
                        "confidence": d["confidence"],
                    })
                resp_payload = {"verifications": batch_verifications}
            elif is_batch_investigator:
                resp_payload = {"proposals": batch_decisions}
            else:
                resp_payload = {"decisions": batch_decisions}

            class BatchDemoMessage:
                content = json.dumps(resp_payload)
                tool_calls = None

            class BatchDemoChoice:
                message = BatchDemoMessage()

            class BatchDemoResponse:
                choices = [BatchDemoChoice()]

            return BatchDemoResponse()

        txn_id = "UNKNOWN"
        user_content = ""
        is_verifier = False
        is_investigator = False

        for m in messages:
            content = m.get("content") or ""
            if "VERIFIER AGENT" in content or "Verification Instructions" in content:
                is_verifier = True
            if "INVESTIGATOR AGENT" in content:
                is_investigator = True
            if m.get("role") == "user":
                user_content = content
                for line in user_content.splitlines():
                    if "Transaction ID:" in line:
                        txn_id = line.split(":")[-1].strip()
                        break

        # Check if this is a Verifier Agent verification request
        if is_verifier:
            is_auto = "AUTO_RESOLVED" in user_content
            has_valid_proof = "ADJUSTMENT_EXPLAINED" in user_content or (is_auto and "adjusted_expected_net" in user_content)
            
            if has_valid_proof:
                v_decision = "AUTO_RESOLVED"
                v_reason = "Independent verification confirmed that documented adjustments mathematically explain the discrepancy."
                v_refs = ["Adjusted settlement matches bank credit exactly."]
                v_contra = []
                v_conf = 1.0
            else:
                v_decision = "HUMAN_REVIEW"
                v_reason = "Independent verification confirmed discrepancy is unexplained with no valid adjustment record."
                v_refs = ["No valid adjustment record found."]
                v_contra = []
                v_conf = 0.95

            v_payload = {
                "transaction_id": txn_id,
                "verified": True,
                "decision": v_decision,
                "reason": v_reason,
                "evidence_references": v_refs,
                "contradictions": v_contra,
                "confidence": v_conf,
            }

            class VerifierDemoMessage:
                content = json.dumps(v_payload)
                tool_calls = None

            class VerifierDemoChoice:
                message = VerifierDemoMessage()

            class VerifierDemoResponse:
                choices = [VerifierDemoChoice()]

            return VerifierDemoResponse()

        tool_responses = [m for m in messages if m.get("role") == "tool"]


        # Step 1: Call get_transaction first
        if len(tool_responses) == 0:
            class DemoFunction1:
                name = "get_transaction"
                arguments = json.dumps({"transaction_id": txn_id})

            class DemoToolCall1:
                id = "call_demo_1"
                function = DemoFunction1()

            class DemoMessage1:
                content = None
                tool_calls = [DemoToolCall1()]

            class DemoChoice1:
                message = DemoMessage1()

            class DemoResponse1:
                choices = [DemoChoice1()]

            return DemoResponse1()

        # Step 2: Call get_adjustments second
        if len(tool_responses) == 1:
            class DemoFunction2:
                name = "get_adjustments"
                arguments = json.dumps({"transaction_id": txn_id})

            class DemoToolCall2:
                id = "call_demo_2"
                function = DemoFunction2()

            class DemoMessage2:
                content = None
                tool_calls = [DemoToolCall2()]

            class DemoChoice2:
                message = DemoMessage2()

            class DemoResponse2:
                choices = [DemoChoice2()]

            return DemoResponse2()

        # Step 3: Parse tool responses and evaluate decision
        txn_data = {}
        adj_data = {}

        try:
            txn_data = json.loads(tool_responses[0].get("content", "{}"))
        except Exception:
            pass

        try:
            adj_data = json.loads(tool_responses[1].get("content", "{}"))
        except Exception:
            pass

        payment = txn_data.get("payment")
        ledger = txn_data.get("ledger")
        banks = txn_data.get("bank_records", [])
        adjustments = adj_data.get("adjustments", [])

        # Calculate numbers safely with Decimal precision
        payment_dec = safe_decimal(payment.get("amount")) if payment else None
        gross_dec = safe_decimal(ledger.get("gross_amount")) if ledger else None
        fee_dec = safe_decimal(ledger.get("fee")) if ledger else None
        expected_net_dec = (gross_dec - fee_dec) if (gross_dec is not None and fee_dec is not None) else None
        bank_dec = safe_decimal(banks[0].get("credited_amount")) if len(banks) == 1 else None

        payment_amt = safe_numeric(payment_dec)
        gross_amt = safe_numeric(gross_dec)
        fee_amt = safe_numeric(fee_dec)
        expected_net = safe_numeric(expected_net_dec)
        bank_amt = safe_numeric(bank_dec)

        total_adj_dec = sum((safe_decimal(a.get("amount")) or Decimal(0)) for a in adjustments)
        total_adj_amt = safe_numeric(total_adj_dec) or 0

        # Decision Evaluation Policy
        decision = "HUMAN_REVIEW"
        resolution_type = "NONE"
        resolved_diff = None
        reason = ""
        action = ""
        confidence = 0.95
        evidence = []

        if payment_amt is not None:
            evidence.append(f"Payment amount = {format_currency(payment_amt)}")
        if ledger:
            evidence.append(f"Ledger gross = {format_currency(gross_amt)}, fee = {format_currency(fee_amt)}")
            if expected_net is not None:
                evidence.append(f"Expected settlement = {format_currency(expected_net)}")
        if bank_amt is not None:
            evidence.append(f"Bank credit = {format_currency(bank_amt)}")

        # Check if adjustments explain the gap
        if adjustments:
            for adj in adjustments:
                evidence.append(f"Adjustment ({adj.get('adjustment_type')}): {format_currency(adj.get('amount'))} - {adj.get('reason')}")

        if not ledger:
            decision = "HUMAN_REVIEW"
            reason = f"Payment captured ({format_currency(payment_amt)}) but missing corresponding ledger entry in ERP."
            action = "Post missing ledger entry in ERP."
        elif not banks:
            decision = "HUMAN_REVIEW"
            reason = f"Expected settlement {format_currency(expected_net)} missing from bank statements."
            action = "Contact acquiring bank to trace settlement batch."
        elif len(banks) > 1:
            decision = "HUMAN_REVIEW"
            reason = f"Multiple ({len(banks)}) bank settlement records found for single transaction."
            action = "Review bank statement for potential duplicate credit."
        elif expected_net_dec is not None and bank_dec is not None and (expected_net_dec - total_adj_dec) == bank_dec and total_adj_dec > 0:
            # Deterministically explained by adjustments!
            decision = "AUTO_RESOLVED"
            resolution_type = "ADJUSTMENT_EXPLAINED"
            resolved_diff = float(total_adj_dec)
            confidence = 1.0
            reason = f"Bank credit ({format_currency(bank_amt)}) equals expected settlement ({format_currency(expected_net)}) minus documented adjustment of {format_currency(total_adj_amt)}."
            action = "No action needed; discrepancy fully accounted for by adjustment record."
            evidence.append(f"Calculation: {format_currency(expected_net)} - {format_currency(total_adj_amt)} = {format_currency(bank_amt)}")
        elif payment_dec is not None and gross_dec is not None and (payment_dec - total_adj_dec) == gross_dec and total_adj_dec > 0:
            decision = "AUTO_RESOLVED"
            resolution_type = "ADJUSTMENT_EXPLAINED"
            resolved_diff = float(total_adj_dec)
            confidence = 1.0
            reason = f"Gross amount discrepancy of {format_currency(total_adj_amt)} is explicitly accounted for by adjustment reference."
            action = "No action needed; gross amount adjustment verified."
        elif expected_net_dec is not None and bank_dec is not None:
            diff_dec = expected_net_dec - bank_dec
            diff = safe_numeric(diff_dec)
            if adjustments and total_adj_dec != diff_dec:
                reason = f"Bank credit is {format_currency(diff)} lower than expected, but documented adjustments total {format_currency(total_adj_amt)} (mismatch of {format_currency(safe_numeric(diff_dec - total_adj_dec))})."
                action = "Review bank fee schedule and settlement file."
            else:
                reason = f"Bank credit of {format_currency(bank_amt)} is {format_currency(diff)} lower than expected settlement ({format_currency(expected_net)}) with no adjustment record."
                action = "Review bank settlement details."
        else:
            reason = "Discrepancy detected requiring manual review."
            action = "Manual review required."

        resp_payload = {
            "transaction_id": txn_id,
            "decision": decision,
            "exception_type": "INVESTIGATED_EXCEPTION",
            "resolution_type": resolution_type,
            "resolved_difference": resolved_diff,
            "reason": reason,
            "evidence": evidence,
            "confidence": confidence,
            "recommended_action": action
        }

        class FinalDemoMessage:
            content = json.dumps(resp_payload)
            tool_calls = None

        class FinalDemoChoice:
            message = FinalDemoMessage()

        class FinalDemoResponse:
            choices = [FinalDemoChoice()]

        return FinalDemoResponse()


def validate_model_not_key(provider: str, model_str: str) -> None:
    """Checks if a model string accidentally contains a secret key pattern."""
    if not model_str:
        return
    import re
    # Patterns matching secret keys
    if re.search(r"(sk-or-v1-[a-zA-Z0-9]{10,}|sk-[a-zA-Z0-9_-]{20,}|AIzaSy[a-zA-Z0-9_-]{20,}|AQ\.[a-zA-Z0-9_-]{20,}|xai-[a-zA-Z0-9]{20,})", model_str):
        raise ValueError(
            f"ConfigurationError: {provider.upper()}_MODEL appears to contain a credential rather than a model ID."
        )


def create_llm_client(
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> Any:
    """Standalone provider client factory helper."""
    return LLMClient(provider=provider, api_key=api_key, model=model)


class LLMClient:
    """
    Factory router for creating the appropriate LLM client instance based on
    provider configuration and available API credentials.
    """

    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: str = "auto",
        max_tokens: Optional[int] = None,
    ) -> Any:
        """Interface method declaration for type hinting and mocking."""
        pass

    def __new__(
        cls,
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Any:
        selected_provider = (provider or os.getenv("LLM_PROVIDER") or "").strip().lower()
        env_or_key = (api_key or os.getenv("OPENROUTER_API_KEY") or "").strip()
        env_gem_key = (api_key or os.getenv("GEMINI_API_KEY") or "").strip()

        if not selected_provider:
            if env_or_key and os.getenv("OPENROUTER_MODEL"):
                selected_provider = "openrouter"
            elif env_gem_key:
                selected_provider = "gemini"
            else:
                selected_provider = "demo"

        if selected_provider == "openrouter":
            or_key = (api_key or env_or_key).strip() if (api_key or env_or_key) else ""
            if not or_key:
                raise ValueError(
                    "OPENROUTER_API_KEY is missing. "
                    "Set OPENROUTER_API_KEY in environment or configure provider=demo for Demo Mode."
                )
            or_model = (model or os.getenv("OPENROUTER_MODEL") or "").strip()
            if not or_model:
                raise ValueError(
                    "OPENROUTER_MODEL is missing. "
                    "Set OPENROUTER_MODEL (e.g. OPENROUTER_MODEL=meta-llama/llama-3.3-70b-instruct) in environment."
                )
            validate_model_not_key("openrouter", or_model)

            from src.agent.openrouter_client import OpenRouterLLMClient
            client = OpenRouterLLMClient(api_key=or_key, model=or_model)
            client.provider_name = "openrouter"
            return client

        elif selected_provider == "gemini":
            gem_key = (api_key or env_gem_key).strip() if (api_key or env_gem_key) else ""
            if not gem_key:
                raise ValueError(
                    "GEMINI_API_KEY is missing. "
                    "Set GEMINI_API_KEY in environment or configure provider=demo for Demo Mode."
                )
            gem_model = (model or os.getenv("GEMINI_MODEL") or "gemini-3.6-flash").strip()
            if not gem_model:
                raise ValueError("GEMINI_MODEL is missing.")
            validate_model_not_key("gemini", gem_model)

            from src.agent.gemini_client import GeminiLLMClient
            client = GeminiLLMClient(api_key=gem_key, model=gem_model)
            client.provider_name = "gemini"
            return client

        elif selected_provider == "agentrouter":
            # AgentRouter is an OpenAI-compatible gateway (https://agentrouter.org/v1).
            # It uses the same wire format as OpenRouter, so we reuse OpenRouterLLMClient
            # but point base_url at AgentRouter and pull agentrouter-specific credentials.
            ar_key = (
                api_key
                or os.getenv("AGENTROUTER_API_KEY")
                or os.getenv("INVESTIGATOR_API_KEY")
                or os.getenv("VERIFIER_API_KEY")
                or ""
            ).strip()
            if not ar_key:
                raise ValueError(
                    "AgentRouter API key is missing. "
                    "Set AGENTROUTER_API_KEY (or INVESTIGATOR_API_KEY / VERIFIER_API_KEY) "
                    "in environment or configure provider=demo for Demo Mode."
                )
            ar_model = (model or os.getenv("AGENTROUTER_MODEL") or "").strip()
            if not ar_model:
                raise ValueError(
                    "AgentRouter model is missing. "
                    "Pass a model or set AGENTROUTER_MODEL (e.g. AGENTROUTER_MODEL=claude-opus-4-8)."
                )
            validate_model_not_key("agentrouter", ar_model)

            ar_base = (os.getenv("AGENTROUTER_BASE_URL") or "https://agentrouter.org/v1").strip()

            from src.agent.openrouter_client import OpenRouterLLMClient
            client = OpenRouterLLMClient(api_key=ar_key, model=ar_model, base_url=ar_base)
            client.provider = "agentrouter"
            client.provider_name = "agentrouter"
            return client

        elif selected_provider == "demo":
            client = DemoLLMClient(model=model or "demo")
            client.provider_name = "demo"
            return client

        else:
            raise ValueError(
                f"Unsupported LLM_PROVIDER '{selected_provider}'. Valid options are 'demo', 'gemini', 'openrouter', or 'agentrouter'."
            )




class EvidenceState:
    """Tracks financial evidence discovered during an exception investigation."""

    def __init__(self, transaction_id: str):
        self.transaction_id = transaction_id
        self.payment: Optional[Dict[str, Any]] = None
        self.ledger: Optional[Dict[str, Any]] = None
        self.bank_records: List[Dict[str, Any]] = []
        self.adjustments: List[Dict[str, Any]] = []
        self.expected_settlement: Optional[Dict[str, Any]] = None
        self.adjusted_expected_settlement: Optional[Dict[str, Any]] = None
        self.duplicate_check: Optional[Dict[str, Any]] = None
        self.discrepancy_verification: Optional[Dict[str, Any]] = None
        self.record_presence: Optional[Dict[str, Any]] = None
        self.date_consistency: Optional[Dict[str, Any]] = None

    def update(self, tool_name: str, result: Any) -> None:
        if not isinstance(result, dict) or "error" in result:
            return

        if tool_name == "get_transaction":
            if result.get("payment"):
                self.payment = result.get("payment")
            if result.get("ledger"):
                self.ledger = result.get("ledger")
            if result.get("bank_records"):
                self.bank_records = result.get("bank_records", [])
            if result.get("adjustments"):
                self.adjustments = result.get("adjustments", [])

        elif tool_name == "get_payment_record":
            if result.get("transaction_id") or "amount" in result:
                self.payment = result

        elif tool_name == "get_ledger_record":
            if result.get("transaction_id") or "gross_amount" in result:
                self.ledger = result

        elif tool_name == "get_bank_records":
            self.bank_records = result.get("bank_records", [])

        elif tool_name == "get_adjustments":
            self.adjustments = result.get("adjustments", [])

        elif tool_name == "calculate_expected_settlement":
            self.expected_settlement = result

        elif tool_name == "calculate_adjusted_expected_settlement":
            self.adjusted_expected_settlement = result

        elif tool_name == "check_for_duplicates":
            self.duplicate_check = result

        elif tool_name == "verify_discrepancy":
            self.discrepancy_verification = result

        elif tool_name == "check_record_presence":
            self.record_presence = result

        elif tool_name == "check_date_consistency":
            self.date_consistency = result


#: Exception types an adjustment record can legitimately explain in full.
#:
#: The proofs below are amount-reconciliation identities, so they only mean
#: anything for a discrepancy in an amount. ``exception_type`` used to be
#: accepted and ignored, which let a coincidental adjustment close out an
#: exception it had no bearing on -- most seriously MISSING_BANK_RECORD, where
#: the money never arrived at all but a matching adjustment amount produced a
#: confidence-1.0 AUTO_RESOLVED. A missing or duplicated record is a presence
#: problem, not an arithmetic one, and must reach a human.
_ADJUSTMENT_EXPLAINABLE_EXCEPTIONS = frozenset({
    "BANK_AMOUNT_MISMATCH",
    "GROSS_AMOUNT_MISMATCH",
    "LEDGER_CALCULATION_ERROR",
})

#: Which reconciliation identity actually proves each exception type.
#:
#: Two independent identities are available as proof. The *bank* identity
#: (``expected_net -/+ adjustments == bank_credited``, reported by
#: ``verify_discrepancy`` as ``BANK_ADJUSTMENT``) and the *gross* identity
#: (``ledger_gross -/+ adjustments == payment``, reported as ``GROSS_ADJUSTMENT``)
#: are claims about different amounts, so the one that balanced has to be the one
#: the exception was raised on. Each is tested in both directions, since an
#: adjustment record states a magnitude and not a sign.
#:
#: Accepting either for either was unsound in both directions. A
#: GROSS_AMOUNT_MISMATCH with a 2,000 payment-vs-gross gap was auto-resolved at
#: confidence 1.0 by a 500 adjustment purely because the bank leg happened to
#: balance -- 1,500 left unexplained, and an audit trail quoting a bank figure the
#: exception had nothing to do with. Symmetrically, the gross identity needs no
#: bank record at all, so it could close a BANK_AMOUNT_MISMATCH while the bank
#: shortfall stayed entirely unaccounted for.
#:
#: LEDGER_CALCULATION_ERROR is an internal gross/fee/net arithmetic fault that
#: neither identity settles on its own, so either is accepted as corroboration.
_MATCH_TYPES_FOR_EXCEPTION = {
    "BANK_AMOUNT_MISMATCH": ("BANK_ADJUSTMENT",),
    "GROSS_AMOUNT_MISMATCH": ("GROSS_ADJUSTMENT",),
    "LEDGER_CALCULATION_ERROR": ("BANK_ADJUSTMENT", "GROSS_ADJUSTMENT"),
}


def has_sufficient_resolution_evidence(
    state: EvidenceState,
    exception_type: str,
) -> tuple[bool, Optional[Dict[str, Any]]]:
    """
    Deterministically evaluates whether the collected evidence objectively proves
    an AUTO_RESOLVED decision without needing further tool calls.

    Only amount-mismatch exceptions are eligible; see
    ``_ADJUSTMENT_EXPLAINABLE_EXCEPTIONS``. The identity that balanced must also
    be one that bears on the exception; see ``_MATCH_TYPES_FOR_EXCEPTION``.
    """
    normalized_exception = (exception_type or "").strip().upper()
    if normalized_exception not in _ADJUSTMENT_EXPLAINABLE_EXCEPTIONS:
        return False, None

    admissible = _MATCH_TYPES_FOR_EXCEPTION.get(normalized_exception, ())

    # Fast path: deterministic discrepancy verification tool proves explanation.
    if state.discrepancy_verification and state.discrepancy_verification.get("discrepancy_fully_explained"):
        match_type = state.discrepancy_verification.get("match_type")
        # ``verify_discrepancy`` always reports match_type. When the key is absent
        # entirely the direction cannot be checked, so the proof is taken at face
        # value rather than discarded -- the guard exists to reject a proof about
        # the *wrong* figure, not to reject one that did not state its figure.
        if match_type is None or match_type in admissible:
            return True, {
                "resolution_type": "ADJUSTMENT_EXPLAINED",
                "resolved_difference": state.discrepancy_verification.get("resolved_difference"),
                "reason": state.discrepancy_verification.get("explanation"),
                "calculation": state.discrepancy_verification.get("explanation"),
            }

    # 1. Contradictory evidence check: multiple bank records require HUMAN_REVIEW
    if state.duplicate_check and state.duplicate_check.get("is_duplicate"):
        return False, None
    if len(state.bank_records) > 1:
        return False, None

    # 2. Adjustments check
    adjustments = state.adjustments
    total_adj_dec = sum((safe_decimal(a.get("amount")) or Decimal(0)) for a in adjustments if a.get("amount") is not None)
    if total_adj_dec <= 0:
        return False, None
    total_adj_amt = safe_numeric(total_adj_dec) or 0

    # 3. Bank Amount Mismatch / Adjusted Settlement Resolution
    #
    # Only for exceptions the bank identity bears on: it says the bank credit
    # agrees with the ledger's own gross/fee less documented adjustments, which is
    # no statement at all about a payment-vs-gross gap.
    bank_dec = None
    if state.bank_records and len(state.bank_records) == 1:
        bank_dec = safe_decimal(state.bank_records[0].get("credited_amount"))
    bank_amt = safe_numeric(bank_dec)

    if "BANK_ADJUSTMENT" in admissible:
        # An adjustment amount is a magnitude, not a signed direction: a TDS
        # deduction lowers the settlement, a rebate credit raises it, and both are
        # filed as a positive amount. Each identity below is therefore tested in
        # both directions, and the direction that lands exactly on the bank figure
        # is the one recorded in the audit trail. Neither matching is still an
        # unexplained discrepancy.

        # If calculate_adjusted_expected_settlement was explicitly called
        if state.adjusted_expected_settlement:
            adj_net_dec = safe_decimal(state.adjusted_expected_settlement.get("adjusted_expected_net"))
            base_net_dec = safe_decimal(state.adjusted_expected_settlement.get("base_expected_net"))
            tool_adj_dec = safe_decimal(state.adjusted_expected_settlement.get("total_adjustments"))
            # The tool subtracts, so the additive candidate is rebuilt from the
            # unadjusted base it also reports.
            additive_net_dec = (
                base_net_dec + tool_adj_dec
                if base_net_dec is not None and tool_adj_dec is not None
                else None
            )
            if bank_dec is not None and adj_net_dec is not None and adj_net_dec == bank_dec:
                return True, {
                    "resolution_type": "ADJUSTMENT_EXPLAINED",
                    "resolved_difference": float(total_adj_dec),
                    "reason": f"Bank credit ({format_currency(bank_amt)}) equals expected settlement minus documented adjustment of {format_currency(total_adj_amt)} (adjustment applied subtractively).",
                    "calculation": state.adjusted_expected_settlement.get("calculation", f"Adjusted settlement = {format_currency(bank_amt)}"),
                }
            if bank_dec is not None and additive_net_dec is not None and additive_net_dec == bank_dec:
                return True, {
                    "resolution_type": "ADJUSTMENT_EXPLAINED",
                    "resolved_difference": float(total_adj_dec),
                    "reason": f"Bank credit ({format_currency(bank_amt)}) equals expected settlement plus documented adjustment of {format_currency(total_adj_amt)} (adjustment applied additively; the subtractive direction does not match).",
                    "calculation": f"{format_currency(safe_numeric(base_net_dec))} + {format_currency(total_adj_amt)} = {format_currency(bank_amt)}",
                }

        # If ledger and bank amounts are known
        expected_net_dec = None
        if state.expected_settlement:
            expected_net_dec = safe_decimal(state.expected_settlement.get("expected_net"))
        elif state.ledger:
            gross_dec = safe_decimal(state.ledger.get("gross_amount"))
            fee_dec = safe_decimal(state.ledger.get("fee")) or Decimal(0)
            if gross_dec is not None:
                expected_net_dec = gross_dec - fee_dec

        expected_net = safe_numeric(expected_net_dec)
        if expected_net_dec is not None and bank_dec is not None:
            if (expected_net_dec - total_adj_dec) == bank_dec:
                return True, {
                    "resolution_type": "ADJUSTMENT_EXPLAINED",
                    "resolved_difference": float(total_adj_dec),
                    "reason": f"Bank credit ({format_currency(bank_amt)}) equals expected settlement ({format_currency(expected_net)}) minus documented adjustment of {format_currency(total_adj_amt)} (adjustment applied subtractively).",
                    "calculation": f"{format_currency(expected_net)} - {format_currency(total_adj_amt)} = {format_currency(bank_amt)}",
                }
            if (expected_net_dec + total_adj_dec) == bank_dec:
                return True, {
                    "resolution_type": "ADJUSTMENT_EXPLAINED",
                    "resolved_difference": float(total_adj_dec),
                    "reason": f"Bank credit ({format_currency(bank_amt)}) equals expected settlement ({format_currency(expected_net)}) plus documented adjustment of {format_currency(total_adj_amt)} (adjustment applied additively; the subtractive direction does not match).",
                    "calculation": f"{format_currency(expected_net)} + {format_currency(total_adj_amt)} = {format_currency(bank_amt)}",
                }

    # 4. Gross Amount Mismatch Resolution
    #
    # Gated for the mirror-image reason: this identity needs no bank record, so on
    # its own it cannot account for a bank shortfall.
    payment_dec = safe_decimal(state.payment.get("amount")) if state.payment else None
    gross_dec = safe_decimal(state.ledger.get("gross_amount")) if state.ledger else None
    payment_amt = safe_numeric(payment_dec)
    gross_amt = safe_numeric(gross_dec)
    if "GROSS_ADJUSTMENT" in admissible and payment_dec is not None and gross_dec is not None:
        # Which direction holds matters for the audit trail: a single message was
        # previously emitted for both, so half of these resolutions documented a
        # calculation that was not the one that actually balanced.
        if (gross_dec - total_adj_dec) == payment_dec:
            direction = "subtractively"
            calculation = (
                f"Ledger Gross {format_currency(gross_amt)} - adjustment "
                f"{format_currency(total_adj_amt)} = Payment {format_currency(payment_amt)}"
            )
        elif (gross_dec + total_adj_dec) == payment_dec:
            direction = "additively"
            calculation = (
                f"Ledger Gross {format_currency(gross_amt)} + adjustment "
                f"{format_currency(total_adj_amt)} = Payment {format_currency(payment_amt)}"
            )
        else:
            direction = None
            calculation = None

        if calculation:
            return True, {
                "resolution_type": "ADJUSTMENT_EXPLAINED",
                "resolved_difference": float(total_adj_dec),
                "reason": f"Gross amount discrepancy of {format_currency(total_adj_amt)} is explicitly accounted for by adjustment reference (adjustment applied {direction}).",
                "calculation": calculation,
            }

    return False, None


def build_proven_adjustment_resolution(
    txn_id: str,
    exception_type: str,
    evidence: List[str],
    resolution_data: Dict[str, Any],
) -> AgentDecision:
    """Constructs a deterministic AUTO_RESOLVED decision when proof conditions are strictly met."""
    calc = resolution_data.get("calculation")
    if calc and f"Calculation: {calc}" not in evidence:
        evidence.append(f"Calculation: {calc}")

    return AgentDecision(
        transaction_id=txn_id,
        decision="AUTO_RESOLVED",
        exception_type=exception_type,
        resolution_type="ADJUSTMENT_EXPLAINED",
        resolved_difference=resolution_data.get("resolved_difference"),
        reason=resolution_data.get("reason", "A documented transaction-specific adjustment exactly explains the settlement discrepancy."),
        evidence=evidence or [f"Phase 1 exception: {exception_type}"],
        confidence=1.0,
        recommended_action="No action needed; discrepancy fully accounted for by adjustment record.",
    )


class AgentController:
    """Orchestrates exception investigation using the LLM and deterministic tools."""

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

    def investigate_exception(
        self, exception_record: Dict[str, Any]
    ) -> tuple[AgentDecision, InvestigationLog]:
        """Runs a full investigation for a single Phase 1 exception."""
        txn_id = exception_record.get("transaction_id", "UNKNOWN")
        exception_type = exception_record.get("reason", "UNKNOWN")
        timestamp = datetime.now(timezone.utc)

        tools_used: List[str] = []
        evidence: List[str] = []
        tool_traces: List[ToolCallTrace] = []
        tool_call_count = 0

        evidence_state = EvidenceState(txn_id)
        executed_tools: Dict[str, Any] = {}

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_investigation_prompt(exception_record)},
        ]

        tool_definitions = self.toolkit.get_tool_definitions()

        while tool_call_count < MAX_TOOL_CALLS:
            try:
                response = self.llm.chat(messages=messages, tools=tool_definitions)
            except Exception as e:
                decision = AgentDecision(
                    transaction_id=txn_id,
                    decision="NOT_EVALUATED",
                    exception_type=exception_type,
                    resolution_type="NONE",
                    reason=f"Provider request failed: {str(e)[:200]}",
                    evidence=evidence or [f"Phase 1 exception: {exception_type}"],
                    confidence=0.0,
                    recommended_action="Investigation not evaluated due to provider API failure.",
                )
                log = InvestigationLog(
                    transaction_id=txn_id,
                    initial_exception=exception_type,
                    tools_used=tools_used,
                    evidence=evidence or [f"Phase 1 exception: {exception_type}"],
                    decision=decision.decision,
                    resolution_type=decision.resolution_type,
                    reason=decision.reason,
                    confidence=decision.confidence,
                    recommended_action=decision.recommended_action,
                    timestamp=timestamp,
                    tool_call_count=tool_call_count,
                    tool_traces=tool_traces,
                )
                return decision, log

            choice = response.choices[0]
            message = choice.message

            messages.append({
                "role": "assistant",
                "content": message.content,
                "raw_content": getattr(message, "raw_content", None),
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        "thought_signature": getattr(tc, "thought_signature", None),
                    }
                    for tc in (message.tool_calls or [])
                ],
            })

            if not message.tool_calls:
                content = message.content or ""
                decision = self._parse_decision(content, txn_id, exception_type, evidence)
                log = InvestigationLog(
                    transaction_id=txn_id,
                    initial_exception=exception_type,
                    tools_used=tools_used,
                    evidence=evidence or [f"Phase 1 exception: {exception_type}"],
                    decision=decision.decision,
                    resolution_type=decision.resolution_type,
                    resolved_difference=decision.resolved_difference,
                    reason=decision.reason,
                    confidence=decision.confidence,
                    recommended_action=decision.recommended_action,
                    timestamp=timestamp,
                    tool_call_count=tool_call_count,
                    tool_traces=tool_traces,
                )
                return decision, log

            for tool_call in message.tool_calls:
                tool_call_count += 1
                tool_name = tool_call.function.name
                tools_used.append(tool_name)

                try:
                    arguments = json.loads(tool_call.function.arguments) if isinstance(tool_call.function.arguments, str) else tool_call.function.arguments
                except Exception:
                    arguments = {}

                # Tool-call deduplication check
                args_norm = json.dumps(arguments, sort_keys=True) if isinstance(arguments, dict) else str(arguments)
                call_key = f"{tool_name}:{args_norm}"

                if call_key in executed_tools:
                    result = executed_tools[call_key]
                    duplicate_prevented = True
                else:
                    try:
                        result = self.toolkit.dispatch(tool_name, arguments)
                    except Exception as e:
                        result = {"error": f"Tool execution failed: {str(e)}"}
                    executed_tools[call_key] = result
                    duplicate_prevented = False

                # Update evidence state
                evidence_state.update(tool_name, result)
                self._extract_evidence(tool_name, result, evidence)

                # Check if deterministic resolution conditions are satisfied
                is_sufficient, res_data = has_sufficient_resolution_evidence(evidence_state, exception_type)

                # Create non-sensitive tool trace
                summary = self._summarize_tool_result(tool_name, result)
                trace = ToolCallTrace(
                    transaction_id=txn_id,
                    tool_name=tool_name,
                    tool_arguments=arguments if isinstance(arguments, dict) else {},
                    tool_result_summary=summary,
                    tool_call_index=tool_call_count,
                    timestamp=datetime.now(timezone.utc),
                    evidence_sufficient=is_sufficient,
                    duplicate_call_prevented=duplicate_prevented,
                    early_stop_reason="Sufficient deterministic evidence established." if is_sufficient else None,
                    deterministic_resolution="AUTO_RESOLVED" if is_sufficient else None,
                )
                tool_traces.append(trace)

                # If sufficient evidence has been proven, terminate early with deterministic resolution
                if is_sufficient and res_data:
                    decision = build_proven_adjustment_resolution(txn_id, exception_type, evidence, res_data)
                    log = InvestigationLog(
                        transaction_id=txn_id,
                        initial_exception=exception_type,
                        tools_used=tools_used,
                        evidence=evidence or [f"Phase 1 exception: {exception_type}"],
                        decision=decision.decision,
                        resolution_type=decision.resolution_type,
                        resolved_difference=decision.resolved_difference,
                        reason=decision.reason,
                        confidence=decision.confidence,
                        recommended_action=decision.recommended_action,
                        timestamp=timestamp,
                        tool_call_count=tool_call_count,
                        tool_traces=tool_traces,
                    )
                    return decision, log

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result, default=str),
                })

                if tool_call_count >= MAX_TOOL_CALLS:
                    break

        return self._escalate_on_limit(
            txn_id=txn_id,
            exception_type=exception_type,
            evidence=evidence,
            tools_used=tools_used,
            timestamp=timestamp,
            tool_call_count=tool_call_count,
            tool_traces=tool_traces,
            evidence_state=evidence_state,
        )

    def _parse_decision(
        self,
        content: str,
        txn_id: str,
        exception_type: str,
        evidence: List[str],
    ) -> AgentDecision:
        """Parses and validates the LLM's final JSON response into an AgentDecision."""
        try:
            data = repair_and_parse_json(content)
            if not isinstance(data, dict):
                raise ValueError("Parsed decision content is not a dictionary")
            data.setdefault("transaction_id", txn_id)
            data.setdefault("exception_type", exception_type)
            data.setdefault("evidence", evidence or [f"Phase 1 exception: {exception_type}"])
            # Ensure confidence is clamped between 0.0 and 1.0
            if "confidence" in data and isinstance(data["confidence"], (int, float)):
                data["confidence"] = max(0.0, min(1.0, float(data["confidence"])))
            return AgentDecision(**data)


        except Exception as e:
            return AgentDecision(
                transaction_id=txn_id,
                decision="HUMAN_REVIEW",
                exception_type=exception_type,
                resolution_type="NONE",
                reason=f"Agent output parse error: {str(e)[:200]}",
                evidence=evidence or [f"Phase 1 exception: {exception_type}"],
                confidence=0.0,
                recommended_action="Manual review required due to agent output error.",
            )

    def _escalate_on_limit(
        self,
        txn_id: str,
        exception_type: str,
        evidence: List[str],
        tools_used: List[str],
        timestamp: datetime,
        tool_call_count: int,
        tool_traces: Optional[List[ToolCallTrace]] = None,
        evidence_state: Optional[EvidenceState] = None,
    ) -> tuple[AgentDecision, InvestigationLog]:
        """Handles decision when MAX_TOOL_CALLS limit is reached."""
        # If evidence was already sufficient, resolve deterministically rather than escalating
        if evidence_state:
            is_sufficient, res_data = has_sufficient_resolution_evidence(evidence_state, exception_type)
            if is_sufficient and res_data:
                decision = build_proven_adjustment_resolution(txn_id, exception_type, evidence, res_data)
                log = InvestigationLog(
                    transaction_id=txn_id,
                    initial_exception=exception_type,
                    tools_used=tools_used,
                    evidence=evidence or [f"Phase 1 exception: {exception_type}"],
                    decision=decision.decision,
                    resolution_type=decision.resolution_type,
                    resolved_difference=decision.resolved_difference,
                    reason=decision.reason,
                    confidence=decision.confidence,
                    recommended_action=decision.recommended_action,
                    timestamp=timestamp,
                    tool_call_count=tool_call_count,
                    tool_traces=tool_traces or [],
                )
                return decision, log

        decision = AgentDecision(
            transaction_id=txn_id,
            decision="HUMAN_REVIEW",
            exception_type=exception_type,
            resolution_type="NONE",
            reason=f"Investigation reached the maximum tool-call limit (MAX_TOOL_CALLS = {MAX_TOOL_CALLS}) without sufficient evidence.",
            evidence=evidence or [f"Phase 1 exception: {exception_type}"],
            confidence=0.5,
            recommended_action="Manual review required — agent investigation was inconclusive.",
        )

        log = InvestigationLog(
            transaction_id=txn_id,
            initial_exception=exception_type,
            tools_used=tools_used,
            evidence=evidence or [f"Phase 1 exception: {exception_type}"],
            decision=decision.decision,
            resolution_type=decision.resolution_type,
            reason=decision.reason,
            confidence=decision.confidence,
            recommended_action=decision.recommended_action,
            timestamp=timestamp,
            tool_call_count=tool_call_count,
            tool_traces=tool_traces or [],
        )
        return decision, log


    @staticmethod
    def _summarize_tool_result(tool_name: str, result: Any) -> str:
        """Generates a concise non-sensitive summary of a tool execution result."""
        if not isinstance(result, dict):
            return str(result)[:200]
        if "error" in result:
            return f"Error: {result['error']}"

        if tool_name == "get_transaction":
            p = result.get("payment")
            l = result.get("ledger")
            b = result.get("bank_records", [])
            a = result.get("adjustments", [])
            return (
                f"Payment: {'found' if p else 'none'}, "
                f"Ledger: {'found' if l else 'none'}, "
                f"Bank records: {len(b)}, "
                f"Adjustments: {len(a)}"
            )

        elif tool_name == "get_payment_record":
            amt = result.get("amount")
            return f"Payment amount: {format_currency(amt)} (status: {result.get('status')})" if amt is not None else "No record"

        elif tool_name == "get_ledger_record":
            gross = result.get("gross_amount")
            fee = result.get("fee", 0)
            net = result.get("net_amount", 0)
            return f"Ledger gross: {format_currency(gross)}, fee: {format_currency(fee)}, net: {format_currency(net)}" if gross is not None else "No record"

        elif tool_name == "get_bank_records":
            count = result.get("count", 0)
            records = result.get("bank_records", [])
            amounts = [f"{format_currency(r.get('credited_amount', 0))}" for r in records]
            return f"{count} bank record(s): {', '.join(amounts)}" if count > 0 else "0 bank records"

        elif tool_name == "get_adjustments":
            count = result.get("count", 0)
            records = result.get("adjustments", [])
            if count == 0:
                return "0 adjustments found"
            adjs = [f"{r.get('adjustment_type')}: {format_currency(r.get('amount', 0))} ({r.get('reason', '')})" for r in records]
            return f"{count} adjustment(s): {'; '.join(adjs)}"

        elif tool_name == "calculate_expected_settlement":
            return f"Expected net: {format_currency(result.get('expected_net', 0))} ({result.get('calculation', '')})"

        elif tool_name == "calculate_adjusted_expected_settlement":
            return f"Adjusted expected net: {format_currency(result.get('adjusted_expected_net', 0))} ({result.get('calculation', '')})"

        elif tool_name == "check_for_duplicates":
            return f"Duplicate count: {result.get('duplicate_count', 0)}, is_duplicate: {result.get('is_duplicate', False)}"

        return str(result)[:200]

    @staticmethod
    def _extract_evidence(tool_name: str, result: Any, evidence: List[str]) -> None:
        """Extracts concise evidence facts from tool execution results."""
        if not isinstance(result, dict) or "error" in result:
            return

        if tool_name == "get_transaction":
            p = result.get("payment")
            if p and p.get("amount") is not None:
                evidence.append(f"Payment captured = {format_currency(p.get('amount'))}")
            l = result.get("ledger")
            if l:
                gross = l.get("gross_amount")
                fee = l.get("fee")
                if gross is not None and fee is not None:
                    evidence.append(f"Ledger gross = {format_currency(gross)}, fee = {format_currency(fee)}")
            for b in result.get("bank_records", []):
                amt = b.get("credited_amount")
                if amt is not None:
                    evidence.append(f"Bank credit ({b.get('bank_reference')}) = {format_currency(amt)}")
            for a in result.get("adjustments", []):
                amt = a.get("amount")
                if amt is not None:
                    evidence.append(f"Adjustment ({a.get('adjustment_type')}): {format_currency(amt)} ({a.get('reason', '')})")

        elif tool_name == "get_payment_record":
            amt = result.get("amount")
            if amt is not None:
                evidence.append(f"Payment amount = {format_currency(amt)}")

        elif tool_name == "get_ledger_record":
            gross = result.get("gross_amount")
            fee = result.get("fee")
            if gross is not None:
                evidence.append(f"Ledger gross = {format_currency(gross)}")
            if fee is not None:
                evidence.append(f"Ledger fee = {format_currency(fee)}")

        elif tool_name == "get_adjustments":
            count = result.get("count", 0)
            records = result.get("adjustments", [])
            evidence.append(f"Adjustment records found: {count}")
            for r in records:
                typ = r.get("adjustment_type")
                amt = r.get("amount")
                if amt is not None:
                    evidence.append(f"  Adjustment ({typ}): {format_currency(amt)} ({r.get('reason')})")

        elif tool_name in ["calculate_expected_settlement", "calculate_adjusted_expected_settlement"]:
            calc = result.get("calculation")
            if calc:
                evidence.append(f"Settlement calculation: {calc}")

        elif tool_name == "get_bank_records":
            count = result.get("count", 0)
            records = result.get("bank_records", [])
            evidence.append(f"Bank records found: {count}")
            for r in records:
                amt = r.get("credited_amount")
                if amt is not None:
                    evidence.append(f"  {r.get('bank_reference')}: credited {format_currency(amt)}")

        elif tool_name == "check_for_duplicates":
            count = result.get("duplicate_count", 0)
            evidence.append(f"Duplicate check: {count} bank record(s) found")



def create_agent_controller(
    payments: List[Dict[str, Any]],
    ledger_records: List[Dict[str, Any]],
    bank_records: List[Dict[str, Any]],
    adjustments: Optional[List[Dict[str, Any]]] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    tracer: Optional[Any] = None,
) -> AgentController:
    """Factory function for creating an AgentController."""
    toolkit = FinancialToolkit(payments, ledger_records, bank_records, adjustments)
    llm_client = LLMClient(api_key=api_key, model=model)
    return AgentController(toolkit=toolkit, llm_client=llm_client, tracer=tracer)


def create_multi_agent_controller(
    payments: List[Dict[str, Any]],
    ledger_records: List[Dict[str, Any]],
    bank_records: List[Dict[str, Any]],
    adjustments: Optional[List[Dict[str, Any]]] = None,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    investigator_model: Optional[str] = None,
    verifier_model: Optional[str] = None,
    tracer: Optional[Any] = None,
) -> Any:
    """Factory function for creating a MultiAgentOrchestrator."""
    from src.agent.multi_agent.orchestrator import MultiAgentOrchestrator

    toolkit = FinancialToolkit(payments, ledger_records, bank_records, adjustments)
    return MultiAgentOrchestrator(
        toolkit=toolkit,
        provider=provider,
        api_key=api_key,
        investigator_model=investigator_model,
        verifier_model=verifier_model,
        tracer=tracer,
    )


