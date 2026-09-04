"""
Unit tests for robust JSON parsing utilities in src/agent/json_utils.py.
"""

import json
import pytest

from src.agent.json_utils import clean_json_string, repair_and_parse_json, sanitize_json_syntax


def test_standard_json():
    raw = '{"status": "ok", "count": 42}'
    parsed = repair_and_parse_json(raw)
    assert parsed == {"status": "ok", "count": 42}


def test_markdown_code_fences_with_surrounding_text():
    raw = """
Here is your requested output:
```json
{
  "proposals": [
    {"transaction_id": "T001", "decision": "AUTO_RESOLVED"}
  ]
}
```
Hope this helps!
"""
    parsed = repair_and_parse_json(raw)
    assert "proposals" in parsed
    assert parsed["proposals"][0]["transaction_id"] == "T001"


def test_strip_thinking_tags():
    raw = """
<think>
We have 2 transactions here. Let's see: T001 matches adjustments.
So decision is AUTO_RESOLVED.
</think>
```json
{
  "decisions": [
    {"transaction_id": "T001", "verified": true}
  ]
}
```
"""
    parsed = repair_and_parse_json(raw)
    assert parsed["decisions"][0]["transaction_id"] == "T001"
    assert parsed["decisions"][0]["verified"] is True


def test_python_booleans_and_none():
    raw = """
{
  "transaction_id": "T002",
  "verified": True,
  "flagged": False,
  "resolved_difference": None,
  "evidence_flags": [True, False, None]
}
"""
    parsed = repair_and_parse_json(raw)
    assert parsed["verified"] is True
    assert parsed["flagged"] is False
    assert parsed["resolved_difference"] is None
    assert parsed["evidence_flags"] == [True, False, None]


def test_trailing_commas():
    raw = """
{
  "verifications": [
    {
      "transaction_id": "T003",
      "evidence": ["e1", "e2", ],
    },
  ],
}
"""
    parsed = repair_and_parse_json(raw)
    assert len(parsed["verifications"]) == 1
    assert parsed["verifications"][0]["evidence"] == ["e1", "e2"]


def test_single_quoted_python_dict():
    raw = """
{'transaction_id': 'T004', 'decision': 'HUMAN_REVIEW', 'confidence': 0.95}
"""
    parsed = repair_and_parse_json(raw)
    assert parsed["transaction_id"] == "T004"
    assert parsed["decision"] == "HUMAN_REVIEW"
    assert parsed["confidence"] == 0.95


def test_truncated_json_salvage():
    # Simulates finish_reason=length cutting off midway through the 2nd item
    raw = """{
  "verifications": [
    {
      "transaction_id": "TEST_001",
      "verified": true,
      "decision": "AUTO_RESOLVED"
    },
    {
      "transaction_id": "TEST_002",
      "verified": false,
      "decision": "HUMAN_RE
"""
    parsed = repair_and_parse_json(raw)
    assert "verifications" in parsed
    assert len(parsed["verifications"]) == 1
    assert parsed["verifications"][0]["transaction_id"] == "TEST_001"


def test_user_reported_truncation_snippet():
    raw = """{
  "verifications": [
    {
      "transaction_id": "TEST5_013",
      "verified": true,
      "decision": "AUTO_RESOLVED",
      "evidence_references": [
        "Adjustments documented",
        "Unaccounted variance of ₹0.50"
      ],
      "contradictions": []
    },
    {
      "transaction_id": "[TEST5_014]",
      "verified": true,
      "decision": "HUMAN_RE
"""
    parsed = repair_and_parse_json(raw)
    assert "verifications" in parsed
    assert len(parsed["verifications"]) == 1
    assert parsed["verifications"][0]["transaction_id"] == "TEST5_013"
