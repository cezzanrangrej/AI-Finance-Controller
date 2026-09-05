# Finance Test Dataset 02

Second synthetic test dataset for the AI Finance Controller.

- 100 payment transactions
- 85 transactions have no injected exception
- 15 transactions contain deliberate reconciliation exceptions
- 7 exceptions are explainable with documented adjustments
- 8 exceptions should remain HUMAN_REVIEW
- Duplicate bank records, missing records, and unexplained mismatches are included
- Deterministic generation seed: 20260826

Files:
- payments.csv
- ledger.csv
- bank.csv
- adjustments.csv
- ground_truth.csv

This dataset is intended for upload/validation testing and should not replace the
project's canonical demo dataset.
