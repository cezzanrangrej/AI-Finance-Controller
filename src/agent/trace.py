"""
Live Agent Trace / Terminal Observability layer for AI Finance Controller.
Provides clean, structured, real-time terminal observability of the multi-agent
workflow, tool executions, deterministic finance engine calculations, independent
verifier evaluations, and final controller safety policies.

Two independent outputs are driven from the same events:

* The terminal stream, gated by ``SHOW_AGENT_TRACE`` and filtered by
  ``AGENT_TRACE_LEVEL`` (minimal | compact | verbose).
* An optional structured ``event_sink`` callable, used by the API to forward the
  same workflow events to the browser over SSE. The sink is deliberately
  independent of ``enabled``: the frontend trace feed works whether or not the
  operator wants terminal output.
"""

import os
import re
import sys
from typing import Any, Callable, Dict, List, Optional
from src.utils.formatters import format_currency


#: Trace verbosity levels, least to most detailed. An event tagged with a level
#: prints only when the configured level is at least as detailed.
#:
#:   minimal  -- run/transaction boundaries, final decisions, errors, summaries
#:   compact  -- the above plus agent routing, verifier outcomes, evidence checks
#:   verbose  -- the above plus every tool call, tool result, and arithmetic step
TRACE_LEVELS: Dict[str, int] = {"minimal": 0, "compact": 1, "verbose": 2}

DEFAULT_TRACE_LEVEL = "verbose"


def parse_bool_env(var_name: str, default: bool = False) -> bool:
    """Safely parses boolean environment variables."""
    val = os.getenv(var_name)
    if val is None:
        return default
    val_clean = str(val).strip().lower()
    return val_clean in ("true", "1", "t", "yes", "y", "on")


def normalize_trace_level(level: Optional[str]) -> str:
    """
    Resolves a trace level name, falling back to the most detailed level.

    An unrecognised value falls back to 'verbose' rather than raising: a typo in
    AGENT_TRACE_LEVEL should not abort a reconciliation run, and showing too much
    is the safer failure mode for an observability layer.
    """
    name = (level or "").strip().lower()
    return name if name in TRACE_LEVELS else DEFAULT_TRACE_LEVEL


class AgentTracer:
    """
    Real-time terminal observability utility for AI Finance Controller.
    Emits structured, non-sensitive operational events with real-time flushing.
    """

    def __init__(
        self,
        enabled: Optional[bool] = None,
        level: Optional[str] = None,
        output_stream=None,
        event_sink: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        # Precedence: Explicit constructor arg > Environment variable > Default (False)
        if enabled is not None:
            self.enabled = enabled
        else:
            self.enabled = parse_bool_env("SHOW_AGENT_TRACE", False)

        self.level = normalize_trace_level(level or os.getenv("AGENT_TRACE_LEVEL"))
        self.stream = output_stream or sys.stdout
        self.event_sink = event_sink
        self._seq = 0

    # ------------------------------------------------------------------
    # Level gating
    # ------------------------------------------------------------------

    def _visible(self, required_level: str = "verbose") -> bool:
        """Returns True when terminal output is on and detailed enough for this event."""
        if not self.enabled:
            return False
        return TRACE_LEVELS[self.level] >= TRACE_LEVELS[normalize_trace_level(required_level)]

    # ------------------------------------------------------------------
    # Structured event sink
    # ------------------------------------------------------------------

    def _sanitize_value(self, value: Any) -> Any:
        """Recursively strips secrets from sink payload values."""
        if isinstance(value, str):
            return self._sanitize(value)
        if isinstance(value, dict):
            return {k: self._sanitize_value(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._sanitize_value(v) for v in value]
        return value

    def _event(self, event_type: str, payload: Optional[Dict[str, Any]] = None, level: str = "verbose") -> None:
        """
        Forwards a structured workflow event to the sink, if one is attached.

        Never raises: a failing sink (closed SSE stream, full queue) must not take
        down the reconciliation run it is only observing.
        """
        if self.event_sink is None:
            return
        try:
            self._seq += 1
            self.event_sink({
                "seq": self._seq,
                "type": event_type,
                "level": normalize_trace_level(level),
                **self._sanitize_value(payload or {}),
            })
        except Exception:
            pass

    def _sanitize(self, text: str) -> str:
        """Strips secrets, API keys, and authorization headers from trace text."""
        if not text:
            return ""
        sanitized = str(text)
        # Mask OpenRouter, Gemini, Google, xAI, and general API keys / tokens if present
        sanitized = re.sub(
            r"(sk-or-v1-[a-zA-Z0-9]{10,}|sk-[a-zA-Z0-9_-]{20,}|AIzaSy[a-zA-Z0-9_-]{20,}|AQ\.[a-zA-Z0-9_-]{20,}|xai-[a-zA-Z0-9]{20,})",
            "[REDACTED_API_KEY]",
            sanitized,
        )
        sanitized = re.sub(r"(Bearer\s+)[a-zA-Z0-9_\-\.]{10,}", r"\1[REDACTED_TOKEN]", sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(r"(Authorization:\s*)[^\r\n]+", r"\1[REDACTED_HEADER]", sanitized, flags=re.IGNORECASE)
        return sanitized

    def _print(self, message: str = "") -> None:
        """Prints a sanitized message immediately to the output stream."""
        if not self.enabled:
            return
        sanitized = self._sanitize(message)
        print(sanitized, file=self.stream, flush=True)

    # ------------------------------------------------------------------
    # Transaction & Orchestrator Events
    # ------------------------------------------------------------------

    def header(self, title: str = "AI FINANCE CONTROLLER — MULTI-AGENT TRACE") -> None:
        """Prints the top-level section header."""
        self._event("run_header", {"title": title}, level="minimal")
        if not self._visible("minimal"):
            return
        self._print("\n" + "=" * 50)
        self._print(title)
        self._print("=" * 50 + "\n")

    def transaction_header(self, txn_id: str, exception_type: str, index: Optional[int] = None, total: Optional[int] = None) -> None:
        """Prints the start of a transaction investigation."""
        self._event(
            "transaction_started",
            {"transaction_id": txn_id, "exception_type": exception_type, "index": index, "total": total},
            level="minimal",
        )
        if not self._visible("minimal"):
            return
        self._print("-" * 50)
        prefix = f"[{index}/{total}] " if index is not None and total is not None else ""
        self._print(f"{prefix}Transaction: {txn_id}")
        self._print(f"Exception: {exception_type}")
        self._print("-" * 50)

    def orchestrator_routing(self, target: str = "Investigator", fast_path: bool = False) -> None:
        """Emits an orchestrator routing decision."""
        self._event("orchestrator_routing", {"target": target, "fast_path": fast_path}, level="compact")
        if not self._visible("compact"):
            return
        self._print("\n[ORCHESTRATOR]")
        if fast_path:
            self._print(f"→ Applying deterministic fast path: {target}")
        else:
            self._print(f"→ Routing to {target}")

    def orchestrator_step_completed(self, step_name: str) -> None:
        """Emits orchestrator phase completion."""
        self._event("orchestrator_step_completed", {"step": step_name}, level="compact")
        if not self._visible("compact"):
            return
        self._print("\n[ORCHESTRATOR]")
        self._print(f"✓ {step_name} completed")

    def orchestrator_policy_start(self) -> None:
        """Emits start of final decision policy application."""
        self._event("orchestrator_policy_start", {}, level="compact")
        if not self._visible("compact"):
            return
        self._print("\n[ORCHESTRATOR]")
        self._print("→ Applying final decision policy")

    # ------------------------------------------------------------------
    # Agent & Tool Events
    # ------------------------------------------------------------------

    def agent_started(self, role: str, provider: str, model: Optional[str] = None) -> None:
        """Emits the start of an agent's execution phase."""
        self._event("agent_started", {"role": role, "provider": provider, "model": model}, level="compact")
        if not self._visible("compact"):
            return
        role_label = role.upper()
        prov_label = (provider or "DEMO").upper()
        self._print(f"\n[{role_label} | {prov_label}]")
        if model:
            self._print(f"Model: {model}")

    def tool_call_started(self, role: str, provider: str, tool_name: str, arguments: Dict[str, Any]) -> None:
        """Emits an investigator tool call with sanitized, concise arguments."""
        # Format safe operational arguments
        if isinstance(arguments, dict):
            safe_args_str = ", ".join(f"{k}={v}" for k, v in arguments.items() if not str(k).lower().endswith("key"))
        else:
            safe_args_str = str(arguments)

        self._event(
            "tool_call",
            {"role": role, "provider": provider, "tool_name": tool_name, "arguments": safe_args_str},
            level="verbose",
        )
        if not self._visible("verbose"):
            return
        role_label = role.upper()
        prov_label = (provider or "DEMO").upper()
        self._print(f"[{role_label} | {prov_label}]")
        self._print(f"→ Calling {tool_name}({safe_args_str})")

    def _tool_result_lines(self, tool_name: str, result: Any) -> List[str]:
        """Builds the concise, safe summary lines for a tool execution result."""
        if not isinstance(result, dict):
            return [f"← {str(result)[:100]}"]

        if "error" in result:
            return [f"← Error: {result['error']}"]

        lines: List[str] = []

        if tool_name == "get_transaction":
            p = result.get("payment")
            l = result.get("ledger")
            b = result.get("bank_records", [])
            a = result.get("adjustments", [])
            if p and p.get("amount") is not None:
                lines.append(f"← Payment: {format_currency(p.get('amount'))}")
            if l and l.get("gross_amount") is not None:
                lines.append(f"← Ledger gross: {format_currency(l.get('gross_amount'))}")
            if b:
                amt = b[0].get("credited_amount")
                lines.append(f"← Bank credit: {format_currency(amt) if amt is not None else 'present'} ({len(b)} record{'s' if len(b) > 1 else ''})")
            else:
                lines.append("← Bank credit: None")
            if a:
                lines.append(f"← Adjustments: {len(a)} found")

        elif tool_name == "get_adjustments":
            count = result.get("count", 0)
            adjs = result.get("adjustments", [])
            lines.append(f"← {count} adjustment{'s' if count != 1 else ''} found")
            for adj in adjs:
                typ = adj.get("adjustment_type", "ADJUSTMENT")
                amt = adj.get("amount")
                amt_str = format_currency(amt) if amt is not None else ""
                lines.append(f"← {typ}: {amt_str}")

        elif tool_name == "get_payment_record":
            amt = result.get("amount")
            lines.append(f"← Payment amount: {format_currency(amt) if amt is not None else 'None'}")

        elif tool_name == "get_ledger_record":
            gross = result.get("gross_amount")
            fee = result.get("fee")
            lines.append(f"← Ledger gross: {format_currency(gross)}, fee: {format_currency(fee)}")

        elif tool_name == "get_bank_records":
            count = result.get("count", 0)
            records = result.get("bank_records", [])
            lines.append(f"← {count} bank record(s) found")
            for r in records:
                amt = r.get("credited_amount")
                lines.append(f"← Credit: {format_currency(amt)}")

        elif tool_name == "check_for_duplicates":
            count = result.get("duplicate_count", 0)
            is_dup = result.get("is_duplicate", False)
            lines.append(f"← {count} bank record(s) checked")
            lines.append(f"← Duplicate: {'YES' if is_dup else 'NO'}")

        elif tool_name in ("calculate_expected_settlement", "calculate_adjusted_expected_settlement"):
            calc = result.get("calculation", "")
            adj_net = result.get("adjusted_expected_net") or result.get("expected_net")
            lines.append(f"← Calculation: {calc}")
            if adj_net is not None:
                lines.append(f"← Result: {format_currency(adj_net)}")
        else:
            lines.append(f"← {str(result)[:120]}")

        return lines

    def tool_result(self, tool_name: str, result: Any) -> None:
        """Emits a concise, safe summary of a tool execution result."""
        lines = self._tool_result_lines(tool_name, result)
        is_error = isinstance(result, dict) and "error" in result
        self._event(
            "tool_result",
            {"tool_name": tool_name, "lines": lines, "error": is_error},
            level="verbose",
        )
        if not self._visible("verbose"):
            return
        self._print("[TOOL RESULT]")
        for line in lines:
            self._print(line)

    # ------------------------------------------------------------------
    # Deterministic Finance Engine Events
    # ------------------------------------------------------------------

    def deterministic_calculation(self, items: Dict[str, Any], proven: bool = False) -> None:
        """
        Emits authoritative deterministic financial engine calculations.
        Clearly demonstrates that Python (not LLM) performs financial arithmetic.
        """
        formatted = {
            k: (format_currency(v) if isinstance(v, (int, float)) else str(v))
            for k, v in items.items()
        }
        self._event("deterministic_calculation", {"items": formatted, "proven": proven}, level="verbose")
        if not self._visible("verbose"):
            return
        self._print("\n[FINANCE ENGINE | PYTHON]")
        for k, v_str in formatted.items():
            self._print(f"→ {k}: {v_str}")
        if proven:
            self._print("✓ Equality proven")

    def evidence_sufficient(self, reasons: Optional[List[str]] = None) -> None:
        """Emits deterministic sufficiency check passing."""
        self._event("evidence_sufficient", {"reasons": list(reasons or [])}, level="compact")
        if not self._visible("compact"):
            return
        self._print("\n[EVIDENCE CHECK | PYTHON]")
        self._print("✓ Sufficient deterministic evidence established")
        if reasons:
            for r in reasons:
                self._print(f"✓ {r}")

    def early_stop(self, role: str, tool_count: int, reason: str = "sufficient evidence established") -> None:
        """Emits early stopping event."""
        self._event("early_stop", {"role": role, "tool_count": tool_count, "reason": reason}, level="compact")
        if not self._visible("compact"):
            return
        role_label = role.upper()
        self._print(f"\n[{role_label}]")
        self._print(f"✓ Investigation complete — {reason}")
        self._print(f"Tool calls used: {tool_count}")

    # ------------------------------------------------------------------
    # Verifier Events
    # ------------------------------------------------------------------

    def verifier_review_started(self, provider: str, model: Optional[str] = None) -> None:
        """Emits the start of independent verification."""
        self._event("verifier_review_started", {"provider": provider, "model": model}, level="compact")
        if not self._visible("compact"):
            return
        prov_label = (provider or "DEMO").upper()
        self._print(f"\n[VERIFIER | {prov_label}]")
        if model:
            self._print(f"Model: {model}")
        self._print("→ Reviewing investigator proposal against source records")

    def verifier_review_result(self, provider: str, verified: bool, decision: str, reason: str, contradictions: Optional[List[str]] = None) -> None:
        """Emits the outcome of verifier evaluation."""
        self._event(
            "verifier_review_result",
            {
                "provider": provider,
                "verified": verified,
                "decision": decision,
                "reason": reason,
                "contradictions": list(contradictions or []),
            },
            level="compact",
        )
        if not self._visible("compact"):
            return
        prov_label = (provider or "DEMO").upper()
        self._print(f"\n[VERIFIER | {prov_label}]")
        if verified and decision == "AUTO_RESOLVED":
            self._print("✓ Evidence supported")
            self._print("← Verification: VERIFIED")
        elif contradictions:
            self._print("⚠ Contradiction detected")
            self._print("← Verification: REJECTED")
        else:
            self._print("⚠ Evidence insufficient for auto-resolution")
            self._print(f"← Verification: {decision}")

    # ------------------------------------------------------------------
    # Final Decision & Controller Policy
    # ------------------------------------------------------------------

    def final_decision(
        self,
        investigator_dec: str,
        verifier_dec: str,
        proof_pass: bool,
        final_decision: str,
        resolution_type: str = "NONE",
        resolution_source: str = "MULTI_AGENT_CONSENSUS",
        reason: Optional[str] = None,
    ) -> None:
        """Emits the final controller decision and disagreement breakdown."""
        self._event(
            "final_decision",
            {
                "investigator_decision": investigator_dec,
                "verifier_decision": verifier_dec,
                "proof_pass": proof_pass,
                "final_decision": final_decision,
                "resolution_type": resolution_type,
                "resolution_source": resolution_source,
                "reason": reason,
            },
            level="minimal",
        )
        if not self._visible("minimal"):
            return
        self._print("\n[FINAL CONTROLLER]")
        self._print(f"Investigator: {investigator_dec}")
        self._print(f"Verifier: {'VERIFIED' if verifier_dec == 'AUTO_RESOLVED' else verifier_dec}")
        self._print(f"Deterministic proof: {'PASS' if proof_pass else 'FAIL'}")
        self._print(f"\n→ FINAL DECISION: {final_decision}")
        if resolution_type and resolution_type != "NONE":
            self._print(f"Resolution: {resolution_type}")
        if resolution_source:
            self._print(f"Resolution source: {resolution_source}")
        if reason and final_decision == "HUMAN_REVIEW":
            self._print(f"Reason: {reason}")

    # ------------------------------------------------------------------
    # Technical Error Events
    # ------------------------------------------------------------------

    def provider_error(
        self,
        role: str,
        provider: str,
        status: str,
        action: str = "NOT_EVALUATED",
        error_msg: Optional[str] = None,
        error_type: Optional[str] = None,
    ) -> None:
        """Emits a sanitized provider error event."""
        self._event(
            "provider_error",
            {
                "role": role,
                "provider": provider,
                "status": status,
                "action": action,
                "error_type": error_type,
                "details": str(error_msg)[:150] if error_msg else None,
            },
            level="minimal",
        )
        if not self._visible("minimal"):
            return
        prov_label = (provider or "UNKNOWN").upper()
        self._print(f"\n[PROVIDER ERROR | {prov_label}]")
        self._print(f"Status: {status}")
        if error_type:
            self._print(f"Type: {error_type}")
        self._print(f"Action: {action}")
        if error_msg and not error_type:
            self._print(f"Details: {self._sanitize(str(error_msg)[:150])}")

    # ------------------------------------------------------------------
    # Summaries
    # ------------------------------------------------------------------

    def transaction_summary(
        self,
        txn_id: str,
        investigator_prov: str,
        verifier_prov: str,
        inv_calls: int,
        ver_calls: int,
        model_interactions: int,
        latency_sec: float,
        tokens: Optional[int],
        final_decision: str,
        resolution_source: str,
    ) -> None:
        """Prints a clean summary block at the conclusion of a transaction."""
        self._event(
            "transaction_summary",
            {
                "transaction_id": txn_id,
                "investigator_provider": investigator_prov,
                "verifier_provider": verifier_prov,
                "investigator_calls": inv_calls,
                "verifier_calls": ver_calls,
                "model_interactions": model_interactions,
                "latency_sec": round(latency_sec, 4),
                "tokens": tokens,
                "final_decision": final_decision,
                "resolution_source": resolution_source,
            },
            level="compact",
        )
        if not self._visible("compact"):
            return
        self._print("\n" + "-" * 50)
        self._print("TRANSACTION SUMMARY")
        self._print("-" * 50)
        self._print(f"Transaction: {txn_id}")
        self._print(f"Investigator: {investigator_prov}")
        self._print(f"Verifier: {verifier_prov}")
        self._print(f"\nTool calls:")
        self._print(f"  Investigator: {inv_calls}")
        self._print(f"  Verifier: {ver_calls}")
        self._print(f"Model interactions: {model_interactions}")
        self._print(f"Latency: {latency_sec:.2f} sec")
        self._print(f"Tokens: {f'{tokens:,}' if tokens else 'N/A'}")
        self._print(f"\nFinal decision: {final_decision}")
        self._print(f"Resolution source: {resolution_source}")
        self._print("-" * 50 + "\n")

    def multi_agent_run_summary(
        self,
        cases_processed: int,
        auto_resolved: int,
        human_review: int,
        not_evaluated: int,
        investigator_calls: int,
        verifier_calls: int,
        total_interactions: int,
        average_latency: float,
        total_tokens: Optional[int],
    ) -> None:
        """Prints an aggregate multi-agent run summary block."""
        self._event(
            "run_summary",
            {
                "cases_processed": cases_processed,
                "auto_resolved": auto_resolved,
                "human_review": human_review,
                "not_evaluated": not_evaluated,
                "investigator_calls": investigator_calls,
                "verifier_calls": verifier_calls,
                "total_interactions": total_interactions,
                "average_latency": round(average_latency, 4),
                "total_tokens": total_tokens,
            },
            level="minimal",
        )
        if not self._visible("minimal"):
            return
        self._print("\n" + "=" * 50)
        self._print("MULTI-AGENT RUN SUMMARY")
        self._print("=" * 50)
        self._print(f"Cases processed:           {cases_processed}")
        self._print(f"AUTO_RESOLVED:             {auto_resolved}")
        self._print(f"HUMAN_REVIEW:              {human_review}")
        self._print(f"NOT_EVALUATED:             {not_evaluated}\n")
        self._print(f"Investigator calls:        {investigator_calls}")
        self._print(f"Verifier calls:            {verifier_calls}")
        self._print(f"Total model interactions:  {total_interactions}\n")
        self._print(f"Average latency/case:      {average_latency:.4f} sec")
        tok_str = f"{total_tokens:,}" if total_tokens else "N/A"
        self._print(f"Total tokens:              {tok_str}")
        self._print("=" * 50 + "\n")


# Global default tracer instance
default_tracer = AgentTracer()
