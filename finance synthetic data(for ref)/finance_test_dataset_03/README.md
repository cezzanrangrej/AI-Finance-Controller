# Finance Test Dataset 03

Synthetic upload-testing dataset for the AI Finance Controller.

* 100 payment transactions
* 18 intentionally injected exception transactions
* 6 adjustment-backed cases intended to be AUTO\_RESOLVED
* 14 cases intended for HUMAN\_REVIEW
* Generation seed: 20260827

Files:

* payments.csv
* ledger.csv
* bank.csv
* adjustments.csv
* ground\_truth.csv

IMPORTANT:
This dataset is intended for upload/UI testing. Verify the observed exception
counts against the project's actual reconciliation engine before using it for
benchmark claims.

