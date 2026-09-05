# Finance Test Dataset 06

**Dataset name:** Finance Test Dataset 06  
**Records:** 100  
**Synthetic:** YES

Synthetic-only reconciliation test data for an AI Finance Controller. No real customer, account, banking, or payment information is used.

## Files
- `payments.csv` — synthetic payment source records.
- `ledger.csv` — gross amount, fee, net amount, and date.
- `bank.csv` — synthetic settlement records and bank references.
- `adjustments.csv` — documented adjustments for selected discrepancies.
- `ground_truth.csv` — expected reconciliation and investigation outcomes.
- `README.md` — dataset documentation.

## Intended Exception Distribution
Exactly 23 exceptions:
- 5 adjustment-backed discrepancies — `AUTO_RESOLVED`
- 4 missing ledger records — `HUMAN_REVIEW`
- 3 missing bank records — `HUMAN_REVIEW`
- 3 duplicate bank records — `HUMAN_REVIEW`
- 4 unexplained bank amount mismatches — `HUMAN_REVIEW`
- 4 ledger calculation errors — `HUMAN_REVIEW`

The remaining 77 transactions are clean/reconciled.

All monetary values use two decimal places, with many fractional amounts. Dates are valid ISO `YYYY-MM-DD` dates. This dataset is synthetic and intended for testing only.
