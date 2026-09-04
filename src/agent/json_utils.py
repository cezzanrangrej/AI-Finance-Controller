"""
Robust JSON parsing and sanitization utilities for LLM outputs.

Handles common LLM formatting anomalies:
- Internal reasoning tags (<think>, <thought>, <reasoning>)
- Markdown code fences with extraneous pre/post text
- Python-style literals (True, False, None) instead of JSON (true, false, null)
- Trailing commas before closing brackets or braces
- Single-quoted structures (via ast.literal_eval fallback)
- Truncated JSON recovery (closing unclosed arrays/objects to salvage complete items)
"""

import ast
import json
import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)


def clean_json_string(raw_content: str) -> str:
    """
    Cleans an LLM response string before JSON parsing.
    Strips reasoning blocks, markdown fences, and extracts outermost JSON structure.
    """
    if not raw_content:
        return ""

    cleaned = raw_content.strip()

    # 1. Strip reasoning blocks from reasoning models (Nemotron, DeepSeek, MiniMax)
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"<thought>.*?</thought>", "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"<reasoning>.*?</reasoning>", "", cleaned, flags=re.DOTALL)
    cleaned = cleaned.strip()

    # 2. Strip markdown code fences
    if "```" in cleaned:
        # Match ```json ... ``` or ``` ... ```
        fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, re.IGNORECASE)
        if fence_match:
            cleaned = fence_match.group(1).strip()
        else:
            # Code fence opened but perhaps wasn't closed before truncation
            open_match = re.search(r"```(?:json)?\s*([\s\S]*)", cleaned, re.IGNORECASE)
            if open_match:
                cleaned = open_match.group(1).strip()

    # 3. Extract outermost JSON object {...} or array [...]
    first_brace = cleaned.find("{")
    first_bracket = cleaned.find("[")

    if first_brace != -1 and (first_bracket == -1 or first_brace < first_bracket):
        last_brace = cleaned.rfind("}")
        if last_brace != -1 and last_brace > first_brace:
            cleaned = cleaned[first_brace : last_brace + 1]
        else:
            cleaned = cleaned[first_brace:]
    elif first_bracket != -1:
        last_bracket = cleaned.rfind("]")
        if last_bracket != -1 and last_bracket > first_bracket:
            cleaned = cleaned[first_bracket : last_bracket + 1]
        else:
            cleaned = cleaned[first_bracket:]

    return cleaned.strip()


def sanitize_json_syntax(text: str) -> str:
    """
    Applies regex sanitizers to repair common LLM syntax deviations:
    - Python literals (True, False, None) -> (true, false, null)
    - Trailing commas before } and ]
    - Single-line comments (// ...)
    """
    sanitized = text

    # Remove C-style line comments (// ...) outside strings
    sanitized = re.sub(r"(?m)^\s*//.*$", "", sanitized)
    sanitized = re.sub(r"(?m)\s*//[^\n\"]*$", "", sanitized)

    # Normalize Python literals after colons or in lists
    sanitized = re.sub(r":\s*True\b", ": true", sanitized)
    sanitized = re.sub(r":\s*False\b", ": false", sanitized)
    sanitized = re.sub(r":\s*None\b", ": null", sanitized)

    sanitized = re.sub(r"(\[|,)\s*True\b", r"\1 true", sanitized)
    sanitized = re.sub(r"(\[|,)\s*False\b", r"\1 false", sanitized)
    sanitized = re.sub(r"(\[|,)\s*None\b", r"\1 null", sanitized)

    # Remove trailing commas before closing braces/brackets: e.g. [1, 2, ] or {"a": 1, }
    sanitized = re.sub(r",\s*([\]\}])", r"\1", sanitized)

    return sanitized


def attempt_truncated_json_salvage(text: str) -> Optional[Any]:
    """
    Attempts to salvage complete array items from truncated JSON responses
    (e.g. when finish_reason=length cuts off an array of decisions or proposals).
    """
    # Find the last completed item ending with '}' in an array
    last_item_end = text.rfind("}")
    if last_item_end == -1:
        return None

    candidate = text[: last_item_end + 1].strip()

    # Determine unclosed brackets
    open_brackets = candidate.count("[") - candidate.count("]")
    open_braces = candidate.count("{") - candidate.count("}")

    # Remove any trailing comma from candidate before closing
    candidate = re.sub(r",\s*$", "", candidate)

    # Close brackets/braces in order
    closing = ("]" * max(0, open_brackets)) + ("}" * max(0, open_braces))
    candidate += closing

    try:
        return json.loads(candidate, strict=False)
    except Exception:
        # Also try sanitizing the candidate
        try:
            sanitized = sanitize_json_syntax(candidate)
            return json.loads(sanitized, strict=False)
        except Exception:
            return None


def repair_and_parse_json(raw_content: str) -> Any:
    """
    Parses JSON from an LLM response with multiple layers of recovery and sanitization.

    1. Fast path: Direct json.loads on cleaned string.
    2. Syntax sanitization: Fixes True/False/None and trailing commas.
    3. Python literal eval: Recovers single-quoted dicts/lists.
    4. Truncation salvage: Recovers fully formed items from truncated arrays.
    """
    if not raw_content or not raw_content.strip():
        raise ValueError("Empty content cannot be parsed as JSON")

    cleaned = clean_json_string(raw_content)

    # Attempt 1: Standard parse on cleaned string
    try:
        return json.loads(cleaned, strict=False)
    except json.JSONDecodeError as err1:
        last_error = err1

    # Attempt 2: Sanitize Python literals & trailing commas
    sanitized = sanitize_json_syntax(cleaned)
    try:
        return json.loads(sanitized, strict=False)
    except json.JSONDecodeError as err2:
        last_error = err2

    # Attempt 3: ast.literal_eval for single-quoted Python dictionaries
    try:
        parsed_ast = ast.literal_eval(cleaned)
        if isinstance(parsed_ast, (dict, list)):
            return parsed_ast
    except (ValueError, SyntaxError, MemoryError):
        pass

    # Attempt 4: Truncated JSON recovery
    salvaged = attempt_truncated_json_salvage(sanitized)
    if salvaged is not None:
        logger.warning(
            "Salvaged partially truncated JSON response containing keys: %s",
            list(salvaged.keys()) if isinstance(salvaged, dict) else "array",
        )
        return salvaged

    # Re-raise the most specific parse error
    raise last_error
