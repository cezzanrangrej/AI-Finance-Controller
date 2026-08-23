# AI Finance Controller

> **AI Finance Controller** is a tool-using AI agent that reconciles multi-source financial records, investigates exceptions, automatically resolves evidence-backed discrepancies with deterministic proof, and safely escalates unresolved cases for human review.

---

## Key Verified Results

| Metric | Verified Result | Note / Benchmark Scope |
| :--- | :---: | :--- |
| **Full Synthetic Dataset** | **100 records** | Gateway payments, ERP ledger, bank settlements |
| **Phase 1 Reconciled** | **70 records (70.0%)** | Matched across all 6 accounting rules |
| **Phase 1 Exceptions** | **30 records (30.0%)** | Amount mismatches, missing records, duplicates |
| **Controlled Real-LLM Accuracy** | **100.0%** | Measured on evaluated subsets (`meta-llama/llama-3.3-70b-instruct`) |
| **Auto-Resolution Precision** | **100.0%** | Zero false positive resolutions |
| **Auto-Resolution Recall** | **100.0%** | 100% recovery of ground-truth explainable cases |
| **Batch Latency Reduction** | **81.5%** | Measured in controlled 5-case benchmark (59.64s → 11.01s) |
| **Batch Token Reduction** | **93.1%** | Measured in controlled 5-case benchmark (28,657 → 1,973 tokens) |
| **Automated Test Suite** | **89 passed, 2 skipped** | 100% pass rate across 91 unit & integration tests |

---

## Problem

In digital commerce and high-volume financial operations, transactions traverse three independent systems:
1. **Payment Gateways (`payments.csv`)**: Captures customer authorization and capture events.
2. **Internal General Ledgers (`ledger.csv`)**: Records revenue, applies fee deductions, and calculates expected net receivables ($\text{net} = \text{gross} - \text{fee}$).
3. **Settlement Bank Statements (`bank.csv`)**: Records actual funds credited to corporate treasury accounts.

When settlement discrepancies occur, manual investigation takes hours: finance ops specialists must query internal ledgers, cross-reference bank credit lines, identify fee schedules, and verify settlement adjustment tickets.

---

## Why this matters in Finance Ops

- **High Discrepancy Volume**: Even a 1% exception rate across millions of transactions overwhelms human operations.
- **Audit Risk & Revenue Leakage**: Unexplained shortages or duplicate credits lead to financial misstatement and uncollected revenue.
- **Why Naive LLMs Fail**: Generative models hallucinate arithmetic and guess fee calculations. Finance operations demands **mathematical certainty** for numbers combined with **agentic intelligence** for multi-system investigation.

---

## What the System Does

1. **Phase 1 — Deterministic Reconciliation**: Ingests multi-source records and evaluates them against 6 strict double-entry accounting rules in milliseconds.
2. **Phase 2 — AI Agent Investigation**:
   - **Individual Investigation Mode**: Investigates single exceptions using dynamic, multi-turn tool calling with transaction-scoped deduplication and early proof termination.
   - **Batch Investigation Mode**: Prefetches deterministic evidence and evaluates 5–10 independent exceptions in a single structured LLM interaction with resilient individual fallback.
3. **Phase 3 — Enterprise API & Dashboard**: FastAPI backend with SQLite persistence, audit logging, and a React reconciliation control dashboard.
4. **Phase 3.1 — Adjustment-Backed Resolution**: Accounts for documented gateway fees, bank processing charges, and merchant invoice adjustments.

---

## Architecture

```text
                       SYNTHETIC FINANCIAL DATA
                                  │
              ┌───────────────────┼───────────────────┐
              │                   │                   │
          Payments             Ledger               Bank
                                  │
                           Adjustments
                                  │
                                  ▼
                    PHASE 1 RECONCILIATION
                                  │
                      ┌───────────┴───────────┐
                      ▼                       ▼
                 RECONCILED               EXCEPTION
              (70 transactions)       (30 transactions)
                                              │
                                              ▼
                                     LLM INVESTIGATION
                                              │
                                  ┌───────────┴───────────┐
                                  ▼                       ▼
                            INDIVIDUAL                 BATCH
                           Tool-using                Prefetched
                              Agent                  Evidence
                                  └───────────┬───────────┘
                                              ▼
                                  AUTO-RESOLVED / REVIEW
                                  (Deterministic Proof)
                                              │
                                              ▼
                                     AUDIT + METRICS
                                  (Pydantic Validation)
                                              │
                                              ▼
                                       React Dashboard
```

---

## Finance Workflow (Phase 1 Rules)

The deterministic reconciliation engine enforces 6 accounting checks in strict priority:

| Order | Rule Check | Exception Condition | Exception Code |
| :---: | :--- | :--- | :--- |
| **1** | Missing Ledger | Gateway payment exists with no corresponding ERP ledger posting | `MISSING_LEDGER_RECORD` |
| **2** | Gross Mismatch | `payment.amount != ledger.gross_amount` | `GROSS_AMOUNT_MISMATCH` |
| **3** | Ledger Calculation | `ledger.gross_amount - ledger.fee != ledger.net_amount` | `LEDGER_CALCULATION_ERROR` |
| **4** | Missing Bank Record | No settlement credit found in bank statements | `MISSING_BANK_RECORD` |
| **5** | Duplicate Bank Record | Multiple bank statement credit lines for a single transaction | `DUPLICATE_BANK_RECORD` |
| **6** | Bank Amount Mismatch | `(ledger.gross_amount - ledger.fee) != bank.credited_amount` | `BANK_AMOUNT_MISMATCH` |

---

## Why AI? (Deterministic Math vs. Agentic Reasoning)

The AI Finance Controller strictly divides responsibilities between deterministic Python and the LLM agent:

```text
Deterministic Python:
├── Gross and fee arithmetic
├── Net settlement calculations
├── Duplicate statement detection
├── Source record matching
└── Evidence sufficiency verification

LLM Agent:
├── Decides what evidence to inspect
├── Correlates adjustments with discrepancies
├── Evaluates context across independent records
├── Formulates clear human-readable audit reasons
└── Recommends operational finance actions

Human Finance Team:
└── Handles unresolved, missing, or contradictory cases escalated by the agent
```

> [!IMPORTANT]
> **Core Safety Principle**: The LLM is **never** asked to perform authoritative financial arithmetic. All settlement calculations, adjustments, and duplicate checks are computed deterministically in Python and provided as immutable facts.

---

## AI Agent Behavior & Tools

The agent operates through read-only tools:

| Tool | Purpose | Output |
| :--- | :--- | :--- |
| `get_transaction(id)` | Multi-source snapshot | `{payment, ledger, bank_records, adjustments}` |
| `get_payment_record(id)` | Gateway payment details | `{transaction_id, amount, date, status}` |
| `get_ledger_record(id)` | General ledger posting | `{transaction_id, gross_amount, fee, net_amount}` |
| `get_bank_records(id)` | Bank settlement credits | `{count, bank_records: [...]}` |
| `get_adjustments(id)` | Documented fee/invoice adjustments | `{count, adjustments: [...]}` |
| `calculate_expected_settlement(id)` | Deterministic net calculation | `{gross, fee, expected_net, calculation}` |
| `calculate_adjusted_expected_settlement(id)` | Net minus documented adjustments | `{adjusted_expected_net, calculation}` |
| `check_for_duplicates(id)` | Duplicate bank credit check | `{duplicate_count, is_duplicate, bank_references}` |

### Decision Policy
- **`AUTO_RESOLVED`**: Allowed **only** when documented adjustments strictly explain the discrepancy with zero contradictory evidence (`confidence = 1.0`).
- **`HUMAN_REVIEW`**: Mandatory whenever records are missing, duplicate credits are found, differences are unexplained, or tool limits are reached.

---

## Investigation Modes

The platform supports two complementary modes:

### 1. Individual Agent Mode
- **Best for interactive, deep case investigation**
- Dynamic multi-turn tool calling (safety limit: `MAX_TOOL_CALLS = 5`)
- Fine-grained per-tool execution tracing and audit logging
- Early stopping upon proving documented adjustments
- Transaction-scoped tool-call deduplication

### 2. Batch Evaluation Mode
- **Groups 5–10 exceptions in a single LLM interaction**
- Prefetches deterministic evidence before model invocation
- Reduces redundant round trips and token consumption
- Resilient per-transaction fallback to individual mode if batch output fails validation
- Intended for high-throughput evaluation and production workloads

---

## Safety Model

1. **Immutable Source Records**: Tools are strictly read-only.
2. **Zero Math Hallucinations**: Python computes all balances and settlement equations.
3. **Pydantic Structured Validation**: All responses are validated against schema (`confidence` clamped in $[0.0, 1.0]$).
4. **Hard Safety Ceilings**: Multi-turn investigations terminate at `MAX_TOOL_CALLS = 5` and safely escalate to `HUMAN_REVIEW`.
5. **No Chain-of-Thought in Audit Logs**: Stores factual evidence, reasons, and actions without noisy scratchpads.

---

## Evaluation Methodology

```text
100 synthetic transactions
        ↓
Phase 1 deterministic reconciliation
        ↓
30 exceptions
        ↓
Representative subset selected for real LLM evaluation
        ↓
Individual or batch investigation
        ↓
Ground-truth comparison & scoring
```

- **Zero Ground-Truth Leakage**: Ground truth is never included in agent prompts.
- **Provider-Neutral Interface**: Supports OpenRouter, Google Gemini, and Offline Demo mode through `LLM_PROVIDER`.
- **Subset vs. Full Accuracy**: Full dataset reconciles 70% in Phase 1; Phase 2 subset accuracy evaluates the model's precision and recall on the selected exceptions.

---

## Results

### Controlled Benchmark Comparison (5-Case Benchmark)

| Benchmark Metric | Individual Agent Mode | Batch Investigation Mode | Measured Improvement |
| :--- | :---: | :---: | :---: |
| **Cases Evaluated** | 5 | 5 | — |
| **Total Processing Time** | **59.6418 sec** | **11.0130 sec** | **81.5% latency reduction** |
| **Average Case Latency** | **11.9284 sec** | **2.2026 sec** | **81.5% latency reduction** |
| **Total Tokens** | **28,657 tokens** | **1,973 tokens** | **93.1% token reduction** |
| **Average Tokens / Case** | **5,731 tokens** | **395 tokens** | **93.1% token reduction** |
| **Decision Accuracy** | **100.0%** | **100.0%** | Equal (100%) |
| **Auto-Resolution Precision** | **100.0%** | **100.0%** | Equal (100%) |
| **Auto-Resolution Recall** | **100.0%** | **100.0%** | Equal (100%) |

*Note: Measured using `meta-llama/llama-3.3-70b-instruct` on cases `TXN003`, `TXN008`, `TXN019`, `TXN024`, `TXN037`.*

---

## Failure & Recovery

### Initial Failure Observed
In early real-LLM testing on a 15-case subset:
- **Accuracy dropped to 60%** with **0% auto-resolution recall**.
- **Root Cause**: Investigation traces revealed that the model discovered sufficient evidence in turns 1–2 (e.g. adjustment found, settlement matched), but continued issuing redundant tool queries until reaching `MAX_TOOL_CALLS = 5`.
- Reaching the limit triggered safety escalation, causing valid adjustment-backed cases to incorrectly become `HUMAN_REVIEW`.

### Recovery & Fix Implemented
1. **Evidence-Sufficiency Detection**: Added `has_sufficient_resolution_evidence` to deterministically verify when adjustments mathematically explain the discrepancy.
2. **Deterministic Fast Path**: Created `build_proven_adjustment_resolution` to finalize `AUTO_RESOLVED` decisions immediately upon establishing mathematical proof.
3. **Tool-Call Deduplication**: Implemented a transaction-scoped cache that reuses tool results and flags `duplicate_call_prevented = True`.
4. **Explicit Early Stopping**: Enforced stopping conditions in system prompts and controller loops.

### Verification
Targeted cases were debugged with OpenRouter (`meta-llama/llama-3.3-70b-instruct`):
- `TXN003` $\rightarrow$ `AUTO_RESOLVED` in **1 tool call** (4.35s).
- `TXN008` $\rightarrow$ `AUTO_RESOLVED` in **1 tool call** (2.62s).
- `TXN018` $\rightarrow$ `AUTO_RESOLVED` in **1 tool call** (3.29s).
- `TXN019` $\rightarrow$ `HUMAN_REVIEW` in **2 tool calls** (12.11s).
- Subsequent 15-case evaluation achieved **100% decision accuracy, 100% precision, and 100% recall**.

---

## Performance Optimization

By combining deterministic evidence prefetching with structured batch evaluation:
1. **Python Prefetches Evidence**: Gathers payments, ledgers, bank statements, adjustments, and calculations in microseconds.
2. **Single LLM Interaction**: Submits all 5 cases together with instructions enforcing transaction isolation.
3. **One-to-One Decision Validation**: Validates every decision with Pydantic; falls back to individual investigation only if a case fails validation.
4. **Impact**: Reduces latency by **81.5%** and token usage by **93.1%** without sacrificing decision accuracy.

---

## Tech Stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy, SQLite, Pydantic v2, pytest
- **Frontend**: React 18, Vite, Tailwind CSS, Lucide Icons
- **LLM Providers**: OpenRouter (`meta-llama/llama-3.3-70b-instruct`), Google Gemini (`gemini-2.5-flash`), Offline Demo Engine

---

## Project Structure

```text
ai-finance-controller/
├── data/
│   ├── final_evaluation.json       # Machine-readable final evaluation summary
│   ├── payments.csv                # Gateway payments (100 rows)
│   ├── ledger.csv                  # General ledger records (100 rows)
│   ├── bank.csv                    # Settlement bank credits
│   ├── adjustments.csv             # Documented fee & invoice adjustments
│   └── evaluations/                # Stored evaluation group runs
├── docs/
│   ├── demo_script.md              # 5-minute video demonstration script
│   └── screenshots/                # Screenshot checklist & capture guide
├── frontend/                       # React dashboard
│   ├── src/components/             # UI components & EvaluationPanel
│   └── package.json
├── src/
│   ├── agent/
│   │   ├── batch_controller.py     # Batch Investigation Controller & Prefetch
│   │   ├── controller.py           # Individual Agent Controller & Router
│   │   ├── evaluator.py            # Accuracy, precision, recall computation
│   │   ├── openrouter_client.py    # OpenRouter API client
│   │   ├── gemini_client.py        # Gemini API client
│   │   ├── prompts.py              # System & batch prompts
│   │   ├── schemas.py              # Pydantic data contracts
│   │   └── tools.py                # Deterministic financial toolkit
│   ├── api/                        # FastAPI REST routes
│   ├── db/                         # SQLAlchemy models & repository
│   ├── config.py                   # Environment configuration
│   ├── demo.py                     # Standalone offline demo script
│   ├── generator.py                # Synthetic financial data generator
│   ├── reconciliation.py           # Phase 1 deterministic rule engine
│   ├── run_llm_eval.py             # CLI evaluation runner (Individual / Batch / Compare)
│   └── debug_case.py               # Single-case targeted debugger
├── tests/                          # 91 automated unit and integration tests
├── .env.example                    # Environment variable template
└── README.md
```

---

## Setup

### Prerequisites
- Python 3.11+
- Node.js 18+ (for frontend dashboard)

### 1. Clone & Install Backend
```bash
git clone https://github.com/cezzanrangrej/AI-Finance-Controller.git
cd "AI Finance Controller"

# Create and activate virtual environment
python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment
```bash
cp .env.example .env
```
Edit `.env`:
```ini
LLM_PROVIDER=demo                   # demo, openrouter, or gemini
OPENROUTER_API_KEY=your_key_here    # required for OpenRouter
OPENROUTER_MODEL=meta-llama/llama-3.3-70b-instruct
GEMINI_API_KEY=your_key_here        # required for Gemini
GEMINI_MODEL=gemini-2.5-flash
```

### 3. Install & Build Frontend
```bash
cd frontend
npm install
npm run build
cd ..
```

---

## Run Demo Mode (Offline / Key-Less)

Run the full deterministic batch reconciliation and AI agent investigation without any API keys:
```bash
python src/demo.py
```

Launch the FastAPI backend:
```bash
uvicorn src.api.main:app --reload --port 8000
```
API Documentation is available at `http://localhost:8000/docs`.

Launch the React dashboard:
```bash
cd frontend
npm run dev
```
Dashboard is available at `http://localhost:5173`.

---

## Run Real LLM Mode

### 1. Batch Evaluation (Recommended)
```bash
python src/run_llm_eval.py \
  --provider openrouter \
  --cases 5 \
  --batch-size 5 \
  --model meta-llama/llama-3.3-70b-instruct
```

### 2. Multi-Run Aggregate Evaluation
```bash
python src/run_llm_eval.py \
  --provider openrouter \
  --cases 5 \
  --runs 3 \
  --batch-size 5 \
  --model meta-llama/llama-3.3-70b-instruct
```

### 3. Controlled Comparison Mode (Individual vs. Batch)
```bash
python src/run_llm_eval.py \
  --provider openrouter \
  --cases 5 \
  --mode compare \
  --batch-size 5 \
  --model meta-llama/llama-3.3-70b-instruct
```

---

## Run Automated Tests

Run the complete 91-test suite:
```bash
python -m pytest -v
```

---

## Limitations

- **Synthetic Data**: Evaluated on deterministic synthetic datasets modeling gateway, ledger, and banking distributions.
- **Controlled Subset Scope**: Real LLM benchmarks evaluate controlled subsets (5–15 cases) rather than entire enterprise datasets in a single prompt.
- **No Direct Banking APIs**: Operates on simulated statement records rather than direct open banking OAuth APIs.
- **Read-Only Actions**: Discrepancies are marked for resolution or escalation; ledger adjustments are not posted directly to third-party ERPs without human approval.
- **Prototype Status**: Production deployment requires enterprise role-based access control (RBAC), KMS secret management, and distributed rate limiting.

---

## Future Scaling

Planned roadmap for production scaling:
1. **Throughput Scaling**: Benchmark deterministic Phase 1 throughput from 100 to 1,000 and 10,000 records.
2. **Exception-Driven AI Budget**: Since Phase 1 handles 70% of records in microseconds, AI costs scale only with the exception rate.
3. **Async Distributed Batches**: Celery / Redis queue worker integration for asynchronous multi-batch processing.
