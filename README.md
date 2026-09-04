# AI Finance Controller

> An enterprise financial reconciliation and exception-investigation engine that pairs **deterministic double-entry accounting rules (Python/Decimal)** with **parallel multi-agent LLM reasoning** to audit multi-source ledgers, prove settlement discrepancies mathematically, and safely escalate unresolved cases.

---

## The Problem, Briefly

In digital commerce and enterprise finance, transactions flow across fragmented systems—payment gateways (e.g., Stripe), internal ERP general ledgers (e.g., NetSuite), and bank settlement statements. Discrepancies constantly arise from processing fee deductions, timing delays, batch settlements, currency conversions, and data anomalies.

Traditional financial operations face two critical failure modes:
- **Brittle Rule Scripts & Manual Audits** : Static rule systems break when fees or settlement timings deviate from hardcoded assumptions, pushing thousands of unmatched lines into manual spreadsheets where human investigation costs hours per case.
- **Naive LLM Automation**: Generative models cannot be trusted with financial calculations. Standard LLMs suffer from floating-point inaccuracies, hallucinate fictitious balance adjustments, and lack auditability.

**AI Finance Controller** solves this with a hybrid architecture: deterministic Python/`Decimal` arithmetic is strictly authoritative for balances and verification, while intelligent multi-agent LLMs are selectively deployed only to investigate context, correlate ambiguous adjustments, and draft audit trails.

---

## Architecture Overview

The system operates as a two-phase pipeline with strict separation between deterministic accounting and AI-driven reasoning:

```text
Financial CSV Sources (Payments, ERP Ledger, Bank Statements, Adjustments)
                            │
                            ▼
        ┌──────────────────────────────────────────┐
        │ Canonical Data Normalization Layer       │
        │ (Decimal precision & schema invariants)  │
        └───────────────────┬──────────────────────┘
                            │
                            ▼
        ┌──────────────────────────────────────────┐
        │ Phase 1: Deterministic Engine (Python)   │
        │ (~5ms / 100 records · 6 accounting checks│
        └───────────┬──────────────────┬───────────┘
                    │                  │
                    ▼                  ▼
             RECONCILED           EXCEPTIONS
          (Passed Invariants)   (Discrepancies)
                                       │
                                       ▼
        ┌──────────────────────────────────────────┐
        │ Balanced Batch Scheduler & Concurrency   │
        │ (5-case diversified batches · Pool ≤ 5)  │
        └───────────────────┬──────────────────────┘
                            │
                            ▼
        ┌──────────────────────────────────────────┐
        │ Phase 2: AI Multi-Agent Investigation    │
        │ ┌──────────────────────────────────────┐ │
        │ │ Investigator Agent                   │ │
        │ │ Correlates evidence & proposes fix   │ │
        │ └──────────────────┬───────────────────┘ │
        │                    │                     │
        │                    ▼                     │
        │ ┌──────────────────────────────────────┐ │
        │ │ Deterministic Proof Engine (Python)  │ │
        │ │ Validates math & adjustment evidence │ │
        │ └──────────────────┬───────────────────┘ │
        │                    │                     │
        │                    ▼                     │
        │ ┌──────────────────────────────────────┐ │
        │ │ Verifier Agent                       │ │
        │ │ Independently critiques proposal     │ │
        │ └──────────────────────────────────────┘ │
        └───────────────────┬──────────────────────┘
                            │
                            ▼
        ┌──────────────────────────────────────────┐
        │ Decision & Escalation Policy             │
        │ AUTO_RESOLVED  or  HUMAN_REVIEW          │
        └───────────────────┬──────────────────────┘
                            │
                            ▼
        ┌──────────────────────────────────────────┐
        │ Live SSE Stream & SQLite Persistence     │
        │ (Real-time updates to React Operations)  │
        └──────────────────────────────────────────┘
```

### Pipeline Flow
1. **Canonical Ingestion & Normalization (`src/normalizer/`)**: Raw source files (Payments, ERP Ledgers, Bank Statements, Adjustments) are parsed into canonical models. All currency values are coerced into exact Python `Decimal` representations to eliminate floating-point drift.
2. **Phase 1 Deterministic Matching (`src/reconciliation.py`)**: Executes in ~5 milliseconds per 100 transactions. Evaluates 6 fundamental accounting checks (gross amount equality, ledger entry existence, fee calculations, bank clearance, duplicate detection, and net balance matching). Exactly matched records are closed immediately.
3. **Balanced Batch Partitioning (`src/agent/batch_partitioner.py`)**: Only unresolved Phase 1 exceptions are forwarded to Phase 2. To avoid straggler bottlenecks, exceptions are categorized by discrepancy type and scheduled into balanced 5-case batches across concurrent worker threads.
4. **Phase 2 AI Investigation (`src/agent/multi_agent/`)**:
   - **Investigator Agent**: Queries tools and correlates adjustments to formulate an `InvestigationProposal`.
   - **Deterministic Proof Engine**: Verifies that any proposed resolution mathematically balances the discrepancy against verified adjustment records (`has_sufficient_resolution_evidence()`).
   - **Verifier Agent**: Independently critiques the resolution against raw source records.
   - **Consensus Policy**: If both agents agree and arithmetic proof holds, the case is marked `AUTO_RESOLVED`. Any ambiguity, missing proof, or agent disagreement automatically routes the case to `HUMAN_REVIEW`.
5. **Real-Time SSE Streaming & Persistence (`src/api/routes/runs.py`)**: Lifecycle milestones (`phase1_completed`, `batch_started`, `case_completed`, `batch_completed`) stream over Server-Sent Events to the React dashboard while recording an immutable SQLite audit log.

---

## File Structure

```text
AI-Finance-Controller/
├── data/
│   └── fixtures/               # Benchmark datasets (Datasets 01, 02, 03)
├── deploy/
│   ├── Dockerfile              # Multi-stage production container build
│   └── docker-compose.yml      # Containerized backend & static UI deployment
├── docs/
│   └── architecture.md         # Detailed architectural documentation
├── frontend/                   # Modern React 18 + Vite dashboard
│   ├── src/
│   │   ├── components/         # UI components (KPI cards, tables, modals, progress panels)
│   │   ├── hooks/              # useActiveRun, useReconciliationRun (SSE stream hooks)
│   │   ├── lib/                # API client (api.js)
│   │   ├── views/              # Modular views (Dashboard, Exceptions, Runs, Settings, Audit)
│   │   ├── App.jsx             # Main application layout and state coordinator
│   │   └── main.jsx            # React root entry point
│   ├── package.json
│   └── vite.config.js
├── scripts/
│   ├── generate_report.py      # CLI script to generate executive exception reports
│   └── run_dataset.py          # Benchmark test dataset CLI runner
├── src/
│   ├── agent/                  # AI agents, orchestrators, and tool contracts
│   │   ├── multi_agent/        # Dual-agent architecture
│   │   │   ├── investigator.py # Investigator Agent logic
│   │   │   ├── verifier.py     # Verifier Agent logic
│   │   │   ├── orchestrator.py # MultiAgentOrchestrator consensus manager
│   │   │   └── batch_multi_agent_controller.py # Parallel batch multi-agent controller
│   │   ├── batch_controller.py # Single-agent batch controller
│   │   ├── batch_partitioner.py# Balanced exception diversification scheduler
│   │   ├── controller.py       # Individual interactive agent controller
│   │   ├── evaluator.py        # Accuracy, precision, recall evaluation engine
│   │   ├── gemini_client.py    # Google Gemini client with retry and error extraction
│   │   ├── grok_client.py      # xAI Grok client
│   │   ├── openrouter_client.py# OpenRouter client
│   │   ├── parallel_batch_engine.py # Async parallel batch execution engine
│   │   ├── prompts.py          # Structured system and verification prompts
│   │   ├── provider_resolution.py # Dynamic provider/credential resolution
│   │   ├── rate_limit.py       # LLMRateLimitError, jittered backoff, and retry wrapper
│   │   ├── schemas.py          # Pydantic data contracts and models
│   │   ├── tools.py            # Deterministic financial lookup and calculation tools
│   │   └── trace.py            # Sanitized operational observability logging
│   ├── api/                    # FastAPI web backend
│   │   ├── routes/             # API routes (evaluations, runs, reports, health)
│   │   └── main.py             # FastAPI entrypoint and SSE event handlers
│   ├── db/                     # SQLAlchemy models, sessions, and persistence layer
│   ├── normalizer/             # Canonical schema normalizer & public benchmark converter
│   ├── reporting/              # Executive Markdown and JSON audit report generators
│   ├── config.py               # Centralized configuration and environment defaults
│   ├── generator.py            # Synthetic financial dataset generator
│   └── reconciliation.py       # Phase 1 deterministic double-entry engine
├── tests/                      # Automated test suite (unit, integration, streaming)
├── .env.example                # Environment variables template
├── requirements.txt            # Python dependencies
└── README.md                   # Project documentation
```

---

## Key Design Decisions, and Why

### 1. Authoritative Python/Decimal Over LLM Arithmetic
- **Decision**: All financial arithmetic, balance checks, and evidence evaluations are performed strictly in Python using arbitrary-precision `Decimal`. LLMs are forbidden from performing unverified math.
- **Why**: Standard IEEE 754 floating-point numbers introduce rounding errors (`0.1 + 0.2 = 0.30000000000000004`), while generative LLMs frequently hallucinate arithmetic totals. In this architecture, LLMs hypothesize correlations, but the Python proof engine verifies that adjustments sum up to the exact penny before any resolution is accepted.

### 2. Selective AI Invocation & Balanced Batching
- **Decision**: Records are never sent to an LLM on a 1:1 basis. 100% of records pass through Phase 1 deterministic rules first; only un-reconciled exceptions are routed to Phase 2 in balanced 5-case batches.
- **Why**: In typical financial datasets, 70–90% of transactions match cleanly. Running full LLM inference across every transaction wastes immense latency and API budget. Filtering first and grouping exceptions into balanced batches reduces token consumption by **>90%** and wall-clock execution time by **>80%**.

### 3. Dual-Agent Separation with Conservative Escalation
- **Decision**: In multi-agent mode, an Investigator Agent proposes resolutions while an independent Verifier Agent critiques the proposal against raw source records. If the agents disagree or evidence is incomplete, the system escalates to `HUMAN_REVIEW`.
- **Why**: Financial compliance requires defense-in-depth. Single-agent setups are vulnerable to confirmation bias. Separating investigation from verification enforces consensus and guarantees zero false-positive auto-resolutions on unprovable discrepancies.

### 4. Resilient Multi-Tier Rate-Limit Defense
- **Decision**: Integrated a dedicated rate-limit layer (`LLMRateLimitError`) with per-thread exponential backoff, jitter, and automatic retry-after parsing. If provider quota is completely exhausted (HTTP 429), the affected batch fast-fails to `NOT_EVALUATED` rather than crashing the system.
- **Why**: Free-tier or shared enterprise LLM quotas often experience burst throttling. Thread-independent retries prevent a single throttled thread from blocking others. If quota is exhausted, isolating failures to `NOT_EVALUATED` preserves the rest of the run and leaves a clean audit trail.

### 5. Strict Accounting Invariant Preservation
- **Decision**: The system enforces that `total_records == reconciled + auto_resolved + human_review + not_evaluated` at every lifecycle stage, including unexpected cancellations and API provider errors.
- **Why**: In financial accounting, an unaccounted-for record is a catastrophic data leak. Guaranteeing that every record is cataloged ensures complete regulatory auditability under all operating conditions.

### 6. Diversified Exception-Type Scheduling
- **Decision**: Rather than grouping exceptions sequentially (`[0..5]`, `[5..10]`), the scheduler round-robins different exception categories (e.g., fee mismatches, missing bank lines, duplicate charges) across batches.
- **Why**: Parallel batch latency is dictated by the slowest worker. Spreading tool-intensive or complex exception types across batches prevents hotspot worker threads from inflating total run time.

---

## Setup / How to Run It

### Prerequisites
- **Python**: Version 3.11 or higher
- **Node.js**: Version 18 or higher (with npm)
- *Optional*: Docker and Docker Compose

---

### 1. Backend Setup

```bash
# Clone the repository
git clone https://github.com/cezzanrangrej/AI-Finance-Controller.git
cd "AI Finance Controller"

# Create and activate virtual environment
python -m venv venv
# Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# macOS/Linux:
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables

```bash
# Copy template configuration
cp .env.example .env
```

Edit `.env` to configure your preferred execution mode:

```ini
# --- Option A: Zero-Key Offline Demo Mode (Default) ---
DEMO_MODE=true

# --- Option B: Live Providers (Google Gemini / OpenRouter / xAI) ---
# For Gemini:
INVESTIGATOR_PROVIDER=gemini
INVESTIGATOR_MODEL=gemini-2.5-flash
GEMINI_API_KEY=your_gemini_api_key

# For OpenRouter (optional Verifier or Investigator):
VERIFIER_PROVIDER=openrouter
VERIFIER_MODEL=meta-llama/llama-3.3-70b-instruct
OPENROUTER_API_KEY=your_openrouter_api_key


---

### 3. Frontend Setup

```bash
cd frontend
npm install
cd ..
```

---

### 4. Running the Application

#### Terminal 1 — FastAPI Backend:
```bash
python -m uvicorn src.api.main:app --port 8000 --reload
```
API OpenAPI Swagger documentation is available at `http://localhost:8000/docs`.

#### Terminal 2 — React Frontend:
```bash
cd frontend
npm run dev
```
Open `http://localhost:5173` in your browser. Click **Run Reconciliation** to start live analysis.

---

### 5. Running with Docker Compose (Single Container)

To launch both the backend API and compiled frontend together in Docker:

```bash
docker compose -f deploy/docker-compose.yml up --build
```
The full application will be accessible at `http://localhost:8000`.

---

### 6. CLI Execution & Benchmark Scripts

Run reconciliation directly from the command line:

```bash
# Deterministic Phase 1 matching only:
python src/run_dataset.py --data-dir "data/fixtures/dataset_03" --mode phase1

# Full reconciliation with parallel batch AI investigation:
python src/run_dataset.py --data-dir "data/fixtures/dataset_03" --mode batch --batch-size 5

# Multi-agent investigation with live trace output:
python src/run_dataset.py --data-dir "data/fixtures/dataset_03" --mode multi-agent --batch-size 5 --trace

# Export executive audit report (Markdown or JSON):
python scripts/generate_report.py --run-id <RUN_ID> --format markdown --out audit_report.md
```

---

### 7. Running the Automated Test Suite

Execute the full automated test suite (303 passed, 2 skipped):

```bash
python -m pytest tests/ -v
```

---

## Tech Stack

| Layer | Technology | Purpose |
| :--- | :--- | :--- |
| **Core Accounting Engine** | Python 3.11+, `Decimal` | Exact arbitrary-precision financial math; double-entry invariant validation |
| **API & Backend** | FastAPI, Uvicorn, Pydantic v2 | High-performance asynchronous REST endpoints & Server-Sent Events (SSE) |
| **Database & Persistence** | SQLAlchemy 2.0, SQLite | ACID transactional storage of reconciliation runs, cases, and immutable audit logs |
| **AI & LLM Orchestration** | Google GenAI SDK, OpenRouter | Multi-agent reasoning, evidence synthesis, and structured JSON outputs |
| **Concurrency & Resilience** | ThreadPoolExecutor, Tenacity | Parallel batch scheduling, per-thread retry loops, and jittered exponential backoff |
| **Frontend Dashboard** | React 18, Vite, Tailwind CSS | Reactive operations console with live SSE streaming, KPI metrics, and inspect modals |
| **UI Components & Icons** | Lucide React | Modern, accessible financial dashboard iconography |
| **Testing & Quality** | Pytest, HTTPX | Comprehensive unit, integration, and streaming test coverage (300+ tests) |
| **Containerization** | Docker, Docker Compose | Multi-stage production container build serving API and compiled SPA bundle |

---

## What's Genuinely Working vs. Known Limitations

### What's Genuinely Working

- **Instant Phase 1 Deterministic Engine**: Evaluates 6 core double-entry accounting rules across 100 transactions in ~5 milliseconds with 100% mathematical precision (zero floating-point error).
- **Parallel Batch AI Investigation**: Groups exceptions into balanced 5-case batches and processes them concurrently across worker threads, achieving >80% latency reduction and >90% token savings compared to serial single-case investigation.
- **Post-LLM Deterministic Proof Engine**: Validates every LLM proposal against database records (`has_sufficient_resolution_evidence()`). Automatically promotes valid adjustment-backed cases to `AUTO_RESOLVED` and provides calculation proofs.
- **Multi-Agent Consensus**: Investigator and Verifier dual-agent collaboration with strict conservative escalation: unresolved, incomplete, or disputed cases are safely escalated to `HUMAN_REVIEW`.
- **Live SSE Event Streaming**: Full multi-stage lifecycle updates (`phase1_started`, `batch_started`, `case_completed`, `batch_completed`) stream in real time to the React dashboard with active batch chips and progress bars.
- **Provider Resilience & Rate-Limit Defense**: Thread-isolated retries with jittered exponential backoff; gracefully handles HTTP 429 quota exhaustion by marking affected cases `NOT_EVALUATED` without stalling other threads.
- **Comprehensive Test Suite & Production Build**: 303 automated tests passing in Python; clean production frontend bundle (`npm run build`) with zero errors.
- **Full Auditability & Report Exports**: Detailed audit logs, execution traces, and executive report export in both Markdown and JSON formats.

### Known Limitations

- **Read-Only Operation**: The system investigates, explains, and proves settlement discrepancies; it does not directly trigger money movements or commit adjustment entries to external banking APIs or ERP systems without human sign-off.
- **Provider Latency & Rate Limits**: Wall-clock performance during Phase 2 is bound by external LLM provider API speeds and tier quotas. Free-tier accounts may hit burst rate limits on high-concurrency workloads.
- **Public Synthetic Datasets**: Bundled demonstration datasets (Datasets 01, 02, and 03) are synthetic benchmarks designed to test edge cases, rather than live banking feeds.
- **Single-Tenant Architecture**: Designed for single-tenant operations or dedicated instances. Enterprise multi-tenant deployment would require external authentication/RBAC (e.g., OAuth2/OIDC) and distributed task queues (e.g., Redis/Celery).
