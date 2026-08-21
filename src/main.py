"""
Main CLI entry point for AI Finance Controller - Phase 1: Finance Logic.

Orchestrates data generation, batch reconciliation, metrics calculation,
and terminal reporting.
"""

import os
import sys
from typing import Any, Dict, List

# Ensure src module can be imported regardless of execution path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Set stdout/stderr to UTF-8 on Windows environments
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass


from src.generator import SyntheticDataGenerator
from src.reconciliation import ReconciliationEngine


def format_currency(val: Any) -> str:
    """Format an integer/float amount as Indian Rupee string."""
    if val is None:
        return "N/A"
    try:
        # Standard thousands comma separation
        return f"₹{val:,.0f}" if isinstance(val, (int, float)) else str(val)
    except Exception:
        return str(val)


def print_reconciliation_report(results: List[Dict[str, Any]], metrics: Dict[str, Any]) -> None:
    """Prints a formatted terminal report of reconciliation results."""
    print("========================================")
    print("       AI FINANCE CONTROLLER")
    print("       PHASE 1: RECONCILIATION")
    print("========================================\n")

    print(f"Records processed: {metrics['total_records']}")
    print(f"Reconciled:        {metrics['reconciled_records']}")
    print(f"Exceptions:        {metrics['exception_records']}")
    print(f"Match rate:        {metrics['match_rate']:.2f}%\n")

    print("----------------------------------------")
    print("EXCEPTION BREAKDOWN")
    print("----------------------------------------")
    # Sort breakdown by count descending
    sorted_breakdown = sorted(metrics["breakdown"].items(), key=lambda item: item[1], reverse=True)
    for reason, count in sorted_breakdown:
        print(f"{reason:<26} {count:>3}")
    print()

    print("----------------------------------------")
    print("EXCEPTION DETAILS")
    print("----------------------------------------\n")

    exceptions = [r for r in results if r["status"] == "EXCEPTION"]
    for ex in exceptions:
        txn_id = ex["transaction_id"]
        status = ex["status"]
        reason = ex["reason"]
        expected_val = format_currency(ex["expected_net_amount"])
        actual_val = format_currency(ex["bank_amount"])
        diff_val = format_currency(ex["difference"])

        print(f"{txn_id}")
        print(f"Status: {status}")
        print(f"Reason: {reason}")
        if reason == "MISSING_LEDGER_RECORD":
            print(f"Payment Amount: {format_currency(ex['payment_amount'])}")
            print("Ledger Entry:   Missing")
        elif reason == "GROSS_AMOUNT_MISMATCH":
            print(f"Payment Amount: {format_currency(ex['payment_amount'])}")
            print(f"Gross Amount:   {format_currency(ex['gross_amount'])}")
            print(f"Difference:     {diff_val}")
        elif reason == "LEDGER_CALCULATION_ERROR":
            print(f"Gross Amount:   {format_currency(ex['gross_amount'])}")
            print(f"Fee:            {format_currency(ex['fee'])}")
            print(f"Expected Net:   {expected_val}")
            print(f"Ledger Net:     {format_currency((ex['gross_amount'] or 0) - (ex['fee'] or 0) - (ex['difference'] or 0))}")
        elif reason == "MISSING_BANK_RECORD":
            print(f"Expected Bank Credit: {expected_val}")
            print("Bank Record:          Missing")
        elif reason == "DUPLICATE_BANK_RECORD":
            print(f"Expected:   {expected_val}")
            print("Bank Record: Duplicate entries found")
        elif reason == "BANK_AMOUNT_MISMATCH":
            print(f"Expected:   {expected_val}")
            print(f"Actual:     {actual_val}")
            print(f"Difference: {diff_val}")
        else:
            print(f"Expected:   {expected_val}")
            print(f"Actual:     {actual_val}")
            print(f"Difference: {diff_val}")
        print()


def main() -> None:
    """Executes synthetic data generation and batch reconciliation."""
    data_dir = os.path.join(project_root, "data")
    payments_path = os.path.join(data_dir, "payments.csv")
    ledger_path = os.path.join(data_dir, "ledger.csv")
    bank_path = os.path.join(data_dir, "bank.csv")

    # Generate synthetic data if missing or to ensure freshness
    generator = SyntheticDataGenerator(seed=42, total_transactions=100)
    generator.save_to_csv(data_dir)

    # Execute batch reconciliation
    results, metrics = ReconciliationEngine.reconcile_batch(
        payments_path=payments_path,
        ledger_path=ledger_path,
        bank_path=bank_path
    )

    # Print formatted CLI report
    print_reconciliation_report(results, metrics)


if __name__ == "__main__":
    main()
