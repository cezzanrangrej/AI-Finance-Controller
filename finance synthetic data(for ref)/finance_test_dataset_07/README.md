# Finance Test Dataset 07

**Dataset name:** Finance Test Dataset 07  
**Records:** 100  
**Synthetic:** YES

Synthetic-only financial reconciliation test data for an AI Finance Controller. No real customer, account, banking, or payment information is used.

## Files
- `payments.csv` — synthetic payment transactions.
- `ledger.csv` — synthetic ledger gross amounts, fees, net amounts, and dates.
- `bank.csv` — synthetic bank settlement records.
- `adjustments.csv` — documented adjustments for selected discrepancies.
- `ground_truth.csv` — expected reconciliation and phase-2 outcomes.
- `README.md` — dataset documentation.

## Intended Exception Distribution

Exactly 13 of 100 transactions are exceptions:
- 3 adjustment-backed discrepancies — `AUTO_RESOLVED`
- 2 missing ledger records — `HUMAN_REVIEW`
- 2 missing bank records — `HUMAN_REVIEW`
- 2 duplicate bank records — `HUMAN_REVIEW`
- 2 unexplained bank amount mismatches — `HUMAN_REVIEW`
- 2 ledger calculation errors — `HUMAN_REVIEW`

The remaining 87 transactions are intended to reconcile cleanly.

All monetary values use exactly two decimal places and include many fractional amounts. Dates are valid ISO `YYYY-MM-DD` dates.

This dataset is synthetic and intended for testing only.
