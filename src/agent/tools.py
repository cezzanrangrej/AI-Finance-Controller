"""
Deterministic financial tools available to the AI agent.

All tools are READ-ONLY. No tool may modify payment, ledger, bank, or adjustment records.
The agent must request information through these explicit interfaces.
"""

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
        }
        if tool_name not in tool_map:
            raise ValueError(f"Unknown tool: '{tool_name}'.")
        return tool_map[tool_name](**arguments)
