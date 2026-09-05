# Finance Test Dataset 04

Synthetic upload-testing dataset for the AI Finance Controller.

- 20 payment transactions
- 12 intentionally injected Phase-1 exception transactions
- 5 adjustment-backed cases
- 7 cases intended for AUTO_RESOLVED
- 5 cases intended for HUMAN_REVIEW
- 8 clean/reconciled transactions
- Generation seed: 20260905

Files:
- payments.csv
- ledger.csv
- bank.csv
- adjustments.csv
- ground_truth.csv

Ground-truth distribution:
- AUTO_RESOLVED: 7
- HUMAN_REVIEW: 5

Adjustment-backed transactions:
TEST4_009, TEST4_010, TEST4_011, TEST4_012, TEST4_013

Note:
The two non-adjustment auto-resolvable cases (TEST4_014 and TEST4_015) use identical duplicate bank entries as a deterministic duplicate scenario. Verify the observed Phase-1 exception set and Phase-2 decisions against the current project engine before using this dataset for benchmark claims.
