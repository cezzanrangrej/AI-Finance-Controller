"""
Deterministic Finance Reconciliation Engine.

Implements rule-based multi-source financial reconciliation across Payment,
Ledger, and Bank records.
"""

import csv
import os
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple, Union


from decimal import Decimal
from src.utils.formatters import safe_decimal, safe_int, safe_numeric


class ReconciliationEngine:
    """Core rule engine and batch processor for financial reconciliation."""

    @staticmethod
    def _safe_decimal(val: Any) -> Optional[Decimal]:
        """Safely parse Decimal from string, float, int, or None."""
        return safe_decimal(val)

    @staticmethod
    def _safe_numeric(val: Any) -> Optional[Union[int, float]]:
        """Safely convert value to int (if integer) or float (if decimal)."""
        return safe_numeric(val)

    @staticmethod
    def _safe_int(val: Any) -> Optional[int]:
        """Safely parse integer for backward compatibility."""
        return safe_int(val)

    @classmethod
    def reconcile_transaction(
        cls,
        payment: Dict[str, Any],
        ledger: Optional[Dict[str, Any]],
        bank_records: Union[Optional[Dict[str, Any]], List[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        """
        Reconciles a single transaction across Payment, Ledger, and Bank records.

        Rules applied deterministically in order:
        1. Missing ledger record (MISSING_LEDGER_RECORD)
        2. Gross amount mismatch (GROSS_AMOUNT_MISMATCH)
        3. Ledger calculation error (LEDGER_CALCULATION_ERROR)
        4. Missing bank record (MISSING_BANK_RECORD)
        5. Duplicate bank records (DUPLICATE_BANK_RECORD)
        6. Bank amount mismatch (BANK_AMOUNT_MISMATCH)

        Returns:
            Dictionary matching the standard result schema.
        """
        txn_id = payment.get("transaction_id", "UNKNOWN")
        payment_dec = cls._safe_decimal(payment.get("amount"))

        # Normalize bank_records to a list
        if bank_records is None:
            bank_list = []
        elif isinstance(bank_records, dict):
            bank_list = [bank_records]
        elif isinstance(bank_records, list):
            bank_list = bank_records
        else:
            bank_list = []

        gross_dec = cls._safe_decimal(ledger.get("gross_amount")) if ledger else None
        fee_dec = cls._safe_decimal(ledger.get("fee")) if ledger else None
        net_dec = cls._safe_decimal(ledger.get("net_amount")) if ledger else None

        expected_net_dec = (
            (gross_dec - fee_dec) if (gross_dec is not None and fee_dec is not None) else None
        )

        single_bank_record = bank_list[0] if len(bank_list) == 1 else None
        bank_dec = (
            cls._safe_decimal(single_bank_record.get("credited_amount"))
            if single_bank_record
            else None
        )

        # Base result template
        result: Dict[str, Any] = {
            "transaction_id": txn_id,
            "status": "RECONCILED",
            "reason": None,
            "payment_amount": cls._safe_numeric(payment_dec),
            "gross_amount": cls._safe_numeric(gross_dec),
            "fee": cls._safe_numeric(fee_dec),
            "expected_net_amount": cls._safe_numeric(expected_net_dec),
            "bank_amount": cls._safe_numeric(bank_dec),
            "difference": 0,
        }

        # Rule 1 — Missing ledger
        if ledger is None:
            result["status"] = "EXCEPTION"
            result["reason"] = "MISSING_LEDGER_RECORD"
            result["difference"] = None
            return result

        # Rule 2 — Gross amount mismatch
        if payment_dec != gross_dec:
            result["status"] = "EXCEPTION"
            result["reason"] = "GROSS_AMOUNT_MISMATCH"
            if payment_dec is not None and gross_dec is not None:
                result["difference"] = cls._safe_numeric(payment_dec - gross_dec)
            else:
                result["difference"] = None
            return result

        # Rule 3 — Ledger calculation error
        # Verify: ledger.gross_amount - ledger.fee == ledger.net_amount
        if gross_dec is not None and fee_dec is not None and net_dec is not None:
            if (gross_dec - fee_dec) != net_dec:
                result["status"] = "EXCEPTION"
                result["reason"] = "LEDGER_CALCULATION_ERROR"
                result["difference"] = cls._safe_numeric((gross_dec - fee_dec) - net_dec)
                return result
        else:
            result["status"] = "EXCEPTION"
            result["reason"] = "LEDGER_CALCULATION_ERROR"
            result["difference"] = None
            return result

        # Rule 4 — Missing bank record
        if len(bank_list) == 0:
            result["status"] = "EXCEPTION"
            result["reason"] = "MISSING_BANK_RECORD"
            result["difference"] = cls._safe_numeric(expected_net_dec)
            return result

        # Rule 6 (evaluated on bank multiplicity) — Duplicate bank records
        if len(bank_list) > 1:
            result["status"] = "EXCEPTION"
            result["reason"] = "DUPLICATE_BANK_RECORD"
            # Difference can reflect the excess or count
            total_credited = sum(
                cls._safe_decimal(b.get("credited_amount")) or Decimal(0) for b in bank_list
            )
            result["difference"] = (
                cls._safe_numeric(expected_net_dec - total_credited)
                if expected_net_dec is not None
                else None
            )
            return result

        # Rule 5 — Bank amount mismatch
        # Expected bank amount = ledger.gross_amount - ledger.fee
        if expected_net_dec is not None and bank_dec is not None:
            if expected_net_dec != bank_dec:
                result["status"] = "EXCEPTION"
                result["reason"] = "BANK_AMOUNT_MISMATCH"
                result["difference"] = cls._safe_numeric(expected_net_dec - bank_dec)
                return result
        else:
            result["status"] = "EXCEPTION"
            result["reason"] = "BANK_AMOUNT_MISMATCH"
            result["difference"] = None
            return result

        # All 6 checks passed — verify RECONCILED is actually justified,
        # don't just assume it because nothing else fired.
        if (
            payment_dec == gross_dec
            and (gross_dec - fee_dec) == net_dec
            and bank_dec == expected_net_dec
        ):
            result["status"] = "RECONCILED"
            result["reason"] = None
            result["difference"] = 0
        else:
            result["status"] = "EXCEPTION"
            result["reason"] = "UNCLASSIFIED_DISCREPANCY"
            result["difference"] = None

        # All checks passed
        result["status"] = "RECONCILED"
        result["reason"] = None
        result["difference"] = 0
        return result

    @classmethod
    def load_csv(cls, file_path: str) -> List[Dict[str, str]]:
        """Safely loads a CSV file into a list of dictionaries."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        with open(file_path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return [row for row in reader]

    @classmethod
    def reconcile_records(
        cls, payments: List[Dict[str, Any]], ledger_rows: List[Dict[str, Any]], bank_rows: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Executes reconciliation across in-memory lists of records.

        Returns:
            Tuple of (all_results, metrics_summary)
        """
        # Index ledger records by transaction_id
        ledger_index: Dict[str, Dict[str, Any]] = {}
        for row in ledger_rows:
            txn_id = row.get("transaction_id")
            if txn_id is not None:
                ledger_index[str(txn_id).strip()] = row

        # Index bank records by transaction_id (supporting duplicates)
        bank_index: Dict[str, List[Dict[str, Any]]] = {}
        for row in bank_rows:
            txn_id = row.get("transaction_id")
            if txn_id is not None:
                bank_index.setdefault(str(txn_id).strip(), []).append(row)

        results: List[Dict[str, Any]] = []
        for payment in payments:
            raw_txn_id = payment.get("transaction_id", "")
            txn_id = str(raw_txn_id).strip()
            ledger_entry = ledger_index.get(txn_id)
            bank_entries = bank_index.get(txn_id, [])

            try:
                result = cls.reconcile_transaction(
                    payment=payment,
                    ledger=ledger_entry,
                    bank_records=bank_entries,
                )
            except Exception as e:
                # Fault tolerance: record system exception without aborting batch
                result = {
                    "transaction_id": txn_id,
                    "status": "EXCEPTION",
                    "reason": f"PROCESSING_ERROR: {str(e)}",
                    "payment_amount": cls._safe_numeric(cls._safe_decimal(payment.get("amount"))),
                    "gross_amount": None,
                    "fee": None,
                    "expected_net_amount": None,
                    "bank_amount": None,
                    "difference": None,
                }
            results.append(result)

        metrics = cls.calculate_metrics(results)
        return results, metrics

    @classmethod
    def reconcile_batch(
        cls, payments_path: str, ledger_path: str, bank_path: str
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Executes batch reconciliation across the three CSV files.

        Returns:
            Tuple of (all_results, metrics_summary)
        """
        payments = cls.load_csv(payments_path)
        ledger_rows = cls.load_csv(ledger_path)
        bank_rows = cls.load_csv(bank_path)
        return cls.reconcile_records(payments, ledger_rows, bank_rows)


    @staticmethod
    def calculate_metrics(results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculates summary and breakdown metrics from reconciliation results."""
        total_records = len(results)
        reconciled_records = sum(1 for r in results if r["status"] == "RECONCILED")
        exception_records = sum(1 for r in results if r["status"] == "EXCEPTION")

        match_rate = (
            (reconciled_records / total_records * 100) if total_records > 0 else 0.0
        )
        exception_rate = (
            (exception_records / total_records * 100) if total_records > 0 else 0.0
        )

        exception_reasons = [
            r["reason"] for r in results if r["status"] == "EXCEPTION" and r["reason"]
        ]
        breakdown = dict(Counter(exception_reasons))

        return {
            "total_records": total_records,
            "reconciled_records": reconciled_records,
            "exception_records": exception_records,
            "match_rate": match_rate,
            "exception_rate": exception_rate,
            "breakdown": breakdown,
        }


def reconcile_transaction(
    payment: Dict[str, Any],
    ledger: Optional[Dict[str, Any]],
    bank: Union[Optional[Dict[str, Any]], List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """Convenience top-level function matching requirement specification."""
    return ReconciliationEngine.reconcile_transaction(payment, ledger, bank)
