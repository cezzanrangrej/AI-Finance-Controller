"""
Deterministic financial tools available to the AI agent.

All tools are READ-ONLY. No tool may modify payment, ledger, bank, or adjustment records.
The agent must request information through these explicit interfaces.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Union
from src.utils.formatters import safe_decimal, safe_int, safe_numeric


class FinancialToolkit:
    """
    Read-only toolkit for investigating financial transactions.

    Built from in-memory indexes of payment, ledger, bank, and adjustment records.
    """

    def __init__(
        self,
        payments: List[Dict[str, Any]],
        ledger_records: List[Dict[str, Any]],
        bank_records: List[Dict[str, Any]],
        adjustments: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """
        Initialises the toolkit from pre-loaded record lists.

        Args:
            payments: All payment records.
            ledger_records: All ledger records.
            bank_records: All bank records (including duplicates).
            adjustments: Optional list of adjustment records.
        """
        # Index payment records — one per transaction (normalized)
        self._payments: Dict[str, Dict[str, Any]] = {}
        for row in payments:
            raw_txn_id = row.get("transaction_id")
            if raw_txn_id is not None:
                txn_id = str(raw_txn_id).strip()
                self._payments[txn_id] = {
                    "transaction_id": txn_id,
                    "merchant_id": row.get("merchant_id"),
                    "amount": self._safe_numeric(row.get("amount")),
                    "date": row.get("date"),
                    "status": row.get("status"),
                }

        # Index ledger records — one per transaction (normalized)
        self._ledger: Dict[str, Dict[str, Any]] = {}
        for row in ledger_records:
            raw_txn_id = row.get("transaction_id")
            if raw_txn_id is not None:
                txn_id = str(raw_txn_id).strip()
                self._ledger[txn_id] = {
                    "transaction_id": txn_id,
                    "gross_amount": self._safe_numeric(row.get("gross_amount")),
                    "fee": self._safe_numeric(row.get("fee")),
                    "net_amount": self._safe_numeric(row.get("net_amount")),
                    "date": row.get("date"),
                    "status": row.get("status"),
                }

        # Index bank records — multiple allowed per transaction (normalized)
        self._bank: Dict[str, List[Dict[str, Any]]] = {}
        for row in bank_records:
            raw_txn_id = row.get("transaction_id")
            if raw_txn_id is not None:
                txn_id = str(raw_txn_id).strip()
                self._bank.setdefault(txn_id, []).append({
                    "bank_reference": row.get("bank_reference"),
                    "transaction_id": txn_id,
                    "credited_amount": self._safe_numeric(row.get("credited_amount")),
                    "date": row.get("date"),
                })

        # Index adjustments — multiple allowed per transaction (normalized)
        self._adjustments: Dict[str, List[Dict[str, Any]]] = {}
        if adjustments:
            for row in adjustments:
                raw_txn_id = row.get("transaction_id")
                if raw_txn_id is not None:
                    txn_id = str(raw_txn_id).strip()
                    self._adjustments.setdefault(txn_id, []).append({
                        "adjustment_type": row.get("adjustment_type"),
                        "amount": self._safe_numeric(row.get("amount")),
                        "reason": row.get("reason"),
                        "date": row.get("date"),
                        "reference": row.get("reference"),
                        "transaction_id": txn_id,
                    })

    @staticmethod
    def _safe_decimal(val: Any) -> Optional[Decimal]:
        """Safely convert a value to Decimal."""
        return safe_decimal(val)

    @staticmethod
    def _safe_numeric(val: Any) -> Optional[Union[int, float]]:
        """Safely convert a value to numeric (int if whole, float if decimal)."""
        return safe_numeric(val)

    @staticmethod
    def _safe_int(val: Any) -> Optional[int]:
        """Safely convert a value to int."""
        return safe_int(val)

    # ------------------------------------------------------------------
    # Public tools (called by the agent via function-calling)
    # ------------------------------------------------------------------

    def get_transaction(self, transaction_id: str) -> Dict[str, Any]:
        """
        Returns all known records for a transaction across all sources.

        Returns:
            Dict with keys 'payment', 'ledger', 'bank_records', 'adjustments'.
        """
        p = self._payments.get(transaction_id)
        l = self._ledger.get(transaction_id)
        b = self._bank.get(transaction_id, [])
        a = self._adjustments.get(transaction_id, [])
        return {
            "transaction_id": transaction_id,
            "payment": dict(p) if p else None,
            "ledger": dict(l) if l else None,
            "bank_records": [dict(r) for r in b],
            "adjustments": [dict(r) for r in a],
        }

    def get_payment_record(self, transaction_id: str) -> Optional[Dict[str, Any]]:
        """Returns the payment gateway record for a transaction."""
        record = self._payments.get(transaction_id)
        if record is None:
            return {"error": f"No payment record found for {transaction_id}"}
        return {
            "transaction_id": record.get("transaction_id"),
            "merchant_id": record.get("merchant_id"),
            "amount": self._safe_numeric(record.get("amount")),
            "date": record.get("date"),
            "status": record.get("status"),
        }

    def get_ledger_record(self, transaction_id: str) -> Optional[Dict[str, Any]]:
        """Returns the internal finance ledger record for a transaction."""
        record = self._ledger.get(transaction_id)
        if record is None:
            return {"error": f"No ledger record found for {transaction_id}"}
        return {
            "transaction_id": record.get("transaction_id"),
            "gross_amount": self._safe_numeric(record.get("gross_amount")),
            "fee": self._safe_numeric(record.get("fee")),
            "net_amount": self._safe_numeric(record.get("net_amount")),
            "date": record.get("date"),
            "status": record.get("status"),
        }

    def get_bank_records(self, transaction_id: str) -> Dict[str, Any]:
        """Returns ALL bank records for a transaction, including any duplicates."""
        records = self._bank.get(transaction_id, [])
        return {
            "transaction_id": transaction_id,
            "count": len(records),
            "bank_records": [
                {
                    "bank_reference": r.get("bank_reference"),
                    "transaction_id": r.get("transaction_id"),
                    "credited_amount": self._safe_numeric(r.get("credited_amount")),
                    "date": r.get("date"),
                }
                for r in records
            ],
        }

    def get_adjustments(self, transaction_id: str) -> Dict[str, Any]:
        """
        Returns all legitimate settlement adjustment records for a transaction.

        Returns:
            Dict with count and list of adjustment records.
        """
        records = self._adjustments.get(transaction_id, [])
        return {
            "transaction_id": transaction_id,
            "count": len(records),
            "adjustments": [
                {
                    "adjustment_type": r.get("adjustment_type"),
                    "amount": self._safe_numeric(r.get("amount")),
                    "reason": r.get("reason"),
                    "date": r.get("date"),
                    "reference": r.get("reference"),
                }
                for r in records
            ],
        }

    def calculate_expected_settlement(self, transaction_id: str) -> Dict[str, Any]:
        """
        Deterministically calculates base expected settlement amount (gross - fee).

        Formula: expected_net = gross_amount - fee
        """
        record = self._ledger.get(transaction_id)
        if record is None:
            return {"error": f"No ledger record found for {transaction_id}"}

        gross_dec = self._safe_decimal(record.get("gross_amount"))
        fee_dec = self._safe_decimal(record.get("fee"))

        if gross_dec is None or fee_dec is None:
            return {"error": "Ledger gross_amount or fee is None"}

        expected_net_dec = gross_dec - fee_dec
        gross = self._safe_numeric(gross_dec)
        fee = self._safe_numeric(fee_dec)
        expected_net = self._safe_numeric(expected_net_dec)
        return {
            "transaction_id": transaction_id,
            "gross_amount": gross,
            "fee": fee,
            "expected_net": expected_net,
            "calculation": f"{gross} - {fee} = {expected_net}",
        }

    def calculate_adjusted_expected_settlement(self, transaction_id: str) -> Dict[str, Any]:
        """
        Deterministically calculates expected settlement taking into account adjustments.

        Formula: expected_adjusted_net = gross_amount - fee - total_adjustments
        """
        record = self._ledger.get(transaction_id)
        if record is None:
            return {"error": f"No ledger record found for {transaction_id}"}

        gross_dec = self._safe_decimal(record.get("gross_amount"))
        fee_dec = self._safe_decimal(record.get("fee"))

        if gross_dec is None or fee_dec is None:
            return {"error": "Ledger gross_amount or fee is None"}

        base_expected_dec = gross_dec - fee_dec
        adj_records = self._adjustments.get(transaction_id, [])
        total_adj_dec = sum(
            (self._safe_decimal(r.get("amount")) or Decimal(0)) for r in adj_records
        )
        adjusted_expected_dec = base_expected_dec - total_adj_dec

        gross = self._safe_numeric(gross_dec)
        fee = self._safe_numeric(fee_dec)
        base_expected = self._safe_numeric(base_expected_dec)
        total_adj = self._safe_numeric(total_adj_dec)
        adjusted_expected = self._safe_numeric(adjusted_expected_dec)

        return {
            "transaction_id": transaction_id,
            "gross_amount": gross,
            "fee": fee,
            "base_expected_net": base_expected,
            "total_adjustments": total_adj,
            "adjusted_expected_net": adjusted_expected,
            "calculation": f"{gross} - {fee} - {total_adj} = {adjusted_expected}",
        }

    def check_for_duplicates(self, transaction_id: str) -> Dict[str, Any]:
        """Checks whether multiple bank records exist for the given transaction ID."""
        records = self._bank.get(transaction_id, [])
        return {
            "transaction_id": transaction_id,
            "duplicate_count": len(records),
            "is_duplicate": len(records) > 1,
            "bank_references": [r.get("bank_reference") for r in records],
            "credited_amounts": [self._safe_numeric(r.get("credited_amount")) for r in records],
        }

    def verify_discrepancy(self, transaction_id: str) -> Dict[str, Any]:
        """
        Deterministically evaluates whether documented adjustments explain amount discrepancies.
        Pre-computes exact comparison flags so the agent never performs arithmetic or comparisons.

        Both adjustment directions are tested (expected settlement minus *and* plus the
        documented adjustment); ``resolved_direction`` reports which one balanced.
        """
        payment = self._payments.get(transaction_id)
        ledger = self._ledger.get(transaction_id)
        bank_records = self._bank.get(transaction_id, [])
        adjustments = self._adjustments.get(transaction_id, [])

        p_dec = self._safe_decimal(payment.get("amount")) if payment else None
        gross_dec = self._safe_decimal(ledger.get("gross_amount")) if ledger else None
        fee_dec = self._safe_decimal(ledger.get("fee")) if ledger else None
        net_dec = self._safe_decimal(ledger.get("net_amount")) if ledger else None

        expected_net_dec = (gross_dec - fee_dec) if (gross_dec is not None and fee_dec is not None) else None
        single_bank = bank_records[0] if len(bank_records) == 1 else None
        bank_dec = self._safe_decimal(single_bank.get("credited_amount")) if single_bank else None

        adj_dec = sum((self._safe_decimal(a.get("amount")) or Decimal(0)) for a in adjustments)
        adj_count = len(adjustments)

        is_duplicate = len(bank_records) > 1

        bank_explained = False
        gross_explained = False
        explanation = ""
        resolved_diff = None
        resolved_direction = None

        # An adjustment record documents a magnitude, not a signed direction. A TDS
        # deduction or chargeback lowers the settlement; a rebate credit or
        # reimbursement raises it, and both are filed as a positive amount. Testing
        # subtraction only left every additive adjustment looking unexplained, so
        # both directions are evaluated and whichever lands exactly on the actual
        # figure is the one reported. Neither matching still means unexplained.
        bank_comparable = expected_net_dec is not None and bank_dec is not None and adj_dec > 0
        bank_subtract = bank_comparable and (expected_net_dec - adj_dec) == bank_dec
        bank_add = bank_comparable and (expected_net_dec + adj_dec) == bank_dec

        # Same test from the gross side: payment == ledger gross -/+ adjustment.
        gross_comparable = p_dec is not None and gross_dec is not None and adj_dec > 0
        gross_subtract = gross_comparable and (gross_dec - adj_dec) == p_dec
        gross_add = gross_comparable and (gross_dec + adj_dec) == p_dec

        if is_duplicate:
            explanation = f"Multiple ({len(bank_records)}) bank records found; requires human review."
        elif bank_subtract or bank_add:
            bank_explained = True
            resolved_diff = self._safe_numeric(adj_dec)
            resolved_direction = "SUBTRACT" if bank_subtract else "ADD"
            operator = "minus" if bank_subtract else "plus"
            applied = "subtractively" if bank_subtract else "additively"
            explanation = (
                f"Bank credit ({self._safe_numeric(bank_dec)}) exactly matches expected settlement "
                f"({self._safe_numeric(expected_net_dec)}) {operator} documented adjustments "
                f"({self._safe_numeric(adj_dec)}); the adjustment was applied {applied}."
            )
        elif gross_subtract or gross_add:
            gross_explained = True
            resolved_diff = self._safe_numeric(adj_dec)
            resolved_direction = "SUBTRACT" if gross_subtract else "ADD"
            operator = "-" if gross_subtract else "+"
            applied = "subtractively" if gross_subtract else "additively"
            explanation = (
                f"Gross discrepancy between payment ({self._safe_numeric(p_dec)}) and ledger "
                f"({self._safe_numeric(gross_dec)}) is exactly explained by adjustment of "
                f"{self._safe_numeric(adj_dec)} applied {applied} "
                f"(ledger gross {operator} adjustment = payment)."
            )
        elif expected_net_dec is not None and bank_dec is not None:
            diff = self._safe_numeric(expected_net_dec - bank_dec)
            explanation = f"Bank discrepancy of {diff} is not explained by documented adjustments in either direction (total: {self._safe_numeric(adj_dec)})."
        else:
            explanation = "Insufficient records to establish discrepancy explanation."

        ledger_calc_correct = (gross_dec - fee_dec == net_dec) if (gross_dec is not None and fee_dec is not None and net_dec is not None) else None

        return {
            "transaction_id": transaction_id,
            "discrepancy_fully_explained": bank_explained or gross_explained,
            "match_type": "BANK_ADJUSTMENT" if bank_explained else ("GROSS_ADJUSTMENT" if gross_explained else "NONE"),
            "resolved_difference": resolved_diff,
            "resolved_direction": resolved_direction,
            "is_duplicate_bank": is_duplicate,
            "bank_records_count": len(bank_records),
            "total_adjustments": self._safe_numeric(adj_dec),
            "adjustments_count": adj_count,
            "expected_settlement": self._safe_numeric(expected_net_dec),
            "bank_credited_amount": self._safe_numeric(bank_dec),
            "ledger_calculation_correct": ledger_calc_correct,
            "explanation": explanation,
        }

    def check_record_presence(self, transaction_id: str) -> Dict[str, Any]:
        """
        Deterministically checks presence and reference validity across all record sources.
        """
        p = self._payments.get(transaction_id)
        l = self._ledger.get(transaction_id)
        b = self._bank.get(transaction_id, [])
        a = self._adjustments.get(transaction_id, [])

        missing = []
        if not p:
            missing.append("PAYMENT")
        if not l:
            missing.append("LEDGER")
        if not b:
            missing.append("BANK")

        refs_valid = True
        for adj in a:
            ref = str(adj.get("reference") or adj.get("transaction_id") or "")
            if transaction_id not in ref and not ref.startswith("ADJ"):
                refs_valid = False

        return {
            "transaction_id": transaction_id,
            "has_payment": p is not None,
            "has_ledger": l is not None,
            "has_bank": len(b) > 0,
            "has_adjustments": len(a) > 0,
            "missing_records": missing,
            "bank_records_count": len(b),
            "adjustment_count": len(a),
            "adjustment_references_valid": refs_valid,
        }

    def check_date_consistency(self, transaction_id: str) -> Dict[str, Any]:
        """
        Deterministically verifies date alignment across transaction sources without LLM date math.
        """
        p = self._payments.get(transaction_id)
        l = self._ledger.get(transaction_id)
        b = self._bank.get(transaction_id, [])
        a = self._adjustments.get(transaction_id, [])

        def parse_date(d_str: Any) -> Optional[datetime]:
            if not d_str:
                return None
            for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
                try:
                    return datetime.strptime(str(d_str)[:10], fmt)
                except Exception:
                    continue
            return None

        p_date = parse_date(p.get("date")) if p else None
        l_date = parse_date(l.get("date")) if l else None
        b_dates = [parse_date(rec.get("date")) for rec in b if rec.get("date")]
        b_dates = [d for d in b_dates if d is not None]
        a_dates = [parse_date(rec.get("date")) for rec in a if rec.get("date")]
        a_dates = [d for d in a_dates if d is not None]

        max_delta_days = 0
        all_dates = [d for d in [p_date, l_date] + b_dates + a_dates if d is not None]
        if len(all_dates) >= 2:
            min_date = min(all_dates)
            max_date = max(all_dates)
            max_delta_days = (max_date - min_date).days

        dates_consistent = max_delta_days <= 30

        return {
            "transaction_id": transaction_id,
            "dates_consistent": dates_consistent,
            "payment_date": p.get("date") if p else None,
            "ledger_date": l.get("date") if l else None,
            "bank_dates": [r.get("date") for r in b if r.get("date")],
            "adjustment_dates": [r.get("date") for r in a if r.get("date")],
            "max_day_difference": max_delta_days,
            "details": f"All recorded event dates are within {max_delta_days} day(s)." if dates_consistent else f"Dates span {max_delta_days} days, exceeding typical settlement window.",
        }

    # ------------------------------------------------------------------
    # OpenAI function-calling schema (tool registry for LLM)
    # ------------------------------------------------------------------

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Returns OpenAI-compatible function definitions for all available tools."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_transaction",
                    "description": "Returns all known records for a transaction across payment, ledger, bank, and adjustments. Use this as an initial retrieval step.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "transaction_id": {"type": "string", "description": "The transaction ID."}
                        },
                        "required": ["transaction_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_payment_record",
                    "description": "Returns the payment gateway record (amount, merchant, status, date) for a transaction.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "transaction_id": {"type": "string", "description": "The transaction ID."}
                        },
                        "required": ["transaction_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_ledger_record",
                    "description": "Returns the internal finance ledger record (gross_amount, fee, net_amount) for a transaction.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "transaction_id": {"type": "string", "description": "The transaction ID."}
                        },
                        "required": ["transaction_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_bank_records",
                    "description": "Returns all bank records for the transaction, including duplicates. Use this when investigating missing, duplicate, or mismatched bank entries.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "transaction_id": {"type": "string", "description": "The transaction ID."}
                        },
                        "required": ["transaction_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_adjustments",
                    "description": "Retrieve all documented transaction-specific financial adjustments that may explain a mismatch between expected settlement and bank credit, or gross discrepancies. Use this tool for amount discrepancies, especially BANK_AMOUNT_MISMATCH and GROSS_AMOUNT_MISMATCH. Do not assume an adjustment exists; retrieve the records and inspect them.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "transaction_id": {"type": "string", "description": "The transaction ID."}
                        },
                        "required": ["transaction_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "calculate_expected_settlement",
                    "description": "Deterministically calculates base expected settlement amount (gross_amount - fee). This tool performs authoritative arithmetic. Do not calculate the result yourself.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "transaction_id": {"type": "string", "description": "The transaction ID."}
                        },
                        "required": ["transaction_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "calculate_adjusted_expected_settlement",
                    "description": "Deterministically calculates the expected bank credit after applying the documented ledger fee and transaction-specific adjustments. Use this tool after retrieving adjustments. This tool performs authoritative arithmetic. Do not calculate the result yourself.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "transaction_id": {"type": "string", "description": "The transaction ID."}
                        },
                        "required": ["transaction_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "check_for_duplicates",
                    "description": "Checks whether multiple bank records exist for the transaction ID. Use this when a transaction may have duplicate bank records.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "transaction_id": {"type": "string", "description": "The transaction ID."}
                        },
                        "required": ["transaction_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "verify_discrepancy",
                    "description": "Deterministically evaluates whether documented adjustments mathematically explain the discrepancy for BANK_AMOUNT_MISMATCH or GROSS_AMOUNT_MISMATCH, and checks ledger calculation integrity. Always use this tool rather than computing or comparing numbers yourself.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "transaction_id": {"type": "string", "description": "The transaction ID."}
                        },
                        "required": ["transaction_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "check_record_presence",
                    "description": "Deterministically checks which records exist across payment, ledger, and bank, and verifies adjustment reference validity.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "transaction_id": {"type": "string", "description": "The transaction ID."}
                        },
                        "required": ["transaction_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "check_date_consistency",
                    "description": "Deterministically computes day deltas between payment, ledger, bank settlement, and adjustment dates without manual date math.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "transaction_id": {"type": "string", "description": "The transaction ID."}
                        },
                        "required": ["transaction_id"],
                    },
                },
            },
        ]

    def dispatch(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Dispatches a tool call by name with keyword arguments."""
        tool_map = {
            "get_transaction": self.get_transaction,
            "get_payment_record": self.get_payment_record,
            "get_ledger_record": self.get_ledger_record,
            "get_bank_records": self.get_bank_records,
            "get_adjustments": self.get_adjustments,
            "calculate_expected_settlement": self.calculate_expected_settlement,
            "calculate_adjusted_expected_settlement": self.calculate_adjusted_expected_settlement,
            "check_for_duplicates": self.check_for_duplicates,
            "verify_discrepancy": self.verify_discrepancy,
            "check_record_presence": self.check_record_presence,
            "check_date_consistency": self.check_date_consistency,
        }
        if tool_name not in tool_map:
            raise ValueError(f"Unknown tool: '{tool_name}'.")
        return tool_map[tool_name](**arguments)
