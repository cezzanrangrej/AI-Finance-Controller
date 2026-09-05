# Finance Test Dataset 05

**Dataset name:** Finance Test Dataset 05  
**Records:** 100  
**Synthetic:** YES

## Description

This dataset contains 100 fully synthetic payment transactions designed to test an AI Finance Controller's multi-source financial reconciliation and exception investigation workflow. It includes payments, ledger settlements, bank credits, documented adjustments, and ground-truth labels.

No real customer, account, or payment information is used. All values, references, and dates are synthetic.

## Files

- `payments.csv` — source payment transactions with transaction ID, amount, and date.
- `ledger.csv` — synthetic ledger records containing gross amount, processing fee, calculated net amount, and date.
- `bank.csv` — synthetic bank settlement records with unique bank references and credited amounts.
- `adjustments.csv` — documented settlement adjustments explaining selected bank discrepancies.
- `ground_truth.csv` — expected phase-1 reconciliation status, exception category, and phase-2 decision.
- `README.md` — dataset documentation.

## Intended Exception Distribution

Exactly 15 of the 100 transactions are intentionally anomalous:

- 4 adjustment-backed discrepancies — expected phase-2 decision: `AUTO_RESOLVED`
- 3 missing ledger records — `HUMAN_REVIEW`
- 2 missing bank records — `HUMAN_REVIEW`
- 2 duplicate bank records — `HUMAN_REVIEW`
- 2 unexplained bank amount mismatches — `HUMAN_REVIEW`
- 2 ledger calculation errors — `HUMAN_REVIEW`

The remaining 85 transactions are intended to reconcile cleanly.

## Adjustment Cases

Four transactions contain documented settlement adjustments. For these cases, the bank credited amount is intentionally lower than the expected ledger settlement by the documented adjustment amount. The adjustment is intended to explain the discrepancy without contradiction.

## Data Quality

- Exactly 100 unique payment transaction IDs: `TEST5_001` through `TEST5_100`.
- Required fields are populated.
- Dates use ISO `YYYY-MM-DD` format.
- Monetary values use exactly two decimal places.
- Fractional amounts are intentionally common.
- Missing ledger and bank records occur only in their designated exception cases.
- Duplicate bank records occur only in the two designated duplicate cases.
- Every adjustment references an existing payment transaction.
- Every `ground_truth.csv` row references an existing payment transaction.

## Testing Only

This dataset is **synthetic and intended for testing only**. It must not be interpreted as real financial, customer, banking, or payment data.
