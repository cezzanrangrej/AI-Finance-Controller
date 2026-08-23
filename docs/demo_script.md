# 5-Minute Video Demonstration Script
## AI Finance Controller — Razorpay Buildathon Submission

---

### Timeline Overview
- **0:00 – 0:30**: Problem & Context
- **0:30 – 1:15**: Product Tour (Dashboard & Workflow)
- **1:15 – 2:00**: Architecture & Safety Division
- **2:00 – 3:00**: Live Investigation Walkthrough (Auto-Resolved vs. Human Review)
- **3:00 – 3:45**: Batch Investigation Optimization (81.5% Latency Reduction)
- **3:45 – 4:30**: Failure & Recovery Journey (Tool Loop Exhaustion Fix)
- **4:30 – 5:00**: Final Results & Closing

---

### 0:00 – 0:30 — Problem & Context
**Visual**: Show slide / opening title with high-volume transaction diagram (Gateway → ERP Ledger → Bank Settlement).

**Speaker**:
> "In digital commerce and high-volume financial operations, finance teams must continuously reconcile three distinct sources of truth: payment gateway authorization feeds, internal ERP general ledgers, and settlement bank statements.
> 
> When settlement discrepancies happen—such as unexplained fee deductions, missing ledger entries, or duplicate bank credits—reconciliation halts. Finance ops specialists spend hundreds of hours manually cross-referencing records to track down each discrepancy.
> 
> Standard automated rules flag that a difference exists, but they can't investigate *why*. Meanwhile, naive LLMs hallucinate calculations and cannot be trusted with financial arithmetic.
> 
> Meet the **AI Finance Controller**: an autonomous system combining deterministic rule-based matching with a tool-using AI investigation agent."

---

### 0:30 – 1:15 — Product Tour (Dashboard & Workflow)
**Visual**: Screen recording of the React Dashboard running at `http://localhost:5173`. Highlight top summary cards, filter tabs, and the Evaluation Panel.

**Speaker**:
> "Here is the AI Finance Controller Dashboard.
> 
> At a glance, you see the complete operational pipeline:
> - **100 source transactions** ingested across payments, ledger, and bank files.
> - **70 transactions** are instantly matched and reconciled by our Phase 1 deterministic engine in under 3 milliseconds.
> - **30 exceptions** are flagged for automated investigation.
> 
> When we run the AI Controller, the agent investigates each exception. Rather than dumping raw data into the LLM, the system executes an auditable investigative workflow:
> **Reconcile → Investigate → Resolve or Escalate**."

---

### 1:15 – 2:00 — Architecture & Safety Division
**Visual**: Display the ASCII / Architecture diagram showing Phase 1 Deterministic Engine, Read-Only Tools, AI Agent Controller, and Audit Log persistence.

**Speaker**:
> "The core philosophy of this project is strict **separation of concerns**:
> 
> 1. **Deterministic Python Engine**: Computes 100% of arithmetic, fee deductions, net settlement calculations, and duplicate detections. The AI is **never** asked to perform authoritative math.
> 2. **Phase 2 AI Agent**: Acts as an investigator. It chooses what records to inspect via read-only tools, correlates adjustment references with discrepancies, and interprets complex multi-source evidence.
> 3. **Safety Guardrails**: Strict Pydantic validation, immutable read-only source access, a hard limit of `MAX_TOOL_CALLS = 5`, and conservative escalation to human review whenever evidence is missing or ambiguous."

---

### 2:00 – 3:00 — Live Investigation Walkthrough
**Visual**: Click into Transaction `TXN003` in the dashboard, then transaction `TXN019`.

**Speaker**:
> "Let's look at two live cases:
> 
> **Case 1: Auto-Resolved (`TXN003`)**
> - In Phase 1, `TXN003` flagged a `BANK_AMOUNT_MISMATCH`—bank credited ₹14,110 instead of expected ₹14,210.
> - The agent investigates, calls `get_adjustments`, and discovers a documented gateway fee adjustment of ₹100.
> - The deterministic engine verifies the equation: `₹14,210 - ₹100 = ₹14,110`.
> - Because the discrepancy is mathematically proven, the agent marks this as **`AUTO_RESOLVED`** (`ADJUSTMENT_EXPLAINED`), eliminating human manual review.
> 
> **Case 2: Human Review Escalation (`TXN019`)**
> - `TXN019` has a bank credit ₹1,000 lower than expected settlement.
> - The agent inspects adjustments, but none exist.
> - Following our conservative safety policy, the agent refuses to guess and safely escalates to **`HUMAN_REVIEW`**, generating a structured recommendation for the finance team."

---

### 3:00 – 3:45 — Batch Investigation Optimization
**Visual**: Show the Evaluation Panel's Investigation Mode Architecture table and compare metrics.

**Speaker**:
> "To make real-LLM evaluation fast and cost-effective, we developed **Batch Investigation Mode**:
> 
> - In **Individual Mode**, the agent takes 59.6 seconds and 28,657 tokens across 5 cases due to dynamic multi-turn round trips.
> - In **Batch Mode**, Python prefetches all deterministic evidence and provides structured case packages to the LLM in a single request.
> - In our controlled 5-case benchmark with Llama 3.3 70B on OpenRouter:
>   - Latency dropped from **59.6s to 11.0s (81.5% reduction)**.
>   - Token usage dropped from **28,657 to 1,973 tokens (93.1% reduction)**.
>   - Decision accuracy, precision, and recall remained at **100.0%**."

---

### 4:30 – 5:00 — Failure & Recovery Journey
**Visual**: Show the Failure & Recovery section of the documentation or console traces.

**Speaker**:
> "One of our most valuable learnings came from an early real-LLM evaluation where accuracy dropped to 60% with 0% recall.
> 
> **What broke?** Traces showed the LLM retrieved sufficient proof on turn 1, but kept querying redundant tools until hitting `MAX_TOOL_CALLS = 5`, causing valid cases to incorrectly escalate.
> 
> **How we fixed it**:
> 1. Added mathematical evidence-sufficiency detection.
> 2. Implemented a deterministic resolution fast path upon proof.
> 3. Added tool-call deduplication and explicit stopping conditions.
> 
> As a result, targeted cases now resolve in a single tool call, and our 15-case evaluation achieved **100% accuracy, 100% precision, and 100% recall**."

---

### 4:30 – 5:00 — Final Results & Closing
**Visual**: Display the Final Evaluation Summary (`data/final_evaluation.json`) and test suite status (89 passed).

**Speaker**:
> "In summary:
> - **100% Phase 1 rule accuracy** across 100 transactions.
> - **100% Phase 2 decision accuracy, precision, and recall** on real-LLM benchmarks.
> - **81.5% lower latency** with Batch Mode.
> - **89 automated tests** verifying safety, edge cases, and provider interfaces.
> 
> AI Finance Controller proves that AI can bring transformative speed to finance operations without compromising on mathematical accuracy or audit safety.
> 
> Thank you!"
