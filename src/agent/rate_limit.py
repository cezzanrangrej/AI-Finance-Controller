"""
Rate limit exception for LLM provider API calls.

Raised by LLM transport clients (Gemini, OpenRouter, Grok) when the upstream
provider returns HTTP 429, RESOURCE_EXHAUSTED, or an equivalent rate-limit
signal.  The outer retry layer in runs.py catches this to apply jittered
exponential backoff *without blocking the asyncio event loop or sibling
threads*, which the old synchronous time.sleep() inside each client did.
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class LLMRateLimitError(Exception):
    """
    Raised when an upstream LLM provider returns a rate-limit response.

    Attributes:
        retry_after:  Seconds the provider asked us to wait (from Retry-After
                      header or error body), or None if not specified.
        provider:     Short label for the provider that throttled the request
                      (e.g. "gemini", "openrouter", "grok").
        status_code:  The HTTP status code, typically 429.
        attempt:      Which internal client attempt triggered this (1-based).
    """

    def __init__(
        self,
        message: str,
        *,
        retry_after: Optional[float] = None,
        provider: str = "",
        status_code: int = 429,
        attempt: int = 1,
    ) -> None:
        super().__init__(message)
        self.retry_after = retry_after
        self.provider = provider
        self.status_code = status_code
        self.attempt = attempt


def extract_retry_after(error_text: str) -> Optional[float]:
    """
    Best-effort extraction of a retry delay from an error message or header.

    Checks for patterns like:
    - ``retry in 25s``
    - ``retry after 30 seconds``
    - ``Retry-After: 60``
    """
    patterns = [
        r"retry[\s_-]*(?:in|after)\s*[:\s]*(\d+(?:\.\d+)?)\s*s",
        r"Retry-After:\s*(\d+(?:\.\d+)?)",
    ]
    for pat in patterns:
        match = re.search(pat, error_text, re.IGNORECASE)
        if match:
            return float(match.group(1))
    return None
