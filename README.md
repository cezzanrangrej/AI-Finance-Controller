# AI Finance Controller

> An enterprise-style AI finance reconciliation and exception-investigation system that combines **milliseconds-fast deterministic accounting rules (Python/Decimal)** with **intelligent LLM agent investigation** to audit multi-source financial records, explain settlement discrepancies with mathematical proof, and safely escalate unresolved cases.

---

## Verified Project Benchmarks Summary

All benchmarks below are verified measurements on specific datasets and test workloads:

| Benchmark / Scope | Verified Result | Measurement / Detail |
| :--- | :---: | :--- |
| **Phase 1 Engine Latency (100 Records)** | **0.0051 sec** (CLI) / **0.0052 sec** (API) | Deterministic double-entry rule engine execution |
| **Run-Start API Response Latency** | **0.0081 sec** | `POST /api/evaluations/start` async response |
| **Time to First SSE Stream Event** | **0.0120 sec** | Stream initialization & `phase1_started` event |
| **Test Dataset 03 (100 Records, 20 Exceptions)** | **100.0% Decision Accuracy** | 20/20 correct decisions (6 `AUTO_RESOLVED`, 14 `HUMAN_REVIEW`) |
| **Test Dataset 03 Precision & Recall** | **100.0% Precision / 100.0% Recall** | 0 false positives; 100% recovery of ground-truth resolvable cases |
| **Test Dataset 03 Execution Time** | **36.1363 sec** | 20 cases in 4 parallel 5-case batches |
| **Test Dataset 02 Wall-Clock Speedup** | **84.8% Time Reduction** | 155.90s (Sequential) → 23.69s (Parallel 3x5 batches) |
| **Controlled 5-Case Batch Optimization** | **81.5% Latency / 93.1% Token Reduction** | Latency: 59.64s → 11.01s; Tokens: 28,657 → 1,973 tokens |
| **Automated Test Suite** | **237 passed, 2 skipped** | 100% pass rate across 16 unit and integration test suites |
| **Frontend Production Build** | **0 Errors** | Verified production bundle via Vite (`npm run build`) |

---

## Project Positioning & Core Flow

In modern digital commerce and payments operations, financial transactions flow across three independent ledger systems:

```text
Financial CSV Sources (Payments, ERP Ledger, Bank Statements, Adjustments)
        ↓
Canonical Normalization & Decimal Validation Layer
        ↓
Deterministic Phase 1 Double-Entry Reconciliation Engine
        ↓
Exception Classification & Filter
        ↓
Intelligent AI Exception Investigation (Individual / Batch / Multi-Agent)
        ↓
Deterministic Financial Proof & Sufficiency Verification (Python)
        ↓
Decision Engine (AUTO_RESOLVED vs. HUMAN_REVIEW)
        ↓
Audit Trail Persistence & React Operations Dashboard
```

> [!IMPORTANT]
> **Core Safety Principle**: Deterministic Python and `Decimal` arithmetic remain strictly authoritative for financial numbers, balance equations, and evidence verification. Generative AI models are used for dynamic context retrieval, correlation of adjustment records, and human-readable audit explanations, but **never for unverified mental math**.

---

## High-Level System Architecture

```text
                               ┌──────────────────────────────────────────┐
                               │   Financial Data Sources (CSV / Files)   │
                               └────────────────────┬─────────────────────┘
                                                    │
                                                    ▼
                               ┌──────────────────────────────────────────┐
                               │ Canonical Data Normalization Layer       │
                               │ (Decimal Invariants & Field Provenance)  │
                               └────────────────────┬─────────────────────┘
                                                    │
                                                    ▼
                               ┌──────────────────────────────────────────┐
                               │ Phase 1 Deterministic Engine (Python)    │
                               │ (6 Accounting Checks · ~0.005s/100 pkts)│
                               └──────────┬────────────────────┬──────────┘
                                          │                    │
                                          ▼                    ▼
                                     RECONCILED           EXCEPTIONS
                                (e.g. 70 records)     (e.g. 30 records)
                                                               │
                                                               ▼
                               ┌──────────────────────────────────────────┐
                               │ Balanced Exception-Type Batch Scheduler  │
                               │ (5-Case Batches · Auto-Concurrency ≤ 5)  │
                               └────────────────────┬─────────────────────┘
                                                    │
                                                    ▼
                               ┌──────────────────────────────────────────┐
                               │ Phase 2 AI Investigation Execution       │
                               │ ┌──────────────────────────────────────┐ │
                               │ │ Individual Agent / Batch Agent /     │ │
                               │ │ Multi-Agent (Investigator+Verifier)  │ │
                               │ └──────────────────┬───────────────────┘ │
                               │                    │                     │
                               │                    ▼                     │
                               │ ┌──────────────────────────────────────┐ │
                               │ │ Deterministic Proof Re-Validation    │ │
                               │ │ (has_sufficient_resolution_evidence) │ │
                               │ └──────────────────────────────────────┘ │
                               └────────────────────┬─────────────────────┘
                                                    │
                                                    ▼
                               ┌──────────────────────────────────────────┐
                               │ Decision Policy (AUTO_RESOLVED / REVIEW) │
                               └────────────────────┬─────────────────────┘
                                                    │
                                                    ▼
                               ┌──────────────────────────────────────────┐
                               │ Progressive SSE Streaming & Persistence  │
                               │ (SQLite Audit Trail + React Dashboard)   │
                               └──────────────────────────────────────────┘
```

---

## Data Flow & Processing Lifecycle

1. **Deterministic Phase 1 Inspection**: Ingests all records (e.g., 100 transactions) and evaluates them against strict double-entry rules.
2. **Selective AI Invocation**: The LLM is **NOT called once per record**. Only records identified as Phase 1 exceptions proceed to AI investigation.
   - *Example*: Out of 100 transactions, 70 match deterministically and 30 produce exceptions $\rightarrow$ only the 30 exceptions are submitted for AI investigation.
3. **Controlled Evaluation (`--cases N`)**:
   - When running CLI benchmarks (`src/run_dataset.py`), omitting `--cases` evaluates **all** detected exceptions in the dataset.
   - Passing `--cases N` restricts AI investigation to the requested subset of $N$ exceptions.

---

## Phase 1 Engine Performance Verification

A dedicated request-lifecycle trace was performed to measure timing across every stage of dataset processing:

| Lifecycle Stage | Measured Latency (100-Record Test Dataset) |
| :--- | :---: |
| **Dataset File Loading & Parsing** | **0.0042 sec** |
| **Schema Invariant Validation** | **0.0018 sec** |
| **CLI Phase 1 Deterministic Engine** | **0.0051 sec** |
| **Backend Phase 1 Engine (via FastAPI)** | **0.0052 sec** |
| **Run-Start API Response (`POST /api/evaluations/start`)** | **0.0081 sec** |
| **Time to First SSE Event (`phase1_started`)** | **0.0120 sec** |

> [!NOTE]
> Phase 1 reconciliation itself is virtually instantaneous (~5 milliseconds for 100 records). Apparent delays in early UI versions were caused by visual state-labeling and asynchronous lifecycle management, rather than backend calculation bottlenecks.

---

## AI Exception Investigation Modes

The system provides four complementary investigation strategies (all backed by the authoritative Python financial engine):

### A. Individual Agent Mode
- **Purpose**: Deep, interactive investigation of complex single exceptions.
- **Mechanism**: Multi-turn tool calling (safety bound: `MAX_TOOL_CALLS = 5`) with transaction-scoped deduplication and early stopping upon finding proof.

### B. Batch Agent Mode
- **Purpose**: High-throughput processing with minimal token and latency overhead.
- **Mechanism**: Groups 5–10 exceptions per LLM prompt, prefetching deterministic evidence so the model can evaluate multiple discrepancies in a single turn.

### C. Multi-Agent Investigator / Verifier Mode
- **Purpose**: Independent dual-agent verification for high-risk financial discrepancies.
- **Roles**:
  1. **Investigator Agent**: Reads records, queries tool APIs, and constructs an initial `InvestigationProposal`.
  2. **Deterministic Python Layer**: Validates mathematical equality and adjustment proof.
  3. **Verifier Agent**: Independently critiques the proposal against raw source records.
  4. **Final Controller**: Enforces conservative escalation to `HUMAN_REVIEW` if any disagreement or evidence gap exists.

### D. Batch Multi-Agent Mode (`BatchMultiAgentController`)
- **Purpose**: High-throughput parallel execution paired with independent dual-agent verification.
- **Mechanism**: Groups exceptions into pre-fetched batches; the Investigator Agent proposes resolutions for the batch, the Python Decimal layer verifies proof sufficiency, and the Verifier Agent independently critiques the batch resolutions before final consensus.

---

## Multi-Agent Architecture & Role Separation

```text
Exception Record
       ↓
Multi-Agent Orchestrator
       ↓
Investigator Agent  ────►  Queries Tools & Proposes Resolution
       ↓
Deterministic Python Layer  ────►  Verifies Arithmetic & Proof Sufficiency
       ↓
Verifier Agent  ────►  Independently Reviews Proposal & Evidence
       ↓
Final Controller  ────►  Applies Disagreement Policy (AUTO_RESOLVED vs. HUMAN_REVIEW)
```

Role-specific LLM providers and models are assigned independently via environment
variables. The role variables are sufficient on their own -- `LLM_PROVIDER` is not
required:

```ini
INVESTIGATOR_PROVIDER=gemini
INVESTIGATOR_MODEL=gemini-3.6-flash

VERIFIER_PROVIDER=openrouter
VERIFIER_MODEL=meta-llama/llama-3.3-70b-instruct
```

Each role resolves separately, so a missing Verifier key does not take the
Investigator offline with it. When a role names a provider whose key or model is
unusable, that role alone falls back to the offline demo engine, a `WARNING` is
logged, and the run is persisted with `llm_degraded=true` so its decisions are never
mistaken for real-model output. See [Provider Configuration](#provider-configuration)
for the full resolution order.

---

## LLM Provider Support

The system supports four provider configurations:
1. **Offline Demo Engine**: Local rule-based emulator requiring zero external API keys.
2. **Google Gemini**: Direct integration via Gemini API (`gemini-2.5-flash`, `gemini-3.6-flash`).
3. **OpenRouter**: Access to open-weights models (`meta-llama/llama-3.3-70b-instruct`, etc.).
4. **Grok / xAI**: Direct integration for xAI models (`grok-2-latest`). `XAI_API_KEY` and
   `XAI_MODEL` are accepted as aliases.

`agentrouter` is also supported, reusing the OpenRouter client against a different base URL.

### Provider Configuration

All resolution runs through `src/agent/provider_resolution.py`, which the API and both
controllers share. For each role, the provider is taken from the first of:

1. An explicit argument passed by the caller (for example the API's `provider` field).
2. `INVESTIGATOR_PROVIDER` / `VERIFIER_PROVIDER`.
3. `LLM_PROVIDER`, which acts as a **fallback for roles left blank**, not as an on/off gate.
4. Inference from whichever provider credentials are present.
5. The offline demo engine.

The key and model are then read from the role-scoped variables first
(`INVESTIGATOR_API_KEY`, `VERIFIER_MODEL`, ...), falling back to the provider's shared
variables (`GEMINI_API_KEY`, `OPENROUTER_MODEL`, ...). Gemini and Grok carry default
models; OpenRouter and AgentRouter do not, so those need a model set explicitly.

So all three of these are valid:

```ini
# a) One provider for both roles
LLM_PROVIDER=gemini
GEMINI_API_KEY=...

# b) Role variables alone -- no LLM_PROVIDER needed
INVESTIGATOR_PROVIDER=openrouter
INVESTIGATOR_API_KEY=...
INVESTIGATOR_MODEL=meta-llama/llama-3.3-70b-instruct
VERIFIER_PROVIDER=gemini
VERIFIER_API_KEY=...

# c) Both -- role values win, LLM_PROVIDER covers the role left blank
LLM_PROVIDER=gemini
GEMINI_API_KEY=...
INVESTIGATOR_PROVIDER=grok
GROK_API_KEY=...
```

### Offline Demo Mode

`DEMO_MODE=true` is a hard kill switch. Both agents run against the local rule-based
emulator and no external API is contacted, regardless of any provider or key configured
alongside it. Use it for key-less demos and deterministic tests. `LLM_PROVIDER=demo`
remains supported and behaves the same way.

An explicitly requested demo run is not a degradation and logs no warning. A run that
lands on demo because credentials were unusable is, and is flagged as such
(`llm_degraded`, `llm_degraded_reason`) on the run record and in the metrics and run
summary API responses.

---

## Automatic Parallel Execution & Batch Partitioning

To optimize wall-clock processing time, exception workloads are automatically divided into concurrent batches:

- **Default Batch Size**: 5 cases per batch (configurable up to 10).
- **Maximum Concurrency**: 5 parallel batches (`MAX_PARALLEL_BATCHES = 5`).
- **Automatic Calculation**:
  $$\text{total\_batches} = \lceil \frac{\text{cases}}{\text{batch\_size}} \rceil$$
  $$\text{actual\_concurrency} = \min(\text{total\_batches}, \text{MAX\_PARALLEL\_BATCHES})$$

### Execution Concurrency Examples
- **13 exceptions** (batch size 5) $\rightarrow$ 3 batches running concurrently.
- **25 exceptions** (batch size 5) $\rightarrow$ 5 batches running concurrently.
- **40 exceptions** (batch size 5) $\rightarrow$ 8 batches total (5 run concurrently, remaining wait for capacity).

> [!NOTE]
> **Multi-Run Cross-Validation Invariant**: When running multi-run benchmarks (`--runs N`), full dataset coverage is guaranteed across the union of all runs ($N$ non-overlapping, balanced partitions with 0 duplicate transaction IDs). At `runs=1` (the operational and frontend default), 100% of detected exceptions are investigated in that single run.

---

## Balanced Exception-Type Partitioning

Instead of naively slicing exceptions sequentially (`[0..5]`, `[5..10]`), the scheduler uses a **balanced diversification heuristic**:

```text
Input Exceptions:
- MISSING_LEDGER_RECORD     x2
- MISSING_BANK_RECORD       x2
- BANK_AMOUNT_MISMATCH      x5
- DUPLICATE_BANK_RECORD     x2
Total: 13 cases across 3 batches (5 + 4 + 4)

Balanced Schedule:
Batch 1: BANK_AMOUNT_MISMATCH (2), MISSING_LEDGER_RECORD (1), MISSING_BANK_RECORD (1), DUPLICATE_BANK_RECORD (1)
Batch 2: BANK_AMOUNT_MISMATCH (2), MISSING_LEDGER_RECORD (1), MISSING_BANK_RECORD (1)
Batch 3: BANK_AMOUNT_MISMATCH (1), DUPLICATE_BANK_RECORD (1), ...
```

*Motivation*: Overall wall-clock latency is constrained by the slowest batch. Diversifying exception types across batches reduces the risk of concentrating slow or tool-heavy cases in a single batch.

---

## Verified Parallel Execution Benchmarks

### Test Dataset 02 Comparison (15 Cases, 3 x 5-Case Batches)

| Mode | Total Elapsed Time | Observed Speedup | Execution Behavior |
| :--- | :---: | :---: | :--- |
| **Sequential Execution** | **155.9037 sec** | 1.00x | Batches executed 1 $\rightarrow$ 2 $\rightarrow$ 3 serially |
| **Parallel Execution** | **23.6896 sec** | **6.58x (84.8% reduction)** | Batches 1, 2, 3 STARTED simultaneously |

*Note: Measured on Test Dataset 02. Wall-clock latency on real LLMs is subject to provider network load.*

---

## Ground-Truth Benchmark Validation (Test Dataset 03)

Test Dataset 03 provides a controlled 100-record benchmark with 20 Phase 1 exceptions and verified ground-truth decisions:

- **Phase 1 Input**: 100 total transactions (80 reconciled, 20 exceptions).
- **Ground-Truth Breakdown**: 6 `AUTO_RESOLVED`, 14 `HUMAN_REVIEW`.
- **Batch Agent Execution Result**:
  - `AUTO_RESOLVED`: **6 cases** (100% correct)
  - `HUMAN_REVIEW`: **14 cases** (100% correct)
  - `NOT_EVALUATED`: **0 cases**
- **Metrics**:
  - **Decision Accuracy**: **100.00%** (20/20)
  - **Auto-Resolution Precision**: **100.00%** (0 false positives)
  - **Auto-Resolution Recall**: **100.00%** (6/6 explainable cases recovered)
- **Total Execution Time**: **36.1363 sec** (4 concurrent 5-case batches).

---

## Failure & Recovery Story: Post-LLM Deterministic Proof Engine

### The Problem
During early batch-mode testing, certain valid adjustment-backed discrepancies (e.g., gross fee adjustments or settlement fee deductions) were returned as `HUMAN_REVIEW` by the LLM because the LLM failed to link the prefetched adjustment record to the discrepancy.

### Root Cause Analysis
In the original batch pipeline, if the LLM output `HUMAN_REVIEW`, the controller accepted it blindly without re-checking whether objective financial proof existed in the underlying database.

### The Production Fix
Added a mandatory **post-LLM deterministic evidence validation step** in `batch_controller.py`:
1. After the LLM returns its proposal, Python calls `has_sufficient_resolution_evidence()`.
2. If documented adjustment records mathematically account for the discrepancy without contradiction, `build_proven_adjustment_resolution()` overrides the LLM's hesitation and outputs an authoritative `AUTO_RESOLVED` decision with full calculation proof.

### Impact on Test Dataset 03
- **Before Fix**: 19/20 correct (95.00% accuracy, 83.33% recall — 1 valid adjustment case missed).
- **After Fix**: **20/20 correct (100.00% accuracy, 100.00% recall, 100.00% precision)**.

---

## Data Integrity & Decimal Precision Safeguards

Financial systems cannot tolerate floating-point rounding errors (e.g., `0.1 + 0.2 = 0.30000000000000004`).

1. **Exact Decimal Parsing**: All monetary fields are parsed using Python's `Decimal` via `safe_decimal`. Floating-point conversion and integer truncation (`int(float(...))`) are strictly prohibited.
2. **Raw vs. Parsed Upload Invariants**: During CSV upload (`_parse_uploaded_csv`), raw strings are validated against normalized `Decimal` representations to prevent silent truncation.
3. **Provenance Tracking**: Every parsed record retains its source file name (`_source_file`) and row number (`_source_row`).
4. **Currency Formatting**: UI and audit logs format monetary values cleanly (e.g., `9357.5` $\rightarrow$ `₹9,357.50`).

---

## Canonical Data Normalizer (`src/normalizer/`)

The system includes a dedicated data normalizer to transform arbitrary third-party export files into canonical financial schemas:

- **Canonical Schemas**: Standard contracts for Payments, Ledgers, Bank Statements, and Adjustments.
- **Supported Formats**: Generic CSV files and public synthetic benchmarks (such as **IBM AMLSim synthetic transaction data**).
- **Features**: Schema auto-detection, manifest generation, normalization preview, and validation.

> [!IMPORTANT]
> **Data Labeling Notice**: Public datasets (such as IBM AMLSim) are **public synthetic financial benchmarks**, not private customer bank records.

---

## Intended User Experience & One-Click Workflow

The frontend dashboard is designed around **one primary user action**:

```text
Upload Source CSV Files (Optional)  ──►  Click "RUN RECONCILIATION"
                                                 │
                                                 ▼
               Automated Ingestion ──► Phase 1 Engine ──► AI Parallel Batches ──► Final Dashboard
```

Developer options (provider selection, model selection, custom batch sizes) are housed in a dedicated **Settings** panel to keep the primary operational workflow clean.

---

## Frontend Phase Lifecycle & Real-Time SSE Updates

To prevent background work from being mislabeled as Phase 1, the React application enforces distinct lifecycle states:

```text
[UPLOADING] ──► [VALIDATING] ──► [STARTING_RECONCILIATION] ──► [RUNNING_PHASE_1] ──► [RUNNING_AI] ──► [COMPLETED]
```

### Real-Time SSE Event Stream

Execution progress is streamed live over Server-Sent Events (SSE) via `/api/evaluations/{group_id}/stream`:

1. `run_started`: Emitted when the run starts.
2. `phase1_started`: Emitted when Phase 1 deterministic reconciliation begins.
3. `phase1_completed`: Emitted immediately upon Phase 1 completion (triggers UI transition to Phase 2).
4. `batch_started`: Emitted when a batch starts execution.
5. `case_completed`: Emitted as individual cases finish.
6. `batch_completed`: Emitted as each batch finishes (results rendered incrementally on screen).
7. `metrics_updated`: Live precision, recall, and accuracy updates.
8. `run_completed`: Final completion signal.

---

## Persistence, Auditability, and Failure Handling

- **Per-Batch Persistence**: As each batch finishes, decisions and metrics are persisted to SQLite. If a browser disconnects, progress is preserved.
- **Resume Support**: Interrupted runs can be resumed (`resume_group_id`) without re-investigating completed batches.
- **Provider API Error Isolation**: If an LLM provider returns an API error (e.g. rate-limit or quota error), the affected batch fast-fails safely to `NOT_EVALUATED` without stalling other batches or crashing the application.
- **Ground-Truth Policy**: Ground-truth labels are **NEVER** passed to the LLM. Ground truth is used exclusively after investigation to compute evaluation metrics. When no ground truth exists, benchmark cards are safely omitted.
- **Observability**: Developer trace mode (`--trace` or `SHOW_AGENT_TRACE=true`) logs operational milestones (`[ORCHESTRATOR]`, `[FINANCE ENGINE | PYTHON]`) without exposing raw prompt CoT or API secrets.

---

## Executive Exception Reporting Engine (`src/reporting/`)

The system includes a dedicated executive exception reporting generator (`src/reporting/exception_report.py`):

- **Structured Metrics**: Summarizes total transactions, reconciled volume, exception breakdown, auto-resolution rate, and human escalation lists.
- **Dual Export Formats**:
  - **Markdown (`.md`)**: Formatted executive report with financial tables, adjustment audit trails, and root-cause summaries.
  - **JSON (`.json`)**: Machine-readable data container for enterprise ERP ingestion and downstream compliance pipelines.
- **Access Points**:
  - **REST API**: `GET /api/runs/{run_id}/report?format=markdown|json&download=true`
  - **CLI Script**: `python scripts/generate_report.py --run-id <RUN_ID> --format markdown --out report.md`

---

## Modernized Operations Dashboard (`frontend/`)

The frontend application provides a reactive financial operations center built with React 18, Vite, and Tailwind CSS:

- **Modular Views (`src/views/`)**:
  - `DashboardView`: Primary one-click reconciliation workflow, real-time KPI metrics, and resolution breakdown.
  - `ExceptionsView`: Filterable discrepancy browser with categorized tabs and detailed transaction inspect modals.
  - `RunsView`: Historical run audit log with live status, duration tracking, and report downloads.
  - `SettingsView`: LLM provider configuration, temperature tuning, and batch sizing.
  - `AuditLogView`: Immutable event trail viewer for regulatory compliance.
- **Reactive Hooks & API Layer (`src/hooks/`, `src/lib/`)**:
  - `useActiveRun` & `useReconciliationRun`: Centralized SSE stream ingestion and state coordination.
  - `lib/api.js`: Unified API client with automatic error handling.
- **Run Progress Panel (`RunProgressPanel.jsx`)**: Real-time multi-stage visual progression showing Phase 1 deterministic matching through Phase 2 AI batch investigation.

---

## Repository Project Structure

```text
AI Finance Controller/
├── data/                       # Benchmark datasets & synthetic test fixtures
│   └── fixtures/               # Test datasets 01, 02, and 03
├── deploy/                     # Production deployment configurations
│   ├── Dockerfile              # Multi-stage production container build
│   └── docker-compose.yml      # Containerized backend & static UI deployment
├── docs/                       # Architectural documentation
│   └── architecture.md         # System architecture & design philosophy
├── frontend/                   # React 18 + Vite + Tailwind dashboard
│   ├── src/
│   │   ├── components/         # Header, KPI cards, tables, modal, progress panel
│   │   ├── hooks/              # useActiveRun, useReconciliationRun
│   │   ├── lib/                # Centralized API client (api.js)
│   │   └── views/              # Modularized views (Dashboard, Exceptions, Runs, etc.)
│   └── package.json
├── scripts/                    # Operational automation scripts
│   ├── generate_report.py      # CLI exception report generator
│   ├── run_dataset.py          # CLI batch dataset runner
│   └── run_llm_eval.py         # Evaluation benchmark runner
├── src/
│   ├── agent/                  # Agent controllers, prompts, schemas, tools
│   │   ├── multi_agent/        # MultiAgentOrchestrator & BatchMultiAgentController
│   │   ├── batch_controller.py # Batch Agent Controller & prefetching
│   │   ├── controller.py       # Individual Agent Controller
│   │   ├── evaluator.py        # Metrics computation & partitioning
│   │   ├── parallel_batch_engine.py # Async parallel batch scheduler
│   │   ├── prompts.py          # Structured system & user prompts
│   │   ├── schemas.py          # Pydantic data contracts
│   │   └── tools.py            # Deterministic financial tools
│   ├── api/                    # FastAPI routes (runs, evaluations, health)
│   │   └── routes/             # Modular API route controllers
│   ├── db/                     # SQLAlchemy models, database session, repository
│   ├── normalizer/             # Canonical schema normalizer & IBM AMLSim converter
│   ├── reporting/              # Executive Markdown & JSON report generator
│   ├── generator.py            # Synthetic financial data generator
│   ├── reconciliation.py       # Phase 1 deterministic reconciliation engine
│   ├── run_dataset.py          # Core CLI dataset runner
│   └── run_llm_eval.py         # Evaluation stream runner
├── tests/                      # 237 automated unit and integration tests
├── .env.example                # Environment variable configuration template
├── requirements.txt            # Python dependencies
└── README.md
```

---

## Installation & Getting Started

### 1. Prerequisites
- Python 3.11+
- Node.js 18+ (or Docker)

### 2. Clone & Install Dependencies
```bash
git clone https://github.com/cezzanrangrej/AI-Finance-Controller.git
cd "AI Finance Controller"

# Create Python virtual environment
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Install Python requirements
pip install -r requirements.txt
```

### 3. Environment Setup
```bash
cp .env.example .env
```
Edit `.env` to configure providers, or leave demo mode on for key-less operation:
```ini
DEMO_MODE=true
```
See [Provider Configuration](#provider-configuration) for live-provider setup.

### 4. Build Frontend
```bash
cd frontend
npm install
npm run build
cd ..
```

---

## Docker & Container Deployment

To launch the complete application stack (FastAPI backend + compiled React frontend) in a single Docker container:

```bash
docker compose -f deploy/docker-compose.yml up --build
```

Access the application at `http://localhost:8000`.

---

## CLI Usage Examples

### 1. Deterministic Phase 1 Dataset Run
Reconcile an explicit dataset using only the deterministic Phase 1 engine:
```bash
python src/run_dataset.py --data-dir "data/fixtures/dataset_03" --mode phase1
```

### 2. Full Automatic Exception Investigation (Batch Mode)
Reconcile a dataset and investigate all detected exceptions in parallel batches:
```bash
python src/run_dataset.py --data-dir "data/fixtures/dataset_03" --mode batch --batch-size 5
```

### 3. Batch Multi-Agent Investigation Mode
Investigate exceptions using concurrent batches with dual-agent investigator and verifier consensus:
```bash
python src/run_dataset.py --data-dir "data/fixtures/dataset_03" --mode multi-agent --batch-size 5 --trace
```

### 4. Generate Executive Exception Report via CLI
Generate an executive audit report in Markdown or JSON for any executed reconciliation run:
```bash
# Markdown Report to stdout or file
python scripts/generate_report.py --run-id run_abc12345 --format markdown --out report.md

# JSON Data Export
python scripts/generate_report.py --run-id run_abc12345 --format json --out report.json
```

---

## Running the Web Application Locally

### Launch FastAPI Backend
```bash
python -m uvicorn src.api.main:app --port 8000 --reload
```
API OpenAPI documentation is available at `http://localhost:8000/docs`.

### Launch React Frontend (Dev Server)
```bash
cd frontend
npm run dev
```
Dashboard is accessible at `http://localhost:5173`.

---

## Automated Test Suite

Run the full Python test suite (237 unit and integration tests):
```bash
python -m pytest -v
```

*Verified Test Results*: **237 passed, 2 skipped** (100% pass rate).

---

## Known Limitations

- **Public Synthetic Data**: Default test datasets are synthetic benchmarks generated for evaluation, not live production banking feeds.
- **Provider Latency Variability**: Wall-clock performance during Phase 2 AI investigation depends on external LLM provider API latency and rate limits.
- **Multi-Agent Overhead**: Multi-agent investigator/verifier mode incurs higher token consumption and latency than single-agent or batch modes.
- **Balanced Partitioning Heuristic**: Balanced exception-type partitioning is a deterministic scheduling heuristic, not a guaranteed mathematical proof of minimum batch time.
- **Read-Only Scope**: Discrepancies are flagged and proven for resolution or escalation; ledger adjustments are not posted directly to third-party ERPs without human approval.
- **Prototype Status**: Production deployment requires enterprise role-based access control (RBAC), KMS secret management, and distributed rate limiting.

---

## Future Roadmap

- **Semantic Veto for High-Value Proven Matches**: Gated multi-agent semantic verification over Layer-2-proven matches above configurable amount thresholds to detect coincidental arithmetic matches with conflicting narrative metadata.
- **High-Throughput Scale Testing**: Benchmark Phase 1 and parallel batch execution across 10,000+ transaction batches.
- **Latency-Aware Scheduling**: Dynamic batch scheduling based on historical per-exception-type execution latencies.
- **Additional Data Converters**: Expand `src/normalizer/` with additional ERP export formats (SAP, NetSuite, QuickBooks).
- **Advanced Operational Analytics**: Extended analytics for tracking merchant adjustment recovery rates over time.


