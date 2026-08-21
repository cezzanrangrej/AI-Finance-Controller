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

from src.agent.prompts import SYSTEM_PROMPT, build_investigation_prompt
from src.agent.schemas import AgentDecision, InvestigationLog
from src.agent.tools import FinancialToolkit

# Maximum number of tool calls per investigation before auto-escalation
MAX_TOOL_CALLS = 5


class LLMClient:
    """
    Thin wrapper around an OpenAI-compatible chat API.

    Supports an automatic Demo / Mock mode fallback if OPENAI_API_KEY is not set,
    allowing full application execution and testing without requiring an API key.
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None) -> None:
        """
        Initialises the LLM client.

        Args:
            api_key: OpenAI API key. Falls back to OPENAI_API_KEY env var.
            model: Model name. Falls back to MODEL_NAME env var, then 'gpt-4o-mini'.
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.model = model or os.getenv("MODEL_NAME", "gpt-4o-mini")
        self.demo_mode = False

        if not self.api_key:
            # Activate deterministic Demo Mode
            self.demo_mode = True
            self._client = None
        else:
            try:
                from openai import OpenAI  # type: ignore
                self._client = OpenAI(api_key=self.api_key)
            except ImportError:
                self.demo_mode = True
                self._client = None

    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: str = "auto",
    ) -> Any:
        """Sends a chat completion request to the LLM or executes deterministic Demo Mode."""
        if self.demo_mode:
            return self._demo_chat(messages, tools)

        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice

        return self._client.chat.completions.create(**kwargs)

    def _demo_chat(self, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]]) -> Any:
        """Deterministic demo mode chat implementation for offline / key-less runs."""
        txn_id = "UNKNOWN"
        user_content = ""
        for m in messages:
            if m.get("role") == "user":
                user_content = m.get("content", "")
                for line in user_content.splitlines():
                    if "Transaction ID:" in line:
                        txn_id = line.split(":")[-1].strip()
                        break

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

        # Calculate numbers
        payment_amt = payment.get("amount") if payment else None
        gross_amt = ledger.get("gross_amount") if ledger else None
        fee_amt = ledger.get("fee") if ledger else None
        expected_net = (gross_amt - fee_amt) if (gross_amt is not None and fee_amt is not None) else None
        bank_amt = banks[0].get("credited_amount") if len(banks) == 1 else None

        total_adj_amt = sum(a.get("amount") or 0 for a in adjustments)

        # Decision Evaluation Policy
        decision = "HUMAN_REVIEW"
        resolution_type = "NONE"
        resolved_diff = None
        reason = ""
        action = ""
        confidence = 0.95
        evidence = []

        if payment_amt:
            evidence.append(f"Payment amount = ₹{payment_amt:,}")
        if ledger:
            evidence.append(f"Ledger gross = ₹{gross_amt:,}, fee = ₹{fee_amt:,}")
            if expected_net is not None:
                evidence.append(f"Expected settlement = ₹{expected_net:,}")
        if bank_amt is not None:
            evidence.append(f"Bank credit = ₹{bank_amt:,}")

        # Check if adjustments explain the gap
        if adjustments:
            for adj in adjustments:
                evidence.append(f"Adjustment ({adj.get('adjustment_type')}): ₹{adj.get('amount'):,} - {adj.get('reason')}")

        if not ledger:
            decision = "HUMAN_REVIEW"
            reason = f"Payment captured (₹{payment_amt:,}) but missing corresponding ledger entry in ERP."
            action = "Post missing ledger entry in ERP."
        elif not banks:
            decision = "HUMAN_REVIEW"
            reason = f"Expected settlement ₹{expected_net:,} missing from bank statements."
            action = "Contact acquiring bank to trace settlement batch."
        elif len(banks) > 1:
            decision = "HUMAN_REVIEW"
            reason = f"Multiple ({len(banks)}) bank settlement records found for single transaction."
            action = "Review bank statement for potential duplicate credit."
        elif expected_net is not None and bank_amt is not None and (expected_net - total_adj_amt) == bank_amt and total_adj_amt > 0:
            # Deterministically explained by adjustments!
            decision = "AUTO_RESOLVED"
            resolution_type = "ADJUSTMENT_EXPLAINED"
            resolved_diff = float(total_adj_amt)
            confidence = 1.0
            reason = f"Bank credit (₹{bank_amt:,}) equals expected settlement (₹{expected_net:,}) minus documented adjustment of ₹{total_adj_amt:,}."
            action = "No action needed; discrepancy fully accounted for by adjustment record."
            evidence.append(f"Calculation: ₹{expected_net:,} - ₹{total_adj_amt:,} = ₹{bank_amt:,}")
        elif payment_amt is not None and gross_amt is not None and (payment_amt - total_adj_amt) == gross_amt and total_adj_amt > 0:
            decision = "AUTO_RESOLVED"
            resolution_type = "ADJUSTMENT_EXPLAINED"
            resolved_diff = float(total_adj_amt)
            confidence = 1.0
            reason = f"Gross amount discrepancy of ₹{total_adj_amt:,} is explicitly accounted for by adjustment reference."
            action = "No action needed; gross amount adjustment verified."
        elif expected_net is not None and bank_amt is not None:
            diff = expected_net - bank_amt
            if adjustments and total_adj_amt != diff:
                reason = f"Bank credit is ₹{diff:,} lower than expected, but documented adjustments total ₹{total_adj_amt:,} (mismatch of ₹{diff - total_adj_amt:,})."
                action = "Review bank fee schedule and settlement file."
            else:
                reason = f"Bank credit of ₹{bank_amt:,} is ₹{diff:,} lower than expected settlement (₹{expected_net:,}) with no adjustment record."
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


class AgentController:
    """Orchestrates exception investigation using the LLM and deterministic tools."""

    def __init__(self, toolkit: FinancialToolkit, llm_client: LLMClient) -> None:
        self.toolkit = toolkit
        self.llm = llm_client

    def investigate_exception(
        self, exception_record: Dict[str, Any]
    ) -> tuple[AgentDecision, InvestigationLog]:
        """Runs a full investigation for a single Phase 1 exception."""
        txn_id = exception_record.get("transaction_id", "UNKNOWN")
        exception_type = exception_record.get("reason", "UNKNOWN")
        timestamp = datetime.now(timezone.utc)

        tools_used: List[str] = []
        evidence: List[str] = []
        tool_call_count = 0

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_investigation_prompt(exception_record)},
        ]

        tool_definitions = self.toolkit.get_tool_definitions()

        while tool_call_count < MAX_TOOL_CALLS:
            response = self.llm.chat(messages=messages, tools=tool_definitions)
            choice = response.choices[0]
            message = choice.message

            messages.append({"role": "assistant", "content": message.content, "tool_calls": (
                [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in (message.tool_calls or [])
                ]
            )})

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
                )
                return decision, log

            for tool_call in message.tool_calls:
                tool_call_count += 1
                tool_name = tool_call.function.name
                tools_used.append(tool_name)

                try:
                    arguments = json.loads(tool_call.function.arguments)
                    result = self.toolkit.dispatch(tool_name, arguments)
                except Exception as e:
                    result = {"error": f"Tool execution failed: {str(e)}"}

                self._extract_evidence(tool_name, result, evidence)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result, default=str),
                })

                if tool_call_count >= MAX_TOOL_CALLS:
                    break

        return self._escalate_on_limit(txn_id, exception_type, evidence, tools_used, timestamp, tool_call_count)

    def _parse_decision(
        self,
        content: str,
        txn_id: str,
        exception_type: str,
        evidence: List[str],
    ) -> AgentDecision:
        """Parses and validates the LLM's final JSON response into an AgentDecision."""
        try:
            cleaned = content.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                cleaned = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])

            data = json.loads(cleaned)
            data.setdefault("transaction_id", txn_id)
            data.setdefault("exception_type", exception_type)
            data.setdefault("evidence", evidence or [f"Phase 1 exception: {exception_type}"])
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
    ) -> tuple[AgentDecision, InvestigationLog]:
        """Produces a HUMAN_REVIEW decision when MAX_TOOL_CALLS is exceeded."""
        decision = AgentDecision(
            transaction_id=txn_id,
            decision="HUMAN_REVIEW",
            exception_type=exception_type,
            resolution_type="NONE",
            reason=f"Investigation exceeded MAX_TOOL_CALLS ({MAX_TOOL_CALLS}) without reaching a conclusion.",
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
        )
        return decision, log

    @staticmethod
    def _extract_evidence(tool_name: str, result: Any, evidence: List[str]) -> None:
        """Extracts concise evidence facts from tool execution results."""
        if not isinstance(result, dict) or "error" in result:
            return

        if tool_name == "get_payment_record":
            amt = result.get("amount")
            if amt is not None:
                evidence.append(f"Payment amount = ₹{amt:,}")

        elif tool_name == "get_ledger_record":
            gross = result.get("gross_amount")
            fee = result.get("fee")
            if gross is not None:
                evidence.append(f"Ledger gross = ₹{gross:,}")
            if fee is not None:
                evidence.append(f"Ledger fee = ₹{fee:,}")

        elif tool_name == "get_adjustments":
            count = result.get("count", 0)
            records = result.get("adjustments", [])
            evidence.append(f"Adjustment records found: {count}")
            for r in records:
                typ = r.get("adjustment_type")
                amt = r.get("amount")
                if amt is not None:
                    evidence.append(f"  Adjustment ({typ}): ₹{amt:,} ({r.get('reason')})")

        elif tool_name in ["calculate_expected_settlement", "calculate_adjusted_expected_settlement"]:
            calc = result.get("calculation")
            exp = result.get("adjusted_expected_net", result.get("expected_net"))
            if calc:
                evidence.append(f"Settlement calculation: {calc}")

        elif tool_name == "get_bank_records":
            count = result.get("count", 0)
            records = result.get("bank_records", [])
            evidence.append(f"Bank records found: {count}")
            for r in records:
                amt = r.get("credited_amount")
                if amt is not None:
                    evidence.append(f"  {r.get('bank_reference')}: credited ₹{amt:,}")

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
) -> AgentController:
    """Factory function for creating an AgentController."""
    toolkit = FinancialToolkit(payments, ledger_records, bank_records, adjustments)
    llm_client = LLMClient(api_key=api_key, model=model)
    return AgentController(toolkit=toolkit, llm_client=llm_client)
