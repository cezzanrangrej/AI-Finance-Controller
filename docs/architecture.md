# AI Finance Controller — Architecture & Design Philosophy

## System Philosophy

The AI Finance Controller is a production-shaped financial reconciliation engine designed to automate complex, multi-source transaction matching across Payment Gateways, Enterprise Resource Planning (ERP) Ledgers, and Bank Settlement Statements.

It combines a high-throughput, deterministic Phase 1 reconciliation engine with a parallel batch multi-agent LLM investigation system (Phase 2) to resolve exception cases, eliminate manual financial operations toil, and maintain an immutable audit trail.

---

## Architectural Pipeline

```text
                                  [Raw Financial Data Feeds]
                              (Payments, Ledger, Bank Records)
                                             │
                                             ▼
                             ┌────────────────────────────────┐
                             │  Phase 1: Deterministic Engine │
                             │   (ReconciliationEngine.py)    │
                             │  - 6 Strict Rule Checkers      │
                             │  - Python Decimal Precision    │
                             └───────────────┬────────────────┘
                                             │
                       ┌─────────────────────┴─────────────────────┐
                       ▼                                           ▼
             [RECONCILED (95-98%)]                         [EXCEPTIONS (2-5%)]
           (Zero LLM Cost, Instant)                                │
                                                                   ▼
                                                   ┌───────────────────────────────┐
                                                   │ Balanced Batch Partitioner    │
                                                   │    (batch_partitioner.py)     │
                                                   └───────────────┬───────────────┘
                                                                   │
                                                                   ▼
                                                   ┌───────────────────────────────┐
                                                   │ Parallel Batch Async Engine   │
                                                   │   (asyncio.Semaphore Worker)  │
                                                   └───────────────┬───────────────┘
                                                                   │
                                    ┌──────────────────────────────┴──────────────────────────────┐
                                    ▼                                                             ▼
                    ┌───────────────────────────────┐                             ┌───────────────────────────────┐
                    │      Investigator Agent       │                             │      Authoritative Proof      │
                    │      (Maker / Proposer)       │                             │     (Python Decimal Check)    │
                    │ - Read-Only Financial Toolkit │                             │ - Mathematical Proof Gate     │
                    │ - Gathers Facts & Hypothesis  │                             └───────────────┬───────────────┘
                    └───────────────┬───────────────┘                                             │
                                    │                                                             │
                                    ▼                                                             │
                    ┌───────────────────────────────┐                                             │
                    │        Verifier Agent         │                                             │
                    │      (Checker / Auditor)      │                                             │
                    │ - Conservative Review         │                                             │
                    │ - Tests Evidence & Conflicts  │                                             │
                    └───────────────┬───────────────┘                                             │
                                    │                                                             │
                                    └──────────────────────────────┬──────────────────────────────┘
                                                                   ▼
                                                   ┌───────────────────────────────┐
                                                   │  Consensus & Safety Policy    │
                                                   │ (AUTO_RESOLVED vs HUMAN_REV)  │
                                                   └───────────────┬───────────────┘
                                                                   │
                                       ┌───────────────────────────┴───────────────────────────┐
                                       ▼                                                       ▼
                            ┌─────────────────────┐                                 ┌─────────────────────┐
                            │    FastAPI & DB     │                                 │   Next.js / React   │
                            │  Audit Trails & SSE │◄────────────────────────────────┤ Real-Time Dashboard │
                            └─────────────────────┘                                 └─────────────────────┘
```

---

## Key Components

### 1. Deterministic Phase 1 Engine (`src/reconciliation.py`)
- Fast, non-LLM matching using exact transaction keys, gross amount verification, and fee calculations.
- Immediately passes ~70% of standard matching records without incurring LLM cost or latency.

### 2. Parallel Batch Multi-Agent Controller (`src/agent/multi_agent/`)
- **Investigator Agent**: Analyzes exception details against financial toolkit APIs (bank settlements, adjustment records, historical context) and proposes resolution decisions with evidence trails.
- **Verifier Agent**: Independently verifies proposed decisions and confidence scores against double-entry accounting rules before accepting or escalating to human review.

### 3. Core Repository & Database (`src/db/`)
- Built on SQLAlchemy with SQLite (local default) and PostgreSQL support (`DATABASE_URL`).
- Manages `reconciliation_runs`, `transaction_results`, `agent_investigations`, and immutable `audit_logs`.

### 4. REST API (`src/api/`)
- FastAPI application serving structured JSON responses for execution metrics, transaction details, live evaluations, and markdown report downloads (`GET /api/runs/{run_id}/report`).

### 5. Reactive Frontend (`frontend/`)
- React + Tailwind CSS single-page application built with Vite.
- Modularized views (`ExceptionsView`, `RunsView`, `SettingsView`, `AuditLogView`), custom state hooks (`useActiveRun`, `useReconciliationRun`), and centralized API client (`lib/api.js`).

---

## CLI & Evaluation Tools

- `scripts/run_dataset.py`: Command-line interface for running batch reconciliation on custom 4-file CSV datasets.
- `scripts/run_llm_eval.py`: Benchmark evaluation runner for evaluating LLM resolution precision and recall.
