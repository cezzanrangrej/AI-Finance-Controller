"""
Tests for Agent Optimization: Deterministic Python Tools, Trimmed Prompt Payloads, and Compact Schemas.
"""

import json
from unittest.mock import MagicMock
import pytest

from src.agent.tools import FinancialToolkit
from src.agent.prompts import (
    build_investigator_prompt,
    build_verifier_prompt,
    build_batch_investigator_prompt,
    build_batch_verifier_prompt,
)
from src.agent.schemas import InvestigationProposal, VerificationResult
from src.agent.multi_agent.investigator import InvestigatorAgent
from src.agent.multi_agent.verifier import VerifierAgent
from src.agent.controller import LLMClient, EvidenceState, has_sufficient_resolution_evidence


@pytest.fixture
def sample_toolkit():
    payments = [
        {"transaction_id": "TXN_001", "amount": 10000, "date": "2026-03-01"},
        {"transaction_id": "TXN_002", "amount": 5000, "date": "2026-03-01"},
        {"transaction_id": "TXN_003", "amount": 8000, "date": "2026-03-01"},
        {"transaction_id": "TXN_DUP", "amount": 6000, "date": "2026-03-01"},
    ]
    ledger = [
        {"transaction_id": "TXN_001", "gross_amount": 10000, "fee": 300, "net_amount": 9700, "date": "2026-03-01"},
        # TXN_002 is missing in ledger
        {"transaction_id": "TXN_003", "gross_amount": 7500, "fee": 200, "net_amount": 7300, "date": "2026-03-01"},
        {"transaction_id": "TXN_DUP", "gross_amount": 6000, "fee": 100, "net_amount": 5900, "date": "2026-03-01"},
    ]
    bank = [
        {"transaction_id": "TXN_001", "bank_reference": "BNK_001", "credited_amount": 9500, "date": "2026-03-02"},
        {"transaction_id": "TXN_002", "bank_reference": "BNK_002", "credited_amount": 5000, "date": "2026-03-02"},
        # TXN_003 missing bank
        {"transaction_id": "TXN_DUP", "bank_reference": "BNK_D1", "credited_amount": 5900, "date": "2026-03-02"},
        {"transaction_id": "TXN_DUP", "bank_reference": "BNK_D2", "credited_amount": 5900, "date": "2026-03-02"},
    ]
    adjustments = [
        {"transaction_id": "TXN_001", "adjustment_type": "FEE_ADJUSTMENT", "amount": 200, "reason": "Tier rebate", "date": "2026-03-02", "reference": "ADJ_TXN_001"},
        {"transaction_id": "TXN_003", "adjustment_type": "PROMO_DISCOUNT", "amount": 500, "reason": "Coupon discount", "date": "2026-03-01", "reference": "ADJ_TXN_003"},
    ]
    return FinancialToolkit(payments=payments, ledger_records=ledger, bank_records=bank, adjustments=adjustments)


def test_verify_discrepancy_bank_adjustment_explained(sample_toolkit):
    """Verifies that an adjustment exactly explaining the bank gap returns discrepancy_fully_explained=True."""
    res = sample_toolkit.verify_discrepancy("TXN_001")
    assert res["discrepancy_fully_explained"] is True
    assert res["match_type"] == "BANK_ADJUSTMENT"
    assert res["resolved_difference"] == 200
    assert res["is_duplicate_bank"] is False
    assert "exactly matches" in res["explanation"]


def test_verify_discrepancy_gross_adjustment_explained(sample_toolkit):
    """Verifies that an adjustment explaining gross mismatch returns discrepancy_fully_explained=True."""
    res = sample_toolkit.verify_discrepancy("TXN_003")
    assert res["discrepancy_fully_explained"] is True
    assert res["match_type"] == "GROSS_ADJUSTMENT"
    assert res["resolved_difference"] == 500


def test_verify_discrepancy_duplicate_bank_detection(sample_toolkit):
    """Verifies that duplicate bank credits immediately flag is_duplicate_bank=True and require human review."""
    res = sample_toolkit.verify_discrepancy("TXN_DUP")
    assert res["is_duplicate_bank"] is True
    assert res["discrepancy_fully_explained"] is False
    assert "Multiple" in res["explanation"]


def test_check_record_presence(sample_toolkit):
    """Verifies deterministic record existence and missing flag detection."""
    p2 = sample_toolkit.check_record_presence("TXN_002")
    assert p2["has_payment"] is True
    assert p2["has_ledger"] is False
    assert "LEDGER" in p2["missing_records"]

    p3 = sample_toolkit.check_record_presence("TXN_003")
    assert p3["has_bank"] is False
    assert "BANK" in p3["missing_records"]
    assert p3["adjustment_references_valid"] is True


def test_check_date_consistency(sample_toolkit):
    """Verifies deterministic date math across payment, ledger, and bank."""
    d1 = sample_toolkit.check_date_consistency("TXN_001")
    assert d1["dates_consistent"] is True
    assert d1["max_day_difference"] == 1
    assert d1["payment_date"] == "2026-03-01"


def test_has_sufficient_resolution_evidence_with_verification():
    """EvidenceState with discrepancy_verification immediately triggers deterministic proof resolution."""
    state = EvidenceState("TXN_001")
    state.update("verify_discrepancy", {
        "transaction_id": "TXN_001",
        "discrepancy_fully_explained": True,
        "resolved_difference": 200.0,
        "explanation": "Bank credit exactly matches expected settlement minus adjustment of 200.",
    })
    proven, data = has_sufficient_resolution_evidence(state, "BANK_AMOUNT_MISMATCH")
    assert proven is True
    assert data["resolution_type"] == "ADJUSTMENT_EXPLAINED"
    assert data["resolved_difference"] == 200.0


def test_pruned_investigator_prompt_payload():
    """Pruned investigator prompt excludes irrelevant fields based on exception type."""
    prompt = build_investigator_prompt({
        "transaction_id": "TXN_TEST",
        "reason": "MISSING_LEDGER_RECORD",
        "payment_amount": 5000,
        "gross_amount": None,
        "fee": None,
        "expected_net_amount": None,
        "bank_amount": None,
        "difference": None,
    })
    assert "Payment Amount: ₹5,000" in prompt
    assert "Ledger Gross" not in prompt
    assert "Ledger Fee" not in prompt
    assert "Bank Credited" not in prompt


def test_pruned_verifier_prompt_payload():
    """Verifier prompt only includes structured proposal and cited evidence without raw record dump."""
    proposal = {
        "transaction_id": "TXN_999",
        "exception_type": "BANK_AMOUNT_MISMATCH",
        "proposed_resolution": "AUTO_RESOLVED",
        "confidence": 1.0,
        "reason": "Documented rebate matches bank credit gap.",
        "evidence": ["Rebate ADJ_01 = 150", "Bank credit = 9850 matches expected 10000 - 150"],
    }
    prompt = build_verifier_prompt(
        exception_record={"transaction_id": "TXN_999", "reason": "BANK_AMOUNT_MISMATCH"},
        source_evidence=["Payment = 10000", "Ledger = 10000"],
        deterministic_calculations={"expected": 10000},
        proposal=proposal,
    )
    assert "TXN_999" in prompt
    assert "Proposed Resolution: AUTO_RESOLVED" in prompt
    assert "Rebate ADJ_01 = 150" in prompt
    assert "## Deterministic Calculations" not in prompt


def test_investigator_passes_max_tokens():
    """Investigator passes max_tokens=300 to llm.chat()."""
    mock_llm = MagicMock(spec=LLMClient)
    mock_resp = MagicMock()
    mock_msg = MagicMock()
    mock_msg.tool_calls = None
    mock_msg.content = json.dumps({
        "transaction_id": "TXN_TEST",
        "exception_type": "GROSS_AMOUNT_MISMATCH",
        "proposed_resolution": "HUMAN_REVIEW",
        "confidence": 0.9,
        "reason": "Missing documentation.",
        "evidence": ["Gross mismatch detected."],
    })
    mock_resp.choices = [MagicMock(message=mock_msg)]
    mock_llm.chat.return_value = mock_resp

    toolkit = FinancialToolkit(payments=[], ledger_records=[], bank_records=[], adjustments=[])
    investigator = InvestigatorAgent(toolkit=toolkit, llm_client=mock_llm)
    investigator.investigate({"transaction_id": "TXN_TEST", "reason": "GROSS_AMOUNT_MISMATCH"})

    assert mock_llm.chat.called
    kwargs = mock_llm.chat.call_args[1]
    assert kwargs.get("max_tokens") == 300


def test_verifier_passes_max_tokens():
    """Verifier passes max_tokens=250 to llm.chat()."""
    mock_llm = MagicMock(spec=LLMClient)
    mock_resp = MagicMock()
    mock_msg = MagicMock()
    mock_msg.content = json.dumps({
        "transaction_id": "TXN_TEST",
        "verified": True,
        "decision": "AUTO_RESOLVED",
        "confidence": 1.0,
        "reason": "Evidence verified.",
        "evidence_references": ["Ref 1"],
        "contradictions": [],
    })
    mock_resp.choices = [MagicMock(message=mock_msg)]
    mock_llm.chat.return_value = mock_resp

    verifier = VerifierAgent(llm_client=mock_llm)
    proposal = InvestigationProposal(
        transaction_id="TXN_TEST",
        exception_type="BANK_AMOUNT_MISMATCH",
        proposed_resolution="AUTO_RESOLVED",
        confidence=1.0,
        reason="Adjustment matched.",
        evidence=["Ref 1"],
    )
    verifier.verify(
        exception_record={"transaction_id": "TXN_TEST", "reason": "BANK_AMOUNT_MISMATCH"},
        source_evidence=["Ref 1"],
        evidence_state=MagicMock(),
        proposal=proposal,
    )

    assert mock_llm.chat.called
    kwargs = mock_llm.chat.call_args[1]
    assert kwargs.get("max_tokens") == 250
