"""
Live Agent Trace / Terminal Observability layer for AI Finance Controller.
Provides clean, structured, real-time terminal observability of the multi-agent
workflow, tool executions, deterministic finance engine calculations, independent
verifier evaluations, and final controller safety policies.
"""

import os
import re
import sys
from typing import Any, Dict, List, Optional
from src.utils.formatters import format_currency


def parse_bool_env(var_name: str, default: bool = False) -> bool:
    """Safely parses boolean environment variables."""
    val = os.getenv(var_name)
    if val is None:
        return default
    val_clean = str(val).strip().lower()
    return val_clean in ("true", "1", "t", "yes", "y", "on")


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
    ) -> None:
        # Precedence: Explicit constructor arg > Environment variable > Default (False)
        if enabled is not None:
            self.enabled = enabled
        else:
            self.enabled = parse_bool_env("SHOW_AGENT_TRACE", False)

        self.level = (level or os.getenv("AGENT_TRACE_LEVEL") or "verbose").strip().lower()
        self.stream = output_stream or sys.stdout

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
        if not self.enabled:
            return
        self._print("\n" + "=" * 50)
        self._print(title)
        self._print("=" * 50 + "\n")

    def transaction_header(self, txn_id: str, exception_type: str, index: Optional[int] = None, total: Optional[int] = None) -> None:
        """Prints the start of a transaction investigation."""
        if not self.enabled:
            return
        self._print("-" * 50)
        prefix = f"[{index}/{total}] " if index is not None and total is not None else ""
        self._print(f"{prefix}Transaction: {txn_id}")
        self._print(f"Exception: {exception_type}")
        self._print("-" * 50)

    def orchestrator_routing(self, target: str = "Investigator", fast_path: bool = False) -> None:
        """Emits an orchestrator routing decision."""
        if not self.enabled:
            return
        self._print("\n[ORCHESTRATOR]")
        if fast_path:
            self._print(f"→ Applying deterministic fast path: {target}")
        else:
            self._print(f"→ Routing to {target}")

    def orchestrator_step_completed(self, step_name: str) -> None:
        """Emits orchestrator phase completion."""
        if not self.enabled:
            return
        self._print("\n[ORCHESTRATOR]")
        self._print(f"✓ {step_name} completed")

    def orchestrator_policy_start(self) -> None:
        """Emits start of final decision policy application."""
        if not self.enabled:
            return
        self._print("\n[ORCHESTRATOR]")
        self._print("→ Applying final decision policy")

    # ------------------------------------------------------------------
    # Agent & Tool Events
    # ------------------------------------------------------------------

    def agent_started(self, role: str, provider: str, model: Optional[str] = None) -> None:
        """Emits the start of an agent's execution phase."""
        if not self.enabled:
            return
        role_label = role.upper()
        prov_label = (provider or "DEMO").upper()
        self._print(f"\n[{role_label} | {prov_label}]")
        if model:
            self._print(f"Model: {model}")

    def tool_call_started(self, role: str, provider: str, tool_name: str, arguments: Dict[str, Any]) -> None:
        """Emits an investigator tool call with sanitized, concise arguments."""
        if not self.enabled:
            return
        role_label = role.upper()
        prov_label = (provider or "DEMO").upper()
        # Format safe operational arguments
        if isinstance(arguments, dict):
            safe_args_str = ", ".join(f"{k}={v}" for k, v in arguments.items() if not str(k).lower().endswith("key"))
        else:
            safe_args_str = str(arguments)

        self._print(f"[{role_label} | {prov_label}]")
        self._print(f"→ Calling {tool_name}({safe_args_str})")

    def tool_result(self, tool_name: str, result: Any) -> None:
        """Emits a concise, safe summary of a tool execution result."""
        if not self.enabled:
            return
        self._print("[TOOL RESULT]")
        if not isinstance(result, dict):
            self._print(f"← {str(result)[:100]}")
            return

        if "error" in result:
            self._print(f"← Error: {result['error']}")
            return

        if tool_name == "get_transaction":
            p = result.get("payment")
            l = result.get("ledger")
            b = result.get("bank_records", [])
            a = result.get("adjustments", [])
            if p and p.get("amount") is not None:
                self._print(f"← Payment: {format_currency(p.get('amount'))}")
            if l and l.get("gross_amount") is not None:
                self._print(f"← Ledger gross: {format_currency(l.get('gross_amount'))}")
            if b:
                amt = b[0].get("credited_amount")
                self._print(f"← Bank credit: {format_currency(amt) if amt is not None else 'present'} ({len(b)} record{'s' if len(b) > 1 else ''})")
            else:
                self._print("← Bank credit: None")
            if a:
                self._print(f"← Adjustments: {len(a)} found")

        elif tool_name == "get_adjustments":
            count = result.get("count", 0)
            adjs = result.get("adjustments", [])
            self._print(f"← {count} adjustment{'s' if count != 1 else ''} found")
            for adj in adjs:
                typ = adj.get("adjustment_type", "ADJUSTMENT")
                amt = adj.get("amount")
                amt_str = format_currency(amt) if amt is not None else ""
                self._print(f"← {typ}: {amt_str}")

        elif tool_name == "get_payment_record":
            amt = result.get("amount")
            self._print(f"← Payment amount: {format_currency(amt) if amt is not None else 'None'}")

        elif tool_name == "get_ledger_record":
            gross = result.get("gross_amount")
            fee = result.get("fee")
            self._print(f"← Ledger gross: {format_currency(gross)}, fee: {format_currency(fee)}")

        elif tool_name == "get_bank_records":
            count = result.get("count", 0)
            records = result.get("bank_records", [])
            self._print(f"← {count} bank record(s) found")
            for r in records:
                amt = r.get("credited_amount")
                self._print(f"← Credit: {format_currency(amt)}")

        elif tool_name == "check_for_duplicates":
            count = result.get("duplicate_count", 0)
            is_dup = result.get("is_duplicate", False)
            self._print(f"← {count} bank record(s) checked")
            self._print(f"← Duplicate: {'YES' if is_dup else 'NO'}")

        elif tool_name in ("calculate_expected_settlement", "calculate_adjusted_expected_settlement"):
            calc = result.get("calculation", "")
            adj_net = result.get("adjusted_expected_net") or result.get("expected_net")
            self._print(f"← Calculation: {calc}")
            if adj_net is not None:
                self._print(f"← Result: {format_currency(adj_net)}")
        else:
            self._print(f"← {str(result)[:120]}")

    # ------------------------------------------------------------------
    # Deterministic Finance Engine Events
    # ------------------------------------------------------------------

    def deterministic_calculation(self, items: Dict[str, Any], proven: bool = False) -> None:
        """
        Emits authoritative deterministic financial engine calculations.
        Clearly demonstrates that Python (not LLM) performs financial arithmetic.
        """
        if not self.enabled:
            return
        self._print("\n[FINANCE ENGINE | PYTHON]")
        for k, v in items.items():
            if isinstance(v, (int, float)):
                v_str = format_currency(v)
            else:
                v_str = str(v)
            self._print(f"→ {k}: {v_str}")
        if proven:
            self._print("✓ Equality proven")

    def evidence_sufficient(self, reasons: Optional[List[str]] = None) -> None:
        """Emits deterministic sufficiency check passing."""
        if not self.enabled:
            return
        self._print("\n[EVIDENCE CHECK | PYTHON]")
        self._print("✓ Sufficient deterministic evidence established")
        if reasons:
            for r in reasons:
                self._print(f"✓ {r}")

    def early_stop(self, role: str, tool_count: int, reason: str = "sufficient evidence established") -> None:
        """Emits early stopping event."""
        if not self.enabled:
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
        if not self.enabled:
            return
        prov_label = (provider or "DEMO").upper()
        self._print(f"\n[VERIFIER | {prov_label}]")
        if model:
            self._print(f"Model: {model}")
        self._print("→ Reviewing investigator proposal against source records")

    def verifier_review_result(self, provider: str, verified: bool, decision: str, reason: str, contradictions: Optional[List[str]] = None) -> None:
        """Emits the outcome of verifier evaluation."""
        if not self.enabled:
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
        if not self.enabled:
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
        if not self.enabled:
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
        if not self.enabled:
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
        if not self.enabled:
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
