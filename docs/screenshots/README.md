# Submission Screenshot Checklist & Capture Guide
## AI Finance Controller

This document details the 5 key visual evidence captures recommended for the buildathon submission, presentation slide deck, and repository documentation.

---

### Screenshot 1: Dashboard Overview (`01_dashboard_overview.png`)
- **Location**: `http://localhost:5173/`
- **What to Capture**:
  - Top metric cards showing:
    - Total Processed: `100`
    - Initial Reconciled: `70`
    - Initial Match Rate: `70.0%`
    - AI Auto-Resolved: `8`
    - Human Review Required: `22`
  - Active run summary and filter tabs (`ALL`, `RECONCILED`, `EXCEPTIONS`).
  - Clean Dark Mode UI with Lucide icon indicators.

---

### Screenshot 2: Auto-Resolved Transaction Detail (`02_auto_resolved_detail.png`)
- **Location**: Click on transaction `TXN003` in the dashboard table.
- **What to Capture**:
  - Discrepancy details: Bank credited ₹14,110 vs Expected ₹14,210 (`BANK_AMOUNT_MISMATCH`).
  - Decision badge: **`AUTO_RESOLVED`** (`ADJUSTMENT_EXPLAINED`).
  - Resolution reason showing documented gateway fee adjustment of ₹100.
  - Mathematical proof formula: `₹14,210 - ₹100 = ₹14,110`.
  - Confidence score: `1.0 (100%)`.

---

### Screenshot 3: Human Review Escalation Detail (`03_human_review_detail.png`)
- **Location**: Click on transaction `TXN019` in the dashboard table.
- **What to Capture**:
  - Discrepancy details: Bank credit of ₹25,413 is ₹1,000 lower than expected settlement (₹26,413).
  - Decision badge: **`HUMAN_REVIEW`**.
  - Reason explaining that no adjustment record exists to account for the difference.
  - Recommended action for manual finance ops follow-up.

---

### Screenshot 4: Evaluation & Ground-Truth Accuracy Panel (`04_evaluation_panel.png`)
- **Location**: Scroll to the Evaluation section in the dashboard.
- **What to Capture**:
  - Phase 1 Accuracy: `100.0%` (Rule Engine).
  - Phase 2 Decision Accuracy: `100.0%` (AI Controller).
  - Auto-Resolution Precision: `100.0%` (Zero false positives).
  - Auto-Resolution Recall: `100.0%` (Explainable recovery).
  - Metadata badges: Provider (`OPENROUTER` / `DEMO`), Model (`meta-llama/llama-3.3-70b-instruct`), Evaluation scope (`15 / 30 exceptions`).

---

### Screenshot 5: Individual vs. Batch Mode Comparison (`05_mode_comparison.png`)
- **Location**: Bottom of the Evaluation Panel / Terminal benchmark output.
- **What to Capture**:
  - Individual vs. Batch Architecture comparison cards.
  - Benchmark performance highlights:
    - **81.5% Latency Reduction** (59.64s → 11.01s).
    - **93.1% Token Reduction** (28,657 → 1,973 tokens).
    - Equal 100.0% Decision Accuracy, Precision, and Recall.
