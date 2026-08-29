# Test Dataset 02 - Synthetic Financial Data

This synthetic dataset provides a secondary test suite for multi-source financial reconciliation and LLM exception investigation within the AI Finance Controller.

## Overview & Distribution Comparison

Unlike the canonical dataset (`data/`), this dataset contains an altered exception distribution designed to test reconciliation engine robustness, edge cases, and agent investigation accuracy under higher exception density.

| Metric / Exception Category | Canonical Dataset (`data/`) | Test Dataset 02 (`data/test_dataset_02/`) |
| :--- | :--- | :--- |
| **Total Transactions** | 100 | 100 |
| **Reconciled Records** | 70 (70.0%) | 55 (55.0%) |
| **Total Exceptions** | 30 (30.0%) | 45 (45.0%) |
| `GROSS_AMOUNT_MISMATCH` | 10 | 12 |
| `MISSING_LEDGER_RECORD` | 5 | 8 |
| `MISSING_BANK_RECORD` | 5 | 7 |
| `BANK_AMOUNT_MISMATCH` | 4 | 9 |
| `DUPLICATE_BANK_RECORD` | 3 | 5 |
| `LEDGER_CALCULATION_ERROR` | 3 | 4 |

## Phase 2 Ground Truth Breakdown

| Decision Category | Count | Percentage |
| :--- | :--- | :--- |
| `N/A` (Reconciled transactions) | 55 | 55% |
| `AUTO_RESOLVED` (Documented in adjustments) | 11 | 11% |
| `HUMAN_REVIEW` (Unexplained discrepancies / structural errors) | 34 | 34% |
| **Total** | 100 | 100% |

- **Auto-Resolvable Exceptions (11 total)**:
  - 6 `GROSS_AMOUNT_MISMATCH` cases explained by `GROSS_INVOICE_ADJUSTMENT` entries in `adjustments.csv`.
  - 5 `BANK_AMOUNT_MISMATCH` cases explained by `BANK_PROCESSING_FEE` or `SETTLEMENT_ADJUSTMENT` entries in `adjustments.csv`.

## File Schemas

### 1. `payments.csv` (100 rows)
- `transaction_id`: Unique transaction identifier (`TXN001` - `TXN100`)
- `merchant_id`: Identifier for the merchant (`M001` - `M020`)
- `amount`: Base transaction amount in integer currency units (₹)
- `date`: Transaction capture date (`YYYY-MM-DD`)
- `status`: Payment status (`CAPTURED`)

### 2. `ledger.csv` (92 rows)
- `transaction_id`: Transaction identifier (8 transactions omitted to simulate missing ledger records)
- `gross_amount`: Invoiced gross amount
- `fee`: Payment processor fee
- `net_amount`: Calculated net settlement amount (`gross_amount - fee`, with intentional calculation errors injected on 4 records)
- `date`: Posting date (`YYYY-MM-DD`)
- `status`: Ledger entry status (`POSTED`)

### 3. `bank.csv` (98 rows)
- `bank_reference`: Unique bank statement transaction reference (`BNK_REF_0001` - `BNK_REF_0098`)
- `transaction_id`: Associated transaction ID (7 transactions omitted for missing bank records, 5 transactions appear twice for duplicate bank records)
- `credited_amount`: Net settlement credited to merchant bank account
- `date`: Settlement date (`YYYY-MM-DD`)

### 4. `adjustments.csv` (11 rows)
- `transaction_id`: Transaction ID reference
- `adjustment_type`: Type of adjustment (`GROSS_INVOICE_ADJUSTMENT`, `BANK_PROCESSING_FEE`, `SETTLEMENT_ADJUSTMENT`)
- `amount`: Adjustment value
- `reason`: Explanatory description
- `date`: Adjustment posting date (`YYYY-MM-DD`)
- `reference`: Adjustment reference code (`ADJ001` - `ADJ011`)

### 5. `ground_truth.csv` (100 rows)
- `transaction_id`: Transaction ID
- `expected_phase1_status`: `RECONCILED` or `EXCEPTION`
- `expected_phase1_exception`: Specific Phase 1 rule or empty if reconciled
- `expected_phase2_decision`: `AUTO_RESOLVED`, `HUMAN_REVIEW`, or `N/A`
- `expected_status`: Alias for `expected_phase1_status`
- `expected_exception`: Alias for `expected_phase1_exception`

## Generation & Verification Methodology

Generated using the project's standard `SyntheticDataGenerator` (`src/generator.py`) and verified against the deterministic `ReconciliationEngine` (`src/reconciliation.py`).
