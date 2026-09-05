# ReconPilot — Architecture & Design Philosophy

## System Philosophy

ReconPilot is a production-shaped financial reconciliation engine designed to automate complex, multi-source transaction matching across Payment Gateways, Enterprise Resource Planning (ERP) Ledgers, and Bank Settlement Statements.

It combines a high-throughput, deterministic Phase 1 reconciliation engine with an upstream pre-batch deterministic proof filter and a parallel batch multi-agent LLM investigation system (Phase 2) to resolve exception cases, eliminate manual financial operations toil, and maintain an immutable audit trail.

---

## Architectural Pipeline

```text
                                  [Raw Financial Data Feeds]
                              (Payments, Ledger, Bank Records)
                                             │
                                             ▼
                             ┌────────────────────────────────┐
                             │  Step 1: Ingestion & Normalizer│
                             │    (src/normalizer/)           │
                             │  - Strict Python Decimal Coerce│
                             └───────────────┬────────────────┘
                                             │
                                             ▼
                             ┌────────────────────────────────┐
                             │  Step 2: Phase 1 Deterministic │
                             │   (src/reconciliation.py)      │
                             │  - 6 Strict Rule Checkers      │
                             │  - Gross, Fee, Bank, Duplicate │
                             └───────────────┬────────────────┘
                                             │
                       ┌─────────────────────┴─────────────────────┐
                       ▼                                           ▼
             [RECONCILED (70-95%)]                         [EXCEPTIONS (5-30%)]
           (Zero LLM Cost, Instant)                                │
                                                                   ▼
                                                   ┌───────────────────────────────┐
                                                   │ Step 3: Pre-Batch Proof Pass  │
                                                   │    (src/agent/pre_filter.py)  │
                                                   │  - Python Decimal Math Proof  │
                                                   │  - 0 LLM Tokens, 0 API Calls  │
                                                   └───────────────┬───────────────┘
                                                                   │
                                     ┌─────────────────────────────┴─────────────────────────────┐
                                     ▼                                                           ▼
                           [AUTO_RESOLVED (Proven)]                                    [AMBIGUOUS EXCEPTIONS]
                          (Deterministic Adjustment)                                             │
                                                                                                 ▼
                                                                                 ┌───────────────────────────────┐
                                                                                 │  Balanced Batch Partitioner   │
                                                                                 │    (batch_partitioner.py)     │
                                                                                 │  - Category Diversification   │
                                                                                 │  - Straggler Elimination      │
                                                                                 └───────────────┬───────────────┘
                                                                                                 │
                                                                                                 ▼
                                                                                 ┌───────────────────────────────┐
                                                                                 │ Step 4: Parallel Batch Engine │
                                                                                 │  (asyncio / Thread Workers)   │
                                                                                 └───────────────┬───────────────┘
                                                                                                 │
                                                                 ┌───────────────────────────────┴───────────────────────────────┐
                                                                 ▼                                                               ▼
                                                 ┌───────────────────────────────┐                               ┌───────────────────────────────┐
                                                 │      Investigator Agent       │                               │        Verifier Agent         │
                                                 │      (Maker / Proposer)       │                               │      (Checker / Auditor)      │
                                                 │ - Read-Only Financial Toolkit │══════════════════════════════>│ - Conservative Audit Review   │
                                                 │ - Correlates Unmatched Context│       (Proposed Evidence)     │ - Cross-Checks Source Records │
                                                 └───────────────────────────────┘                               └───────────────┬───────────────┘
                                                                                                                                 │
                                                                                                 ┌───────────────────────────────┘
                                                                                                 ▼
                                                                                 ┌───────────────────────────────┐
                                                                                 │   Consensus & Safety Policy   │
                                                                                 │  - Unanimous Agreement Check  │
                                                                                 │  - Conservative Escalation    │
                                                                                 └───────────────┬───────────────┘
                                                                                                 │
                                                                 ┌───────────────────────────────┴───────────────────────────────┐
                                                                 ▼                                                               ▼
                                                     [AUTO_RESOLVED (LLM)]                                               [HUMAN_REVIEW]
                                                   (Consensus-Backed Fix)                                            (Breaks / Missing Records)
                                                                 │                                                               │
                                                                 └───────────────────────────────┬───────────────────────────────┘
                                                                                                 │
                                                                                                 ▼
                                                                                 ┌───────────────────────────────┐
                                                                                 │  Step 5: Final Resolution     │
                                                                                 │  - Accounting Invariant Gate  │
                                                                                 │  - ACID SQLite Persistence    │
                                                                                 └───────────────┬───────────────┘
                                                                                                 │
                                                                     ┌───────────────────────────┴───────────────────────────┐
                                                                     ▼                                                       ▼
                                                          ┌─────────────────────┐                                 ┌─────────────────────┐
                                                          │    FastAPI Server   │                                 │   React 18 + Vite   │
                                                          │  Audit Trails & SSE │◄────────────────────────────────┤ 5-Stage Live Console│
                                                          └─────────────────────┘                                 └─────────────────────┘
```

---

## Key Components

### 1. Deterministic Phase 1 Engine (`src/reconciliation.py`)
- Fast, non-LLM matching evaluating 6 fundamental accounting checks (gross amount equality, ledger entry existence, fee calculations, bank clearance, duplicate detection, and net balance matching).
- Immediately passes 70–95% of standard matching records without incurring LLM cost or latency.

### 2. Pre-Batch Deterministic Proof Pass (`src/agent/pre_filter.py`)
- Runs an upstream arithmetic proof pass in Python memory *before* batch partitioning or AI dispatch.
- Checks whether documented adjustments arithmetically explain the discrepancy using exact arbitrary-precision `Decimal` math.
- Resolves provable cases as `AUTO_RESOLVED` (`source: DETERMINISTIC_PROOF`) at 0 LLM tokens and 0 API calls, leaving only genuinely ambiguous cases for the multi-agent pipeline.

### 3. Balanced Batch Partitioner (`src/agent/batch_partitioner.py`)
- Groups remaining ambiguous exceptions into balanced 5-case batches.
- Round-robins discrepancy categories across batches to eliminate worker thread bottlenecks and ensure uniform execution latency.

### 4. Parallel Batch Multi-Agent Controller (`src/agent/multi_agent/`)
- **Investigator Agent (Maker)**: Uses read-only financial tools to examine unmatched records, correlate missing ledger lines, and formulate structured investigation proposals.
- **Verifier Agent (Checker)**: Independently verifies proposed decisions and confidence scores against double-entry accounting rules and raw ledger records.
- **Consensus & Conservative Escalation**: Disputed, incomplete, or unprovable discrepancies safely escalate to `HUMAN_REVIEW`.

### 5. Core Repository & Database (`src/db/`)
- Built on SQLAlchemy with SQLite (local default) and PostgreSQL support (`DATABASE_URL`).
- Manages `reconciliation_runs`, `transaction_results`, `agent_investigations`, and immutable `audit_logs`.
- Enforces strict accounting invariant preservation: `total == reconciled + auto_resolved + human_review + not_evaluated`.

### 6. REST API & SSE Pipeline (`src/api/`)
- FastAPI application serving structured JSON responses for execution metrics, transaction details, live evaluations, and markdown report downloads (`GET /api/runs/{run_id}/report`).
- Full lifecycle Server-Sent Events (SSE) streaming (`pre_filter_started`, `pre_filter_completed`, `phase2_batch_progress`, etc.) for real-time frontend updates.

### 7. Reactive 5-Stage Frontend (`frontend/`)
- React 18 + Tailwind CSS single-page application built with Vite.
- Real-time 5-stage progress panel displaying live actual metrics across Ingestion, Phase 1 Matching, Pre-Batch Proof, AI Multi-Agent Investigation, and Final Resolution.
- Modularized views (`ExceptionsView`, `RunsView`, `SettingsView`, `AuditLogView`), custom state hooks (`useActiveRun`, `useReconciliationRun`), and centralized API client (`lib/api.js`).

---

## CLI & Evaluation Tools

- `scripts/run_dataset.py`: Command-line interface for running batch reconciliation on custom 4-file CSV datasets.
- `scripts/run_llm_eval.py`: Benchmark evaluation runner for evaluating LLM resolution precision and recall.
