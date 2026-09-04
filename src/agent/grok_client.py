"""
xAI Grok API client implementation using OpenAI-compatible HTTP interface via httpx.
"""

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

import httpx

from src.agent.rate_limit import LLMRateLimitError

logger = logging.getLogger(__name__)

DEFAULT_GROK_BASE_URL = "https://api.x.ai/v1"
DEFAULT_GROK_MODEL = "grok-2-latest"
MAX_RETRIES = 3
INITIAL_RETRY_DELAY = 2.0
REQUEST_TIMEOUT_SEC = 60.0


class GrokFunction:
    def __init__(self, name: str, arguments: str) -> None:
        self.name = name
        self.arguments = arguments


class GrokToolCall:
    def __init__(self, tc_id: str, name: str, arguments: str) -> None:
        self.id = tc_id
        self.type = "function"
        self.function = GrokFunction(name, arguments)


class GrokMessage:
    def __init__(
        self,
        content: Optional[str] = None,
        tool_calls: Optional[List[GrokToolCall]] = None,
        raw_content: Optional[Any] = None,
    ) -> None:
        self.content = content
        self.tool_calls = tool_calls
        self.raw_content = raw_content


class GrokChoice:
    def __init__(self, message: GrokMessage) -> None:
        self.message = message


class GrokUsage:
    def __init__(self, prompt_tokens: int, completion_tokens: int, total_tokens: int) -> None:
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens


class GrokResponse:
    def __init__(
        self,
        choices: List[GrokChoice],
        usage: Optional[GrokUsage] = None,
    ) -> None:
        self.choices = choices
        self.usage = usage


class GrokLLMClient:
    """
    Client for interacting with xAI Grok models via OpenAI-compatible HTTP endpoints.
    Supports multi-turn function/tool calling, structured decisions, and token usage tracking.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> None:
        self.api_key = (api_key or os.getenv("INVESTIGATOR_API_KEY") or os.getenv("GROK_API_KEY") or os.getenv("XAI_API_KEY") or "").strip()
        if not self.api_key:
            raise ValueError(
                "INVESTIGATOR_API_KEY / GROK_API_KEY / XAI_API_KEY environment variable is missing. "
                "Set INVESTIGATOR_API_KEY or configure provider=demo for Demo Mode."
            )

        self.model = (model or os.getenv("INVESTIGATOR_MODEL") or os.getenv("GROK_MODEL") or os.getenv("XAI_MODEL") or DEFAULT_GROK_MODEL).strip()
        if not self.model:
            raise ValueError(
                "INVESTIGATOR_MODEL / GROK_MODEL environment variable is missing."
            )

        self.provider_name = "grok"
        self.mode = "REAL_LLM"
        self.demo_mode = False

        self.base_url = (
            base_url
            or os.getenv("GROK_BASE_URL", "").strip()
            or os.getenv("XAI_BASE_URL", "").strip()
            or DEFAULT_GROK_BASE_URL
        ).rstrip("/")

        # Track usage metrics across calls
        self.last_prompt_tokens: Optional[int] = None
        self.last_completion_tokens: Optional[int] = None
        self.last_total_tokens: Optional[int] = None
        self.cumulative_prompt_tokens: int = 0
        self.cumulative_completion_tokens: int = 0
        self.cumulative_total_tokens: int = 0

    def reset_cumulative_tokens(self) -> None:
        """Resets cumulative token counters."""
        self.cumulative_prompt_tokens = 0
        self.cumulative_completion_tokens = 0
        self.cumulative_total_tokens = 0

    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: str = "auto",
        max_tokens: Optional[int] = None,
    ) -> GrokResponse:
        """
        Sends a chat completion request to xAI Grok with retries and tool calling support.
        """
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.0,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice

        delay = INITIAL_RETRY_DELAY
        last_exception: Optional[Exception] = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                with httpx.Client(timeout=REQUEST_TIMEOUT_SEC) as client:
                    resp = client.post(url, headers=headers, json=payload)

                if resp.status_code == 429:
                    err_text = resp.text[:300]
                    retry_after = None
                    ra_header = resp.headers.get("Retry-After") or resp.headers.get("retry-after")
                    if ra_header:
                        try:
                            retry_after = float(ra_header)
                        except (ValueError, TypeError):
                            pass
                    raise LLMRateLimitError(
                        f"Grok rate limit (429): {err_text}",
                        retry_after=retry_after,
                        provider="grok",
                        status_code=429,
                        attempt=attempt,
                    )

                if resp.status_code >= 500:
                    logger.warning(
                        f"Grok API returned HTTP {resp.status_code} (attempt {attempt}/{MAX_RETRIES}). Retrying in {delay}s..."
                    )
                    time.sleep(delay)
                    delay *= 2.0
                    continue

                if resp.status_code != 200:
                    error_detail = resp.text[:300]
                    raise RuntimeError(f"Grok API error HTTP {resp.status_code}: {error_detail}")

                data = resp.json()
                choices_raw = data.get("choices", [])
                if not choices_raw:
                    raise RuntimeError("Grok API response contained no choices.")

                choice_data = choices_raw[0]
                msg_data = choice_data.get("message", {})
                content = msg_data.get("content")

                tool_calls = None
                raw_tcs = msg_data.get("tool_calls")
                if raw_tcs:
                    tool_calls = []
                    for tc in raw_tcs:
                        tc_id = tc.get("id", f"call_{len(tool_calls)}")
                        fn = tc.get("function", {})
                        fn_name = fn.get("name", "")
                        fn_args = fn.get("arguments", "{}")
                        if isinstance(fn_args, dict):
                            fn_args = json.dumps(fn_args)
                        tool_calls.append(GrokToolCall(tc_id, fn_name, fn_args))

                message_obj = GrokMessage(content=content, tool_calls=tool_calls, raw_content=msg_data)
                choice_obj = GrokChoice(message=message_obj)

                # Parse token usage if returned by endpoint
                usage_obj = None
                usage_raw = data.get("usage")
                if usage_raw:
                    p_tok = usage_raw.get("prompt_tokens", 0)
                    c_tok = usage_raw.get("completion_tokens", 0)
                    t_tok = usage_raw.get("total_tokens", p_tok + c_tok)

                    self.last_prompt_tokens = p_tok
                    self.last_completion_tokens = c_tok
                    self.last_total_tokens = t_tok

                    self.cumulative_prompt_tokens += p_tok
                    self.cumulative_completion_tokens += c_tok
                    self.cumulative_total_tokens += t_tok

                    usage_obj = GrokUsage(p_tok, c_tok, t_tok)

                return GrokResponse(choices=[choice_obj], usage=usage_obj)

            except (httpx.RequestError, RuntimeError) as e:
                last_exception = e
                logger.warning(
                    f"Grok API request attempt {attempt}/{MAX_RETRIES} failed: {e}. Retrying in {delay}s..."
                )
                if attempt < MAX_RETRIES:
                    time.sleep(delay)
                    delay *= 2.0

        raise RuntimeError(f"Grok API failed after {MAX_RETRIES} attempts. Last error: {last_exception}")
