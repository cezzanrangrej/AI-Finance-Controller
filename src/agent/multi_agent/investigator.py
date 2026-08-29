"""
Investigator Agent — responsible for investigating financial exceptions, selecting
read-only tools, gathering structured evidence, and producing an InvestigationProposal.
"""

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from src.agent.controller import EvidenceState, LLMClient, has_sufficient_resolution_evidence
from src.agent.prompts import INVESTIGATOR_SYSTEM_PROMPT, build_investigator_prompt
from src.agent.schemas import InvestigationProposal, ToolCallTrace
from src.agent.tools import FinancialToolkit
from src.agent.trace import AgentTracer, default_tracer
from src.utils.formatters import format_currency


class InvestigatorAgent:
    """
    Investigates financial exceptions using read-only financial tools,
    enforcing safety limits and tool deduplication, and producing structured proposals.
    """

    def __init__(
        self,
        toolkit: FinancialToolkit,
        llm_client: LLMClient,
        max_tool_calls: int = 5,
        tracer: Optional[AgentTracer] = None,
    ) -> None:
        self.toolkit = toolkit
        self.llm = llm_client
        self.max_tool_calls = max_tool_calls
        self.tracer = tracer or default_tracer

    def investigate(
        self, exception_record: Dict[str, Any]
    ) -> Tuple[InvestigationProposal, List[str], List[ToolCallTrace], EvidenceState, int]:
        """
        Executes multi-turn tool calling to collect evidence and propose a resolution.

        Returns:
            Tuple of (proposal, evidence_strings, tool_traces, evidence_state, tool_call_count)
        """
        txn_id = exception_record.get("transaction_id", "UNKNOWN")
        exception_type = exception_record.get("reason", "UNKNOWN")

        self.last_successful_calls = 0
        tools_used: List[str] = []
        evidence: List[str] = []
        tool_traces: List[ToolCallTrace] = []
        tool_call_count = 0

        evidence_state = EvidenceState(txn_id)
        executed_tools: Dict[str, Any] = {}

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": INVESTIGATOR_SYSTEM_PROMPT},
            {"role": "user", "content": build_investigator_prompt(exception_record)},
        ]

        tool_definitions = self.toolkit.get_tool_definitions()
        prov_name = getattr(self.llm, "provider_name", getattr(self.llm, "provider", "DEMO"))
        model_name = getattr(self.llm, "model", None)
        self.tracer.agent_started("Investigator", prov_name, model_name)

        while tool_call_count < self.max_tool_calls:
            try:
                response = self.llm.chat(messages=messages, tools=tool_definitions)
                self.last_successful_calls += 1
            except Exception as e:
                self.tracer.provider_error("Investigator", prov_name, "API_ERROR", "NOT_EVALUATED", str(e))
                # Controlled provider failure
                proposal = InvestigationProposal(
                    transaction_id=txn_id,
                    exception_type=exception_type,
                    evidence=evidence or [f"Phase 1 exception: {exception_type}"],
                    proposed_resolution="HUMAN_REVIEW",
                    resolution_type="NONE",
                    confidence=0.0,
                    unresolved_questions=[f"Provider error during investigation: {str(e)[:200]}"],
                    tool_history=tools_used,
                    reason=f"Provider request failed: {str(e)[:200]}",
                    recommended_action="Investigation not completed due to provider API failure.",
                )
                return proposal, evidence, tool_traces, evidence_state, tool_call_count

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

            # Assistant answered without calling tools
            if not message.tool_calls:
                content = message.content or ""
                proposal = self._parse_proposal(content, txn_id, exception_type, evidence, tools_used)
                return proposal, evidence, tool_traces, evidence_state, tool_call_count

            for tool_call in message.tool_calls:
                tool_call_count += 1
                tool_name = tool_call.function.name
                tools_used.append(tool_name)

                try:
                    arguments = (
                        json.loads(tool_call.function.arguments)
                        if isinstance(tool_call.function.arguments, str)
                        else tool_call.function.arguments
                    )
                except Exception:
                    arguments = {}

                # Emit tool start trace
                self.tracer.tool_call_started("Investigator", prov_name, tool_name, arguments)

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

                # Emit tool result trace
                self.tracer.tool_result(tool_name, result)

                # Update evidence state
                evidence_state.update(tool_name, result)
                self._extract_evidence(tool_name, result, evidence)

                # Check if deterministic resolution conditions are satisfied
                is_sufficient, res_data = has_sufficient_resolution_evidence(evidence_state, exception_type)

                # Record trace
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

                # Early stopping on deterministic proof
                if is_sufficient and res_data:
                    calc = res_data.get("calculation")
                    if calc and f"Calculation: {calc}" not in evidence:
                        evidence.append(f"Calculation: {calc}")

                    from src.utils.formatters import safe_decimal, safe_numeric
                    calc_dict = {}
                    if evidence_state.ledger:
                        gross = safe_decimal(evidence_state.ledger.get("gross_amount")) or 0
                        fee = safe_decimal(evidence_state.ledger.get("fee")) or 0
                        exp_net = safe_numeric(gross - fee)
                        calc_dict["Expected settlement"] = exp_net
                    adj_tot = sum((safe_decimal(a.get("amount")) or 0) for a in evidence_state.adjustments)
                    if adj_tot:
                        calc_dict["Adjustment"] = safe_numeric(adj_tot)
                        if "Expected settlement" in calc_dict and calc_dict["Expected settlement"] is not None:
                            calc_dict["Adjusted settlement"] = safe_numeric(safe_decimal(calc_dict["Expected settlement"]) - adj_tot)
                    if evidence_state.bank_records:
                        calc_dict["Bank credit"] = safe_numeric(evidence_state.bank_records[0].get("credited_amount"))

                    self.tracer.deterministic_calculation(calc_dict, proven=True)
                    self.tracer.evidence_sufficient([
                        "Documented adjustment exists",
                        "Adjusted settlement mathematically matches bank credit",
                        "No contradictory duplicate records found",
                    ])
                    self.tracer.early_stop("Investigator", tool_call_count, "sufficient deterministic evidence established")

                    proposal = InvestigationProposal(
                        transaction_id=txn_id,
                        exception_type=exception_type,
                        evidence=evidence,
                        proposed_resolution="AUTO_RESOLVED",
                        resolution_type="ADJUSTMENT_EXPLAINED",
                        resolved_difference=res_data.get("resolved_difference"),
                        confidence=1.0,
                        unresolved_questions=[],
                        tool_history=tools_used,
                        reason=res_data.get(
                            "reason",
                            "A documented transaction-specific adjustment exactly explains the settlement discrepancy.",
                        ),
                        recommended_action="No action needed; discrepancy fully accounted for by adjustment record.",
                    )
                    return proposal, evidence, tool_traces, evidence_state, tool_call_count

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result, default=str),
                })

                if tool_call_count >= self.max_tool_calls:
                    break

        # Max tool calls limit reached
        is_sufficient, res_data = has_sufficient_resolution_evidence(evidence_state, exception_type)
        if is_sufficient and res_data:
            proposal = InvestigationProposal(
                transaction_id=txn_id,
                exception_type=exception_type,
                evidence=evidence,
                proposed_resolution="AUTO_RESOLVED",
                resolution_type="ADJUSTMENT_EXPLAINED",
                resolved_difference=res_data.get("resolved_difference"),
                confidence=1.0,
                unresolved_questions=[],
                tool_history=tools_used,
                reason=res_data.get("reason", "Adjustments account for difference."),
                recommended_action="No action needed.",
            )
        else:
            proposal = InvestigationProposal(
                transaction_id=txn_id,
                exception_type=exception_type,
                evidence=evidence or [f"Phase 1 exception: {exception_type}"],
                proposed_resolution="HUMAN_REVIEW",
                resolution_type="NONE",
                confidence=0.5,
                unresolved_questions=["Investigation reached tool limit without conclusive proof."],
                tool_history=tools_used,
                reason=f"Investigation reached maximum tool limit ({self.max_tool_calls}) without conclusive proof.",
                recommended_action="Manual review required — agent investigation inconclusive.",
            )

        return proposal, evidence, tool_traces, evidence_state, tool_call_count

    def _parse_proposal(
        self,
        content: str,
        txn_id: str,
        exception_type: str,
        evidence: List[str],
        tools_used: List[str],
    ) -> InvestigationProposal:
        """Parses and validates LLM output into an InvestigationProposal."""
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
            data.setdefault("exception_type", exception_type)
            data.setdefault("evidence", evidence or [f"Phase 1 exception: {exception_type}"])
            data.setdefault("tool_history", tools_used)

            # Handle case where LLM outputs 'decision' instead of 'proposed_resolution'
            if "decision" in data and "proposed_resolution" not in data:
                data["proposed_resolution"] = data["decision"]

            if "confidence" in data and isinstance(data["confidence"], (int, float)):
                data["confidence"] = max(0.0, min(1.0, float(data["confidence"])))

            return InvestigationProposal(**data)
        except Exception as e:
            return InvestigationProposal(
                transaction_id=txn_id,
                exception_type=exception_type,
                evidence=evidence or [f"Phase 1 exception: {exception_type}"],
                proposed_resolution="HUMAN_REVIEW",
                resolution_type="NONE",
                confidence=0.0,
                unresolved_questions=[f"Proposal parsing failed: {str(e)[:200]}"],
                tool_history=tools_used,
                reason=f"Investigator proposal parse error: {str(e)[:200]}",
                recommended_action="Manual review required due to output format error.",
            )

    @staticmethod
    def _summarize_tool_result(tool_name: str, result: Any) -> str:
        if not isinstance(result, dict):
            return str(result)[:200]
        if "error" in result:
            return f"Error: {result['error']}"

        if tool_name == "get_transaction":
            p = result.get("payment")
            l = result.get("ledger")
            b = result.get("bank_records", [])
            a = result.get("adjustments", [])
            return f"Payment: {'found' if p else 'none'}, Ledger: {'found' if l else 'none'}, Bank: {len(b)}, Adjs: {len(a)}"
        elif tool_name == "get_payment_record":
            amt = result.get("amount")
            return f"Payment amount: {format_currency(amt)}" if amt is not None else "No record"
        elif tool_name == "get_ledger_record":
            gross = result.get("gross_amount")
            return f"Ledger gross: {format_currency(gross)}" if gross is not None else "No record"
        elif tool_name == "get_bank_records":
            count = result.get("count", 0)
            return f"{count} bank record(s)"
        elif tool_name == "get_adjustments":
            count = result.get("count", 0)
            return f"{count} adjustment(s)"
        elif tool_name in ("calculate_expected_settlement", "calculate_adjusted_expected_settlement"):
            return str(result.get("calculation", ""))
        elif tool_name == "check_for_duplicates":
            return f"is_duplicate: {result.get('is_duplicate', False)}"
        return str(result)[:200]

    @staticmethod
    def _extract_evidence(tool_name: str, result: Any, evidence: List[str]) -> None:
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
        elif tool_name == "get_adjustments":
            for a in result.get("adjustments", []):
                amt = a.get("amount")
                if amt is not None:
                    evidence.append(f"Adjustment ({a.get('adjustment_type')}): {format_currency(amt)} ({a.get('reason', '')})")
        elif tool_name in ("calculate_expected_settlement", "calculate_adjusted_expected_settlement"):
            calc = result.get("calculation")
            if calc:
                evidence.append(f"Settlement calculation: {calc}")
        elif tool_name == "check_for_duplicates":
            count = result.get("duplicate_count", 0)
            if count > 1:
                evidence.append(f"Duplicate check: {count} bank records found (duplicate=True)")
