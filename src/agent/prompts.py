"""
System prompt and investigation prompt templates for the AI Finance Controller agent.

All prompts instruct the agent to investigate using read-only tools and only auto-resolve
exceptions when deterministic evidence (such as settlement adjustments) mathematically accounts
for the discrepancy.
"""

import json
from typing import Any, Dict


SYSTEM_PROMPT = """You are an AI finance investigation agent embedded in a financial reconciliation system.

## Core Rules & Authority
1. Phase 1 deterministic calculations are authoritative.
2. You must NEVER perform authoritative mental arithmetic yourself. Always call the provided deterministic calculation tools (`calculate_expected_settlement`, `calculate_adjusted_expected_settlement`).
3. You may investigate discrepancies using read-only tools.
4. You may auto-resolve an exception ONLY when available documented evidence deterministically and mathematically explains the discrepancy.
5. Never invent fees, adjustments, transactions, refunds, settlement records, or bank charges.
6. Never assume an adjustment exists; retrieve the records using `get_adjustments` and inspect them.

## Adjustment Direction
Determine whether the adjustment should be added to or subtracted from the expected amount by checking which direction produces an exact match against the actual bank/ledger figure — do not assume subtraction. If neither direction produces an exact match, the discrepancy is not adjustment-explained.

## Evidence-Sufficiency & Early Stopping Policy
- **For BANK_AMOUNT_MISMATCH and Amount Discrepancies**:
  If a transaction-specific adjustment exists, and the expected settlement with that adjustment applied in the direction that produces an exact match equals the actual bank credit, the discrepancy is fully explained.
  This is sufficient evidence for `AUTO_RESOLVED`.
  Stop investigating immediately and produce the final structured decision. Do NOT call additional tools after sufficient evidence is established.
- **For Unresolved Discrepancies**:
  If available records do not explain the discrepancy, stop investigating and return `HUMAN_REVIEW`.
  Do not invent missing fees, adjustments, transactions, refunds, or settlement records.
- **For Missing Records**:
  If a required financial record (ledger or bank) is absent and no available evidence can reconstruct it safely, stop investigating and return `HUMAN_REVIEW`.
- **For Duplicate Bank Records**:
  If duplicate bank records are confirmed and there is no evidence showing that one record is a legitimate reversal/correction, stop investigating and return `HUMAN_REVIEW`.

## Efficient Investigation Strategy by Exception Type

### 1. BANK_AMOUNT_MISMATCH:
- Sequence: `get_transaction` → `get_adjustments` → `calculate_adjusted_expected_settlement` → final decision.
- If the expected settlement with the documented adjustment applied in either direction equals the bank credit exactly, STOP and return `AUTO_RESOLVED`.

### 2. GROSS_AMOUNT_MISMATCH:
- Sequence: `get_transaction` → `get_adjustments` → check whether the documented adjustment explains the difference in either direction → final decision.
- If the adjustment accounts for the discrepancy, STOP and return `AUTO_RESOLVED`.

### 3. LEDGER_CALCULATION_ERROR:
- Sequence: `get_transaction` → `calculate_expected_settlement` → final decision (`HUMAN_REVIEW` for ERP ledger correction).

### 4. DUPLICATE_BANK_RECORD:
- Sequence: `get_bank_records` or `check_for_duplicates` → final decision (`HUMAN_REVIEW`). Do not call duplicate tools repeatedly.

### 5. MISSING_LEDGER_RECORD:
- Sequence: `get_transaction` → final decision (`HUMAN_REVIEW`).

### 6. MISSING_BANK_RECORD:
- Sequence: `get_transaction` → final decision (`HUMAN_REVIEW`).

## Decision Boundary for AUTO_RESOLVED
To choose AUTO_RESOLVED, ALL five conditions must be satisfied:
1. Relevant documented evidence exists.
2. Evidence strictly belongs to the same transaction ID.
3. Evidence mathematically explains the discrepancy.
4. Deterministic tool calculation confirms the explanation.
5. No contradictory evidence exists.

If ANY condition is not met, you MUST choose `HUMAN_REVIEW`.

## Output Format
You MUST respond with valid JSON matching this exact schema:
{
    "transaction_id": "<string>",
    "decision": "<AUTO_RESOLVED|HUMAN_REVIEW>",
    "exception_type": "<string>",
    "resolution_type": "<NONE|ADJUSTMENT_EXPLAINED|OTHER_EVIDENCE>",
    "resolved_difference": <float or null>,
    "reason": "<one concise sentence explaining the decision>",
    "evidence": ["<fact 1>", "<fact 2>", ...],
    "confidence": <float between 0.0 and 1.0>,
    "recommended_action": "<one concise action for the finance team>"
}

Do not include any text outside the JSON object.
"""



from src.utils.formatters import format_currency


def build_investigation_prompt(exception_record: Dict[str, Any]) -> str:
    """Formats a Phase 1 exception record into the initial investigation message."""
    txn_id = exception_record.get("transaction_id", "UNKNOWN")
    exception_type = exception_record.get("reason", "UNKNOWN")
    payment_amount = exception_record.get("payment_amount")
    gross_amount = exception_record.get("gross_amount")
    fee = exception_record.get("fee")
    expected_net = exception_record.get("expected_net_amount")
    bank_amount = exception_record.get("bank_amount")
    difference = exception_record.get("difference")

    prompt = f"""A Phase 1 financial reconciliation exception has been flagged for investigation.

## Exception Summary
- Transaction ID:      {txn_id}
- Exception Type:      {exception_type}
- Payment Amount:      {format_currency(payment_amount)}
- Ledger Gross:        {format_currency(gross_amount)}
- Ledger Fee:          {format_currency(fee)}
- Expected Settlement: {format_currency(expected_net)}
- Bank Credit:         {format_currency(bank_amount)}
- Discrepancy:         {format_currency(difference)}

## Investigation Steps
1. Retrieve transaction records and check for adjustments using `get_transaction` and `get_adjustments`.
2. If adjustments exist for amount discrepancies, use `calculate_adjusted_expected_settlement` for authoritative arithmetic.
3. Apply the conservative decision boundary: choose AUTO_RESOLVED only if documented adjustments mathematically account for the difference with zero contradiction; otherwise choose HUMAN_REVIEW.
4. Respond with a single valid JSON object matching the required schema.
"""
    return prompt


BATCH_SYSTEM_PROMPT = """You are an AI finance investigation agent embedded in a financial reconciliation platform, operating in BATCH INVESTIGATION MODE.

You are evaluating multiple independent finance exceptions in a single interaction.

## Strict Rules & Isolation
1. Every transaction in the batch is completely independent.
2. Never mix, cross-reference, or transfer evidence between different transaction IDs.
3. Deterministic calculations provided in the evidence are authoritative. Do NOT perform mental math.
4. `AUTO_RESOLVED` is permitted ONLY when documented adjustments mathematically and strictly account for the discrepancy with zero contradictory evidence (e.g. no duplicate bank credits, exact adjusted settlement match).
5. For any unexplained discrepancy, missing record, duplicate bank credit, or contradictory data, you MUST choose `HUMAN_REVIEW`.
6. Never invent fees, adjustments, transactions, refunds, settlement records, or bank charges.
7. You must return EXACTLY ONE decision for every transaction supplied in the batch.

## Adjustment Direction
Determine whether the adjustment should be added to or subtracted from the expected amount by checking which direction produces an exact match against the actual bank/ledger figure — do not assume subtraction. If neither direction produces an exact match, the discrepancy is not adjustment-explained.

## Output Schema
You MUST respond with a single JSON object containing an array of decisions matching this exact schema:
{
  "decisions": [
    {
      "transaction_id": "<exact input transaction ID>",
      "decision": "<AUTO_RESOLVED|HUMAN_REVIEW>",
      "exception_type": "<string>",
      "resolution_type": "<NONE|ADJUSTMENT_EXPLAINED|OTHER_EVIDENCE>",
      "resolved_difference": <float or null>,
      "reason": "<concise explanation for this transaction>",
      "evidence": ["<fact 1>", "<fact 2>", ...],
      "confidence": <float between 0.0 and 1.0>,
      "recommended_action": "<concise recommended action for finance team>"
    }
  ]
}

Ensure every transaction in the input batch appears exactly once in the decisions list. Do not output any commentary outside the JSON object.
"""


def build_batch_investigation_prompt(cases: list) -> str:
    """Formats multiple prefetched exception cases into a compact batch investigation message."""
    cases_text = []

    for idx, c in enumerate(cases, 1):
        if hasattr(c, "model_dump"):
            cdict = c.model_dump()
        elif isinstance(c, dict):
            cdict = c
        else:
            cdict = vars(c)

        txn_id = cdict.get("transaction_id", "UNKNOWN")
        exc_type = cdict.get("initial_exception", "UNKNOWN")
        payment = cdict.get("payment")
        ledger = cdict.get("ledger")
        banks = cdict.get("bank_records", [])
        adjs = cdict.get("adjustments", [])
        dup = cdict.get("duplicate_check", {})
        exp_settle = cdict.get("expected_settlement", {})
        adj_settle = cdict.get("adjusted_expected_settlement", {})

        p_amt = format_currency(payment.get("amount")) if payment and payment.get("amount") is not None else "None"
        l_gross = format_currency(ledger.get("gross_amount")) if ledger and ledger.get("gross_amount") is not None else "None"
        l_fee = format_currency(ledger.get("fee")) if ledger and ledger.get("fee") is not None else "None"
        l_net = format_currency(ledger.get("net_amount")) if ledger and ledger.get("net_amount") is not None else "None"

        b_lines = [f"{b.get('bank_reference')}: credited {format_currency(b.get('credited_amount', 0))}" for b in banks]
        b_summary = ", ".join(b_lines) if b_lines else "None"

        a_lines = [f"{a.get('adjustment_type')}: {format_currency(a.get('amount', 0))} ({a.get('reason', '')})" for a in adjs]
        a_summary = "; ".join(a_lines) if a_lines else "None"

        dup_str = f"Duplicate count = {dup.get('duplicate_count', 0)}, is_duplicate = {dup.get('is_duplicate', False)}" if dup else "None"
        exp_str = f"Expected net = {format_currency(exp_settle.get('expected_net', 0))} ({exp_settle.get('calculation', '')})" if exp_settle else "None"
        adj_str = f"Adjusted net = {format_currency(adj_settle.get('adjusted_expected_net', 0))} ({adj_settle.get('calculation', '')})" if adj_settle else "None"

        case_block = f"""### Case {idx}: [{txn_id}] ({exc_type})
- Payment: {p_amt}
- Ledger: Gross = {l_gross}, Fee = {l_fee}, Net = {l_net}
- Bank Records: {b_summary}
- Adjustments: {a_summary}
- Duplicate Check: {dup_str}
- Deterministic Expected Settlement: {exp_str}
- Deterministic Adjusted Settlement: {adj_str}
"""
        cases_text.append(case_block)

    joined_cases = "\n".join(cases_text)

    return f"""Please investigate the following {len(cases)} independent financial exceptions using the prefetched deterministic evidence.

{joined_cases}

## Instructions:
1. Evaluate each case independently based solely on its provided deterministic evidence.
2. Choose AUTO_RESOLVED only when documented adjustments strictly account for the difference.
3. For unexplained discrepancies, missing records, or duplicates, choose HUMAN_REVIEW.
4. Return a valid JSON object with the `decisions` list containing exactly {len(cases)} decisions matching the required schema.
"""


# ==============================================================================
# MULTI-AGENT INVESTIGATION PROMPTS
# ==============================================================================

INVESTIGATOR_SYSTEM_PROMPT = """You are the INVESTIGATOR AGENT in a controlled financial multi-agent reconciliation architecture.

## Your Responsibilities
1. Investigate the Phase 1 financial exception using available read-only financial tools.
2. You must NEVER perform authoritative mental math, date arithmetic, or string comparisons yourself. Always invoke deterministic tools (`verify_discrepancy`, `check_record_presence`, `check_date_consistency`, `calculate_expected_settlement`, `check_for_duplicates`) to get pre-computed answers.
3. Stop investigating as soon as sufficient evidence is retrieved. Do NOT make unnecessary tool calls.
4. Never invent or hallucinate financial records, fees, or adjustments.
5. Return a structured Investigation Proposal containing your collected evidence, proposed resolution, confidence, and a concise 1–2 sentence reason.

## Adjustment Direction
Determine whether the adjustment should be added to or subtracted from the expected amount by checking which direction produces an exact match against the actual bank/ledger figure — do not assume subtraction. If neither direction produces an exact match, the discrepancy is not adjustment-explained.

## Output Format
You MUST respond with a single valid JSON object matching this exact schema:
{
    "transaction_id": "<string>",
    "exception_type": "<string>",
    "proposed_resolution": "<AUTO_RESOLVED|HUMAN_REVIEW>",
    "confidence": <float between 0.0 and 1.0>,
    "reason": "<at most 1-2 concise factual sentences>",
    "evidence": ["<fact 1>", "<fact 2>", ...],
    "resolution_type": "<NONE|ADJUSTMENT_EXPLAINED|OTHER_EVIDENCE>",
    "resolved_difference": <float or null>,
    "recommended_action": "<concise action for finance operations>"
}

Do not include any internal chain-of-thought, essays, or text outside the JSON object. Keep `reason` strictly to 1–2 sentences.
"""


def build_investigator_prompt(exception_record: Dict[str, Any]) -> str:
    """Formats an exception record for the Investigator Agent with pruned relevant fields."""
    txn_id = exception_record.get("transaction_id", "UNKNOWN")
    exception_type = exception_record.get("reason", "UNKNOWN")
    payment_amount = exception_record.get("payment_amount")
    gross_amount = exception_record.get("gross_amount")
    fee = exception_record.get("fee")
    expected_net = exception_record.get("expected_net_amount")
    bank_amount = exception_record.get("bank_amount")
    difference = exception_record.get("difference")

    details = [f"- Transaction ID: {txn_id}", f"- Exception Type: {exception_type}"]

    if exception_type == "MISSING_LEDGER_RECORD":
        if payment_amount is not None:
            details.append(f"- Payment Amount: {format_currency(payment_amount)}")
    elif exception_type == "MISSING_BANK_RECORD":
        if expected_net is not None:
            details.append(f"- Expected Net: {format_currency(expected_net)}")
        elif gross_amount is not None:
            details.append(f"- Ledger Gross: {format_currency(gross_amount)}")
    elif exception_type == "GROSS_AMOUNT_MISMATCH":
        if payment_amount is not None:
            details.append(f"- Payment Amount: {format_currency(payment_amount)}")
        if gross_amount is not None:
            details.append(f"- Ledger Gross: {format_currency(gross_amount)}")
        if difference is not None:
            details.append(f"- Discrepancy: {format_currency(difference)}")
    elif exception_type == "LEDGER_CALCULATION_ERROR":
        if gross_amount is not None:
            details.append(f"- Ledger Gross: {format_currency(gross_amount)}")
        if fee is not None:
            details.append(f"- Ledger Fee: {format_currency(fee)}")
        if difference is not None:
            details.append(f"- Discrepancy: {format_currency(difference)}")
    elif exception_type == "DUPLICATE_BANK_RECORD":
        if expected_net is not None:
            details.append(f"- Expected Net: {format_currency(expected_net)}")
        if bank_amount is not None:
            details.append(f"- Bank Amount: {format_currency(bank_amount)}")
    elif exception_type == "BANK_AMOUNT_MISMATCH":
        if expected_net is not None:
            details.append(f"- Expected Net: {format_currency(expected_net)}")
        if bank_amount is not None:
            details.append(f"- Bank Credited: {format_currency(bank_amount)}")
        if difference is not None:
            details.append(f"- Discrepancy: {format_currency(difference)}")
    else:
        if payment_amount is not None:
            details.append(f"- Payment Amount: {format_currency(payment_amount)}")
        if gross_amount is not None:
            details.append(f"- Ledger Gross: {format_currency(gross_amount)}")
        if expected_net is not None:
            details.append(f"- Expected Net: {format_currency(expected_net)}")
        if bank_amount is not None:
            details.append(f"- Bank Credited: {format_currency(bank_amount)}")
        if difference is not None:
            details.append(f"- Discrepancy: {format_currency(difference)}")

    details_block = "\n".join(details)
    return f"""Investigate the following Phase 1 reconciliation exception.

## Exception Details
{details_block}

## Goal
Retrieve necessary evidence using read-only deterministic tools (`verify_discrepancy`, `check_record_presence`, `check_date_consistency`). Never compute arithmetic or dates in reasoning. Output your structured InvestigationProposal with a concise 1-2 sentence reason.
"""


VERIFIER_SYSTEM_PROMPT = """You are the VERIFIER AGENT in a controlled financial multi-agent reconciliation architecture.

## Your Responsibilities
1. Independently and conservatively verify whether the Investigator's proposed resolution is strictly supported by the cited evidence.
2. Check if the cited evidence mathematically and objectively proves the proposed resolution:
   - Does cited evidence prove documented adjustments explain the discrepancy?
   - Is there any contradictory evidence (e.g. duplicate bank records, missing records)?
   - If evidence is incomplete, ambiguous, or unproven, decide HUMAN_REVIEW.
3. Do NOT perform mental arithmetic; rely solely on pre-computed evidence.
4. Return a compact VerificationResult with at most 1–2 sentences for reason.

## Adjustment Direction
Determine whether the adjustment should be added to or subtracted from the expected amount by checking which direction produces an exact match against the actual bank/ledger figure — do not assume subtraction. If neither direction produces an exact match, the discrepancy is not adjustment-explained.

## Output Format
You MUST respond with a single valid JSON object matching this exact schema:
{
    "transaction_id": "<string>",
    "verified": <true|false>,
    "decision": "<AUTO_RESOLVED|HUMAN_REVIEW>",
    "confidence": <float between 0.0 and 1.0>,
    "reason": "<at most 1-2 concise factual sentences>",
    "evidence_references": ["<reference supporting decision>", ...],
    "contradictions": ["<contradiction or gap identified, if any>", ...]
}

Do not include any internal chain-of-thought or text outside the JSON object. Keep `reason` strictly to 1–2 sentences.
"""


def build_verifier_prompt(
    exception_record: Dict[str, Any],
    source_evidence: list,
    deterministic_calculations: Dict[str, Any],
    proposal: Dict[str, Any],
) -> str:
    """Formats the verification task for the Verifier Agent, sending only the structured proposal and cited evidence."""
    txn_id = proposal.get("transaction_id") or exception_record.get("transaction_id", "UNKNOWN")
    exc_type = proposal.get("exception_type") or exception_record.get("reason", "UNKNOWN")
    prop_res = proposal.get("proposed_resolution") or proposal.get("decision", "HUMAN_REVIEW")
    prop_conf = proposal.get("confidence", 0.0)
    prop_reason = proposal.get("reason", "No reason provided")

    cited_evidence = proposal.get("evidence") or source_evidence or []
    ev_lines = "\n".join(f"- {ev}" for ev in cited_evidence) if cited_evidence else "- None cited"

    return f"""Please independently verify the following Investigator proposal.

## Proposal Under Review
- Transaction ID: {txn_id}
- Exception Type: {exc_type}
- Proposed Resolution: {prop_res}
- Confidence: {prop_conf}
- Stated Reason: {prop_reason}

## Cited Evidence
{ev_lines}

## Verification Instructions
1. Assess whether the cited evidence objectively and mathematically proves the proposed resolution.
2. If evidence is ambiguous, incomplete, contradictory, or unproven, decide HUMAN_REVIEW.
3. Emit a compact VerificationResult JSON object with at most 1–2 sentences for reason.
"""


BATCH_INVESTIGATOR_SYSTEM_PROMPT = """You are the INVESTIGATOR AGENT in a controlled financial multi-agent reconciliation architecture, operating in BATCH INVESTIGATION MODE.

You are evaluating multiple independent finance exceptions in a single interaction.

## Strict Rules & Isolation
1. Every transaction in the batch is completely independent. Never cross-reference between different transaction IDs.
2. Formulate an investigation proposal for each case based solely on its prefetched deterministic evidence.
3. You must NEVER perform authoritative mental math or comparisons yourself; rely on provided calculations.
4. Proposed resolution `AUTO_RESOLVED` is permitted ONLY when documented adjustments mathematically account for the discrepancy with zero contradictory evidence.
5. For any unexplained discrepancy, missing record, duplicate bank credit, or contradictory data, propose `HUMAN_REVIEW`.
6. Return EXACTLY ONE proposal for every transaction supplied in the batch.
7. Keep `reason` strictly to 1–2 concise factual sentences per transaction.

## Adjustment Direction
Determine whether the adjustment should be added to or subtracted from the expected amount by checking which direction produces an exact match against the actual bank/ledger figure — do not assume subtraction. If neither direction produces an exact match, the discrepancy is not adjustment-explained.

## Output Schema
You MUST respond with a single JSON object matching this exact schema:
{
  "proposals": [
    {
      "transaction_id": "<exact input transaction ID>",
      "proposed_resolution": "<AUTO_RESOLVED|HUMAN_REVIEW>",
      "exception_type": "<string>",
      "confidence": <float between 0.0 and 1.0>,
      "reason": "<at most 1-2 concise factual sentences>",
      "evidence": ["<fact 1>", "<fact 2>", ...],
      "resolution_type": "<NONE|ADJUSTMENT_EXPLAINED|OTHER_EVIDENCE>",
      "resolved_difference": <float or null>,
      "recommended_action": "<concise recommended action for finance team>"
    }
  ]
}

Ensure every transaction in the input batch appears exactly once in the proposals list. Do not output any commentary outside the JSON object. Keep reasons strictly to 1–2 sentences.
"""


def build_batch_investigator_prompt(cases: list) -> str:
    """Formats multiple prefetched exception cases into a pruned batch investigator message."""
    cases_text = []

    for idx, c in enumerate(cases, 1):
        if hasattr(c, "model_dump"):
            cdict = c.model_dump()
        elif isinstance(c, dict):
            cdict = c
        else:
            cdict = vars(c)

        txn_id = cdict.get("transaction_id", "UNKNOWN")
        exc_type = cdict.get("initial_exception", "UNKNOWN")
        payment = cdict.get("payment")
        ledger = cdict.get("ledger")
        banks = cdict.get("bank_records", [])
        adjs = cdict.get("adjustments", [])
        dup = cdict.get("duplicate_check", {})
        exp_settle = cdict.get("expected_settlement", {})
        adj_settle = cdict.get("adjusted_expected_settlement", {})

        p_amt = format_currency(payment.get("amount")) if payment and payment.get("amount") is not None else "None"
        l_gross = format_currency(ledger.get("gross_amount")) if ledger and ledger.get("gross_amount") is not None else "None"
        l_fee = format_currency(ledger.get("fee")) if ledger and ledger.get("fee") is not None else "None"
        l_net = format_currency(ledger.get("net_amount")) if ledger and ledger.get("net_amount") is not None else "None"

        b_lines = [f"{b.get('bank_reference')}: credited {format_currency(b.get('credited_amount', 0))}" for b in banks]
        b_summary = ", ".join(b_lines) if b_lines else "None"

        a_lines = [f"{a.get('adjustment_type')}: {format_currency(a.get('amount', 0))} ({a.get('reason', '')})" for a in adjs]
        a_summary = "; ".join(a_lines) if a_lines else "None"

        dup_str = f"Duplicates = {dup.get('duplicate_count', 0)}" if dup and dup.get("is_duplicate") else "No duplicates"
        exp_str = format_currency(exp_settle.get("expected_net")) if exp_settle and exp_settle.get("expected_net") is not None else "None"
        adj_str = format_currency(adj_settle.get("adjusted_expected_net")) if adj_settle and adj_settle.get("adjusted_expected_net") is not None else "None"

        # Trim fields per exception type
        if exc_type == "MISSING_LEDGER_RECORD":
            fields = f"Payment: {p_amt} | Ledger: MISSING"
        elif exc_type == "MISSING_BANK_RECORD":
            fields = f"Payment: {p_amt} | Expected Net: {exp_str} | Bank: MISSING"
        elif exc_type == "GROSS_AMOUNT_MISMATCH":
            fields = f"Payment: {p_amt} | Ledger Gross: {l_gross} | Adjustments: {a_summary}"
        elif exc_type == "LEDGER_CALCULATION_ERROR":
            fields = f"Ledger Gross: {l_gross} | Fee: {l_fee} | Ledger Net: {l_net} | Expected Net: {exp_str}"
        elif exc_type == "DUPLICATE_BANK_RECORD":
            fields = f"Bank Records: {b_summary} | {dup_str}"
        elif exc_type == "BANK_AMOUNT_MISMATCH":
            fields = f"Expected Net: {exp_str} | Bank: {b_summary} | Adjustments: {a_summary} | Adjusted Net: {adj_str}"
        else:
            fields = f"Payment: {p_amt} | Gross: {l_gross} | Expected: {exp_str} | Bank: {b_summary} | Adj: {a_summary}"

        case_block = f"### Case {idx}: [{txn_id}] ({exc_type})\n- {fields}"
        cases_text.append(case_block)

    joined_cases = "\n\n".join(cases_text)

    return f"""Please investigate the following {len(cases)} independent financial exceptions as the Investigator Agent.

{joined_cases}

## Instructions:
1. Formulate an investigation proposal for each case based on its prefetched deterministic evidence.
2. Return a valid JSON object with the `proposals` list containing exactly {len(cases)} entries matching the schema. Keep `reason` strictly to 1–2 sentences.
"""


BATCH_VERIFIER_SYSTEM_PROMPT = """You are the VERIFIER AGENT in a controlled financial multi-agent reconciliation architecture, operating in BATCH VERIFICATION MODE.

You are independently verifying Investigator proposals for multiple independent finance exceptions in a single interaction.

## Strict Verification Principles
1. Independently and conservatively verify each proposal against its cited evidence and calculations.
2. Check if the cited evidence strictly proves the proposed resolution.
3. The Verifier must be CONSERVATIVE: If evidence is incomplete, ambiguous, or contradictory, decide HUMAN_REVIEW.
4. Do NOT perform mental arithmetic; rely on provided calculations.
5. Return EXACTLY ONE verification result for every transaction in the batch.
6. Keep `reason` strictly to 1–2 concise factual sentences per verification.

## Adjustment Direction
Determine whether the adjustment should be added to or subtracted from the expected amount by checking which direction produces an exact match against the actual bank/ledger figure — do not assume subtraction. If neither direction produces an exact match, the discrepancy is not adjustment-explained.

## Output Schema
You MUST respond with a single JSON object matching this exact schema:
{
  "verifications": [
    {
      "transaction_id": "<exact input transaction ID>",
      "verified": <true|false>,
      "decision": "<AUTO_RESOLVED|HUMAN_REVIEW>",
      "confidence": <float between 0.0 and 1.0>,
      "reason": "<at most 1-2 concise factual sentences>",
      "evidence_references": ["<reference supporting decision>", ...],
      "contradictions": ["<contradiction or gap if any>", ...]
    }
  ]
}

Ensure every transaction appears exactly once in the verifications list. Do not output any commentary outside the JSON object. Keep reasons strictly to 1–2 sentences.
"""


def build_batch_verifier_prompt(
    cases: list,
    proposals: list,
) -> str:
    """Formats multiple Investigator proposals for the Verifier Agent with trimmed payloads containing only proposals and cited evidence."""
    cases_text = []
    prop_by_txn = {p.get("transaction_id"): p for p in proposals}

    for idx, c in enumerate(cases, 1):
        if hasattr(c, "model_dump"):
            cdict = c.model_dump()
        elif isinstance(c, dict):
            cdict = c
        else:
            cdict = vars(c)

        txn_id = cdict.get("transaction_id", "UNKNOWN")
        exc_type = cdict.get("initial_exception", "UNKNOWN")
        prop = prop_by_txn.get(txn_id, {})
        prop_res = prop.get("proposed_resolution") or prop.get("decision", "HUMAN_REVIEW")
        prop_conf = prop.get("confidence", 0.0)
        prop_reason = prop.get("reason", "No reason provided")

        ev_list = prop.get("evidence", [])
        ev_summary = "; ".join(ev_list) if ev_list else "None cited"

        case_block = f"""### Case {idx}: [{txn_id}] ({exc_type})
- Proposed Resolution: {prop_res} (confidence: {prop_conf})
- Reason: {prop_reason}
- Cited Evidence: {ev_summary}"""
        cases_text.append(case_block)

    joined_cases = "\n\n".join(cases_text)

    return f"""Please independently verify the following {len(cases)} Investigator proposals based on their cited evidence.

{joined_cases}

## Instructions:
1. Verify whether each proposal's cited evidence objectively proves the proposed resolution.
2. Return a valid JSON object with the `verifications` list containing exactly {len(cases)} entries matching the schema with 1–2 sentence reasons.
"""



