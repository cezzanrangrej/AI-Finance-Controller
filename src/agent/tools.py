"""
Deterministic financial tools available to the AI agent.

All tools are READ-ONLY. No tool may modify payment, ledger, bank, or adjustment records.
The agent must request information through these explicit interfaces.
"""

from typing import Any, Dict, List, Optional


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
        # Index payment records — one per transaction
        self._payments: Dict[str, Dict[str, Any]] = {}
        for row in payments:
            txn_id = row.get("transaction_id")
            if txn_id:
                self._payments[txn_id] = row

        # Index ledger records — one per transaction
        self._ledger: Dict[str, Dict[str, Any]] = {}
        for row in ledger_records:
            txn_id = row.get("transaction_id")
            if txn_id:
                self._ledger[txn_id] = row

        # Index bank records — multiple allowed per transaction
        self._bank: Dict[str, List[Dict[str, Any]]] = {}
        for row in bank_records:
            txn_id = row.get("transaction_id")
            if txn_id:
                self._bank.setdefault(txn_id, []).append(row)

        # Index adjustments — multiple allowed per transaction
        self._adjustments: Dict[str, List[Dict[str, Any]]] = {}
        if adjustments:
            for row in adjustments:
                txn_id = row.get("transaction_id")
                if txn_id:
                    self._adjustments.setdefault(txn_id, []).append(row)

    @staticmethod
    def _safe_int(val: Any) -> Optional[int]:
        """Safely convert a value to int."""
        if val is None or val == "":
            return None
        try:
            return int(float(val))
        except (ValueError, TypeError):
            return None

    # ------------------------------------------------------------------
    # Public tools (called by the agent via function-calling)
    # ------------------------------------------------------------------

    def get_transaction(self, transaction_id: str) -> Dict[str, Any]:
        """
        Returns all known records for a transaction across all sources.

        Returns:
            Dict with keys 'payment', 'ledger', 'bank_records', 'adjustments'.
        """
        return {
            "transaction_id": transaction_id,
            "payment": self._payments.get(transaction_id),
            "ledger": self._ledger.get(transaction_id),
            "bank_records": self._bank.get(transaction_id, []),
            "adjustments": self._adjustments.get(transaction_id, []),
        }

    def get_payment_record(self, transaction_id: str) -> Optional[Dict[str, Any]]:
        """Returns the payment gateway record for a transaction."""
        record = self._payments.get(transaction_id)
        if record is None:
            return {"error": f"No payment record found for {transaction_id}"}
        return {
            "transaction_id": record.get("transaction_id"),
            "merchant_id": record.get("merchant_id"),
            "amount": self._safe_int(record.get("amount")),
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
            "gross_amount": self._safe_int(record.get("gross_amount")),
            "fee": self._safe_int(record.get("fee")),
            "net_amount": self._safe_int(record.get("net_amount")),
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
                    "credited_amount": self._safe_int(r.get("credited_amount")),
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
                    "amount": self._safe_int(r.get("amount")),
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

        gross = self._safe_int(record.get("gross_amount"))
        fee = self._safe_int(record.get("fee"))

        if gross is None or fee is None:
            return {"error": "Ledger gross_amount or fee is None"}

        expected_net = gross - fee
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

        gross = self._safe_int(record.get("gross_amount"))
        fee = self._safe_int(record.get("fee"))

        if gross is None or fee is None:
            return {"error": "Ledger gross_amount or fee is None"}

        base_expected = gross - fee
        adj_records = self._adjustments.get(transaction_id, [])
        total_adj = sum(self._safe_int(r.get("amount")) or 0 for r in adj_records)
        adjusted_expected = base_expected - total_adj

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
            "credited_amounts": [self._safe_int(r.get("credited_amount")) for r in records],
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
                    "description": "Returns all known records for a transaction across payment, ledger, bank, and adjustments.",
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
                    "description": "Returns the payment gateway record for a transaction.",
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
                    "description": "Returns the internal finance ledger record for a transaction.",
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
                    "description": "Returns ALL bank statement records for a transaction, including any duplicates.",
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
                    "description": "Returns legitimate settlement adjustment records (e.g. bank fees, adjustments) for a transaction.",
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
                    "description": "Deterministically calculates the base bank settlement amount using gross_amount - fee.",
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
                    "description": "Deterministically calculates expected bank settlement considering fee and total adjustments.",
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
                    "description": "Checks whether multiple bank records exist for the same transaction ID.",
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
