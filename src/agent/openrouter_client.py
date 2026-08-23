"""
OpenRouter API client implementation using OpenAI-compatible HTTP interface via httpx.
"""

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_REFERER = "https://github.com/cezzanrangrej/AI-Finance-Controller"
DEFAULT_TITLE = "AI Finance Controller"
MAX_RETRIES = 3
INITIAL_RETRY_DELAY = 2.0
REQUEST_TIMEOUT_SEC = 60.0


class OpenRouterFunction:
    def __init__(self, name: str, arguments: str) -> None:
        self.name = name
        self.arguments = arguments


class OpenRouterToolCall:
    def __init__(self, tc_id: str, name: str, arguments: str) -> None:
        self.id = tc_id
        self.type = "function"
        self.function = OpenRouterFunction(name, arguments)


class OpenRouterMessage:
    def __init__(
        self,
        content: Optional[str] = None,
        tool_calls: Optional[List[OpenRouterToolCall]] = None,
        raw_content: Optional[Any] = None,
    ) -> None:
        self.content = content
        self.tool_calls = tool_calls
        self.raw_content = raw_content


class OpenRouterChoice:
    def __init__(self, message: OpenRouterMessage) -> None:
        self.message = message


class OpenRouterUsage:
    def __init__(self, prompt_tokens: int, completion_tokens: int, total_tokens: int) -> None:
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens


class OpenRouterResponse:
    def __init__(
        self,
        choices: List[OpenRouterChoice],
        usage: Optional[OpenRouterUsage] = None,
    ) -> None:
        self.choices = choices
        self.usage = usage


class OpenRouterLLMClient:
    """
    Client for interacting with OpenRouter models via OpenAI-compatible HTTP endpoints.
    Supports multi-turn function/tool calling, structured decisions, and token usage tracking.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY", "").strip()
        if not self.api_key:
            raise ValueError(
                "OPENROUTER_API_KEY environment variable is missing. "
                "Set OPENROUTER_API_KEY or configure LLM_PROVIDER=demo for Demo Mode."
            )

        self.model = (model or os.getenv("OPENROUTER_MODEL", "")).strip()
        if not self.model:
            raise ValueError(
                "OPENROUTER_MODEL environment variable is missing. "
                "Set OPENROUTER_MODEL (e.g. OPENROUTER_MODEL=meta-llama/llama-3.3-70b-instruct) or configure LLM_PROVIDER=demo for Demo Mode."
            )

        self.base_url = (
            base_url
            or os.getenv("OPENROUTER_BASE_URL", "").strip()
            or DEFAULT_OPENROUTER_BASE_URL
        ).rstrip("/")

        self.referer = os.getenv("OPENROUTER_HTTP_REFERER", DEFAULT_REFERER)
        self.title = os.getenv("OPENROUTER_TITLE", DEFAULT_TITLE)

        self.provider = "openrouter"
        self.mode = "REAL_LLM"
        self.demo_mode = False

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
    ) -> OpenRouterResponse:
        """
        Sends a chat completion request to OpenRouter with tools and multi-turn message history.
        Returns a response object compatible with the AgentController interface.
        """
        formatted_messages = self._format_messages(messages)
        endpoint = f"{self.base_url}/chat/completions"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": self.referer,
            "X-Title": self.title,
            "Content-Type": "application/json",
        }

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": formatted_messages,
            "temperature": 0.1,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice

        last_exception = None
        data = None

        with httpx.Client(timeout=REQUEST_TIMEOUT_SEC) as client:
            for attempt in range(MAX_RETRIES):
                try:
                    response = client.post(endpoint, headers=headers, json=payload)
                    status_code = response.status_code

                    # Check for non-transient HTTP errors
                    if status_code in (400, 401, 403, 404):
                        err_text = response.text[:300]
                        raise RuntimeError(f"OpenRouter API error ({status_code}): {err_text}")

                    # Check for transient rate limit or server errors
                    if status_code == 429 or status_code >= 500:
                        err_text = response.text[:300]
                        if attempt == MAX_RETRIES - 1:
                            raise RuntimeError(f"OpenRouter API error ({status_code}) after {MAX_RETRIES} attempts: {err_text}")
                        sleep_time = INITIAL_RETRY_DELAY * (2**attempt)
                        if status_code == 429:
                            sleep_time = max(sleep_time, 5.0)
                            print(f"[Rate Limit] Pausing {sleep_time:.1f}s for OpenRouter quota window...", flush=True)
                        time.sleep(sleep_time)
                        continue

                    response.raise_for_status()
                    data = response.json()
                    break

                except (httpx.TimeoutException, httpx.NetworkError) as e:
                    last_exception = e
                    if attempt == MAX_RETRIES - 1:
                        raise RuntimeError(f"OpenRouter network error after {MAX_RETRIES} attempts: {str(e)}") from e
                    sleep_time = INITIAL_RETRY_DELAY * (2**attempt)
                    time.sleep(sleep_time)

                except Exception as e:
                    last_exception = e
                    err_str = str(e).lower()
                    if any(c in err_str for c in ["401", "403", "400", "404", "unauthorized", "invalid api key"]):
                        raise
                    if attempt == MAX_RETRIES - 1:
                        raise RuntimeError(f"OpenRouter API request failed after {MAX_RETRIES} attempts: {str(e)}") from e
                    sleep_time = INITIAL_RETRY_DELAY * (2**attempt)
                    time.sleep(sleep_time)

        if not data:
            raise RuntimeError(f"OpenRouter request returned empty response: {last_exception}")

        return self._parse_api_response(data)

    def _parse_api_response(self, data: Dict[str, Any]) -> OpenRouterResponse:
        """Parses OpenRouter JSON response into OpenRouterResponse object."""
        choices_list = []
        for choice_dict in data.get("choices", []):
            msg_dict = choice_dict.get("message", {})
            content = msg_dict.get("content")

            tool_calls_list = []
            for tc in msg_dict.get("tool_calls", []) or []:
                tc_id = tc.get("id", f"call_or_{int(time.time()*1000)}")
                fn_dict = tc.get("function", {})
                fn_name = fn_dict.get("name", "")
                fn_args = fn_dict.get("arguments", "{}")
                if isinstance(fn_args, dict):
                    fn_args = json.dumps(fn_args)
                tool_calls_list.append(OpenRouterToolCall(tc_id, fn_name, fn_args))

            msg_obj = OpenRouterMessage(
                content=content,
                tool_calls=tool_calls_list if tool_calls_list else None,
            )
            choices_list.append(OpenRouterChoice(msg_obj))

        usage_dict = data.get("usage", {})
        usage_obj = None
        if usage_dict:
            p_tok = usage_dict.get("prompt_tokens", 0)
            c_tok = usage_dict.get("completion_tokens", 0)
            t_tok = usage_dict.get("total_tokens", p_tok + c_tok)
            usage_obj = OpenRouterUsage(p_tok, c_tok, t_tok)

            self.last_prompt_tokens = p_tok
            self.last_completion_tokens = c_tok
            self.last_total_tokens = t_tok

            if p_tok:
                self.cumulative_prompt_tokens += p_tok
            if c_tok:
                self.cumulative_completion_tokens += c_tok
            if t_tok:
                self.cumulative_total_tokens += t_tok

        return OpenRouterResponse(choices=choices_list, usage=usage_obj)

    def _format_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Formats internal message history into standard OpenAI chat messages."""
        formatted = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content")

            if role in ("system", "user"):
                formatted.append({"role": role, "content": content or ""})
            elif role == "assistant":
                item: Dict[str, Any] = {"role": "assistant", "content": content}
                tool_calls = msg.get("tool_calls")
                if tool_calls:
                    item["tool_calls"] = [
                        {
                            "id": tc.get("id"),
                            "type": "function",
                            "function": {
                                "name": tc.get("function", {}).get("name"),
                                "arguments": tc.get("function", {}).get("arguments")
                                if isinstance(tc.get("function", {}).get("arguments"), str)
                                else json.dumps(tc.get("function", {}).get("arguments")),
                            },
                        }
                        for tc in tool_calls
                    ]
                formatted.append(item)
            elif role == "tool":
                formatted.append({
                    "role": "tool",
                    "tool_call_id": msg.get("tool_call_id", ""),
                    "content": content or "",
                })

        return formatted

    def __repr__(self) -> str:
        return f"<OpenRouterLLMClient(model='{self.model}', base_url='{self.base_url}')>"

    def __str__(self) -> str:
        return f"OpenRouterLLMClient(model={self.model})"
