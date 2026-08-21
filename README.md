# AI Finance Controller

An enterprise-grade financial reconciliation and exception investigation platform combining a **deterministic Phase 1 reconciliation engine** with a **Phase 2 AI investigation and escalation agent**.

---

## Architecture Overview

```text
  ┌────────────────────────────────────────────────────────────────────────┐
  │                    SOURCE FINANCIAL DATA (CSV / ERP)                   │
  │     payments.csv           ledger.csv                 bank.csv         │
  └──────────┬─────────────────────┬──────────────────────────┬────────────┘
             │                     │                          │
             └─────────────────────┼──────────────────────────┘
                                   │
                                   ▼
  ┌────────────────────────────────────────────────────────────────────────┐
  │              PHASE 1: DETERMINISTIC RECONCILIATION ENGINE              │
  │                                                                        │
  │   • Transaction Matching         • Ledger Calculation Checks           │
  │   • Amount Comparisons           • Missing / Duplicate Bank Checks     │
  └────────────────────────────────┬───────────────────────────────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    ▼                             ▼
              RECONCILED                      EXCEPTION
           (70 transactions)              (30 transactions)
           [Audit Logged]                         │
                                                  ▼
  ┌────────────────────────────────────────────────────────────────────────┐
  │                 PHASE 2: AI INVESTIGATION CONTROLLER                   │
  │                                                                        │
  │   Agent Loop (Max 5 Tool Calls):                                       │
  │     ├── get_transaction(id)                                            │
  │     ├── get_payment_record(id)                                         │
  │     ├── get_ledger_record(id)                                          │
  │     ├── get_bank_records(id)                                           │
  │     ├── calculate_expected_settlement(id)                              │
  │     └── check_for_duplicates(id)                                       │
  │                                                                        │
  │   Pydantic Structured Output Validation                                │
  │   (transaction_id, decision, exception_type, reason, evidence, conf)   │
  └────────────────────────────────┬───────────────────────────────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    ▼                             ▼
              AUTO_RESOLVED                  HUMAN_REVIEW
          (Deterministic Proof)          (Unexplained Discrepancy)
```

---

## Phase 1: Deterministic Finance Logic

### 1. Project Goal & Finance Workflow
In digital commerce, transactions flow through three systems:
1. **Payment Gateway (`payments.csv`)**: Captures customer checkout transactions.
2. **Internal Ledger (`ledger.csv`)**: Records revenue, applies fee deductions, and calculates expected net receivables ($\text{net} = \text{gross} - \text{fee}$).
3. **Settlement Bank Statement (`bank.csv`)**: Reflects actual funds credited into corporate accounts.

The deterministic engine validates every transaction against 6 strict accounting rules:

| Order | Rule Check | Condition for Exception | Exception Code |
| :---: | :--- | :--- | :--- |
| **1** | Missing Ledger | Payment exists without corresponding ledger posting | `MISSING_LEDGER_RECORD` |
| **2** | Gross Mismatch | `payment.amount != ledger.gross_amount` | `GROSS_AMOUNT_MISMATCH` |
| **3** | Ledger Calculation | `ledger.gross_amount - ledger.fee != ledger.net_amount` | `LEDGER_CALCULATION_ERROR` |
| **4** | Missing Bank Record | No settlement credit found in bank statements | `MISSING_BANK_RECORD` |
| **5** | Duplicate Bank Record | Multiple bank statement lines for one transaction | `DUPLICATE_BANK_RECORD` |
| **6** | Bank Amount Mismatch | `(ledger.gross_amount - ledger.fee) != bank.credited_amount` | `BANK_AMOUNT_MISMATCH` |

---

## Phase 2: AI Investigation & Exception Resolution

### 1. Why Keep the Deterministic Engine as the Source of Truth?
- **Zero Arithmetic Hallucination**: Financial accounting cannot tolerate probabilistic guesses for math. Phase 1 guarantees 100% exact comparisons, fee arithmetic, and duplicate counting.
- **Strict Separation of Concerns**:
  - **Deterministic Engine**: Identifies *what* is broken.
  - **AI Agent**: Investigates *why* it happened, gathers auditable evidence, and decides the next operational action.

### 2. Available Agent Tools (Read-Only)
The AI agent cannot execute arbitrary Python or access filesystem records directly. It must request data via structured, read-only tools:

| Tool | Purpose | Output |
|---|---|---|
| `get_transaction(transaction_id)` | Retrieve multi-source snapshot | `{payment, ledger, bank_records}` |
| `get_payment_record(transaction_id)` | Retrieve gateway payment record | `{transaction_id, merchant_id, amount, date, status}` |
| `get_ledger_record(transaction_id)` | Retrieve general ledger entry | `{transaction_id, gross_amount, fee, net_amount, date, status}` |
| `get_bank_records(transaction_id)` | Retrieve all bank credits (including duplicates) | `{count, bank_records: [...]}` |
| `calculate_expected_settlement(transaction_id)` | Deterministically calculate net settlement | `{gross_amount, fee, expected_net, calculation}` |
| `check_for_duplicates(transaction_id)` | Detect multiple bank settlement lines | `{duplicate_count, is_duplicate, bank_references, credited_amounts}` |

### 3. Investigation & Auto-Resolution Policy
- **`AUTO_RESOLVED` Criteria**:
  - The discrepancy is completely explained by deterministic evidence (e.g. standard fee deduction matched across sources).
  - Confidence is $\ge 0.90$.
- **`HUMAN_REVIEW` Criteria (Safe Escalation)**:
  - Missing ledger entry or missing bank statement.
  - Unexplained shortage or excess in bank credit with no supporting fee/adjustment record.
  - Duplicate bank credits without an explicit reversal.
  - Ambiguous or contradictory tool evidence.
  - Investigation exceeds `MAX_TOOL_CALLS = 5`.

### 4. Safety Controls
1. **Immutable Source Records**: Tools are strictly read-only. No payment, ledger, or bank record can be modified or deleted by the agent.
2. **Anti-Hallucination Constraints**: System prompt forbids inventing fees, transactions, or bank statements.
3. **Structured Pydantic Validation**: All agent responses are validated against `AgentDecision`. Malformed outputs or out-of-range confidence scores ($[0.0, 1.0]$) automatically fail over to `HUMAN_REVIEW`.
4. **Auditable Logs**: Every investigation records tool calls, timestamped UTC execution, extracted factual evidence, and recommendations without storing noisy chain-of-thought traces.

---

## Evaluation & Ground Truth Methodology

The synthetic data generator (`src/generator.py`) builds a ground-truth mapping for all 100 transactions with a fixed seed (`seed=42`).

Phase 2 evaluation measures:
- **`agent_accuracy`**: Fraction of agent decisions matching ground-truth expectation ($\text{correct} / \text{total} \times 100$).
- **Per-Category Accuracy**: Breakdown across `MISSING_LEDGER_RECORD`, `GROSS_AMOUNT_MISMATCH`, `BANK_AMOUNT_MISMATCH`, `DUPLICATE_BANK_RECORD`, `LEDGER_CALCULATION_ERROR`, etc.
- **LLM Confidence Independence**: Accuracy is measured against known ground truth, never against the model's self-reported confidence.

---

## Project Structure

```text
ai-finance-controller/
│
├── data/
│   ├── payments.csv           # 100 synthetic payment transactions
│   ├── ledger.csv             # Internal ERP ledger postings
│   └── bank.csv               # Bank statement settlements
│
├── src/
│   ├── __init__.py
│   ├── generator.py           # Reproducible synthetic dataset & ground truth generator
│   ├── reconciliation.py      # Phase 1 deterministic rule engine & batch processor
│   ├── main.py                # Phase 1 CLI report entry point
│   ├── run_agent.py           # Phase 2 AI investigation & combined metrics entry point
│   │
│   └── agent/
│       ├── __init__.py
│       ├── schemas.py         # Pydantic models (AgentDecision, InvestigationLog, Metrics)
│       ├── prompts.py         # System prompt and investigation prompt builders
│       ├── tools.py           # Read-only FinancialToolkit with 6 deterministic tools
│       ├── controller.py      # AgentController agentic loop & LLM integration
│       └── evaluator.py       # Ground-truth accuracy and combined metrics evaluation
│
├── tests/
│   ├── __init__.py
│   ├── test_reconciliation.py # 9 Phase 1 unit & batch tests
│   └── test_agent.py          # 11 Phase 2 unit & integration tests (mocked LLM)
│
├── .env.example               # Environment variables template
├── requirements.txt           # Python dependencies
└── README.md                  # Project documentation
```

---

## Quickstart

### 1. Installation

```bash
pip install -r requirements.txt
```

### 2. Configuration (For Live LLM Execution)

Copy `.env.example` to `.env` and set your API key:

```bash
cp .env.example .env
```

```env
OPENAI_API_KEY=your-api-key-here
MODEL_NAME=gpt-4o-mini
```

### 3. Run Phase 1 Deterministic Engine

```bash
python src/main.py
```

### 4. Run Phase 2 AI Investigation Controller

```bash
python src/run_agent.py
```

### 5. Run Automated Test Suite (No API Key Required)

```bash
python -m pytest -v
```

All 20 tests (9 Phase 1 + 11 Phase 2) execute with 100% determinism in $< 1\text{s}$.

---

## Summary of Results

```text
============================================
         AI FINANCE CONTROLLER
       PHASE 2: AI INVESTIGATION
============================================

Total transactions       : 100
Initially reconciled     : 70
Initial exceptions       : 30
Initial match rate       : 70.00%

AI auto-resolved         : 0 (Strict policy: no unexplained gaps resolved)
Human review required    : 30
Agent resolution rate    : 0.00%

Final resolved           : 70
Final unresolved         : 30
Final resolution rate    : 70.00%

--------------------------------------------
AGENT ACCURACY vs GROUND TRUTH
--------------------------------------------
  Total decisions   : 30
  Correct decisions : 30
  Accuracy          : 100.00%
```

```text
Phase 1 = deterministic financial truth
Phase 2 = AI investigation + explanation + escalation
```
"# AI-Finance-Controller" 
