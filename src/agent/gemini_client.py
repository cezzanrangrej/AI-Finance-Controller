"""
Google Gemini API client implementation using the modern `google-genai` SDK.
"""

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

from google import genai
from google.genai import types

from src.agent.rate_limit import LLMRateLimitError, extract_retry_after
from src.config import DEFAULT_GEMINI_MODEL

logger = logging.getLogger(__name__)

MAX_RETRIES = 5
INITIAL_RETRY_DELAY = 2.0


class GeminiLLMClient:
    """
    Client for interacting with Google's Gemini models via google-genai SDK.
    Supports multi-turn function calling, structured decisions, and token usage tracking.
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None) -> None:
        import sys
        if not api_key and "pytest" not in sys.modules:
            try:
                from dotenv import load_dotenv
                load_dotenv(override=True)
            except Exception:
                pass
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY environment variable is missing. "
                "Set GEMINI_API_KEY or configure LLM_PROVIDER=demo for Demo Mode."
            )

        self.model = model or os.getenv("GEMINI_MODEL") or os.getenv("MODEL_NAME") or DEFAULT_GEMINI_MODEL
        self.provider = "gemini"
        self.mode = "REAL_LLM"
        self.demo_mode = False

        self._client = genai.Client(api_key=self.api_key)

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
    ) -> Any:
        """
        Sends a chat completion request to Gemini with tools and multi-turn message history.
        Returns a response object compatible with the AgentController interface.
        """
        system_instruction = None
        gemini_contents = []

        # Convert tool definitions to Gemini types.Tool
        gemini_tools = None
        if tools:
            func_decls = []
            for t in tools:
                if t.get("type") == "function":
                    func_info = t["function"]
                    func_decls.append(
                        types.FunctionDeclaration(
                            name=func_info["name"],
                            description=func_info.get("description", ""),
                            parameters=func_info.get("parameters"),
                        )
                    )
            if func_decls:
                gemini_tools = [types.Tool(function_declarations=func_decls)]

        # Process message history
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content")

            if role == "system":
                system_instruction = content
            elif role == "user":
                if content:
                    gemini_contents.append(
                        types.Content(role="user", parts=[types.Part.from_text(text=content)])
                    )
            elif role == "assistant":
                if msg.get("raw_content"):
                    gemini_contents.append(msg["raw_content"])
                else:
                    parts = []
                    if content:
                        parts.append(types.Part.from_text(text=content))
                    if msg.get("tool_calls"):
                        for tc in msg["tool_calls"]:
                            fn = tc.get("function", {})
                            fn_name = fn.get("name", "")
                            fn_args_raw = fn.get("arguments", "{}")
                            thought_sig = tc.get("thought_signature")
                            try:
                                fn_args = json.loads(fn_args_raw) if isinstance(fn_args_raw, str) else fn_args_raw
                            except Exception:
                                fn_args = {}
                            if thought_sig:
                                parts.append(types.Part(function_call=types.FunctionCall(name=fn_name, args=fn_args), thought_signature=thought_sig))
                            else:
                                parts.append(types.Part.from_function_call(name=fn_name, args=fn_args))
                    if parts:
                        gemini_contents.append(types.Content(role="model", parts=parts))

            elif role == "tool":
                tool_id = msg.get("tool_call_id", "")
                tool_name = "tool_response"
                for prev in reversed(messages):
                    if prev.get("role") == "assistant" and prev.get("tool_calls"):
                        for tc in prev["tool_calls"]:
                            if tc.get("id") == tool_id:
                                tool_name = tc.get("function", {}).get("name", tool_name)
                                break

                try:
                    resp_dict = json.loads(content) if isinstance(content, str) else content
                except Exception:
                    resp_dict = {"response": content}

                if not isinstance(resp_dict, dict):
                    resp_dict = {"result": resp_dict}

                gemini_contents.append(
                    types.Content(
                        role="user",
                        parts=[types.Part.from_function_response(name=tool_name, response=resp_dict)],
                    )
                )

        config_kwargs: Dict[str, Any] = {
            "system_instruction": system_instruction,
            "tools": gemini_tools,
            "temperature": 0.1,
            # Always disabled, tools declared or not. This client is a transport:
            # every tool call is dispatched by the caller's own loop
            # (AgentController / InvestigatorAgent), which is what records the
            # audit trail and enforces MAX_TOOL_CALLS. Letting the SDK execute
            # functions itself would bypass both.
            #
            # It has to be set even on tool-free calls (the Verifier, the batch
            # controllers). Left unset, google-genai treats AFC as enabled,
            # routes the request through its own remote-call loop and logs
            # "Direct use of automatic function calling (AFC) in
            # Models.generate_content is not recommended" on the first such call.
            "automatic_function_calling": types.AutomaticFunctionCallingConfig(disable=True),
        }
        if max_tokens is not None:
            config_kwargs["max_output_tokens"] = max_tokens

        config = types.GenerateContentConfig(**config_kwargs)

        response = None
        last_exception = None

        for attempt in range(MAX_RETRIES):
            try:
                response = self._client.models.generate_content(
                    model=self.model,
                    contents=gemini_contents,
                    config=config,
                )
                break
            except Exception as e:
                last_exception = e
                err_str = str(e)
                is_rate_limit = "429" in err_str or "RESOURCE_EXHAUSTED" in err_str
                logger.warning(f"Gemini API attempt {attempt + 1} failed (rate_limit={is_rate_limit}): {err_str}")

                if is_rate_limit:
                    # Surface immediately so the outer parallel retry layer
                    # can back off with jitter without blocking sibling threads.
                    retry_after = extract_retry_after(err_str)
                    raise LLMRateLimitError(
                        f"Gemini rate limit on attempt {attempt + 1}: {err_str}",
                        retry_after=retry_after,
                        provider="gemini",
                        status_code=429,
                        attempt=attempt + 1,
                    ) from e

                if attempt < MAX_RETRIES - 1:
                    sleep_time = INITIAL_RETRY_DELAY * (2**attempt)
                    time.sleep(sleep_time)
                else:
                    raise RuntimeError(f"Gemini API request failed after {MAX_RETRIES} attempts: {err_str}") from e

        # Extract usage metadata if present
        if response and hasattr(response, "usage_metadata") and response.usage_metadata:
            um = response.usage_metadata
            self.last_prompt_tokens = getattr(um, "prompt_token_count", None)
            self.last_completion_tokens = getattr(um, "candidates_token_count", None) or getattr(um, "response_token_count", None)
            self.last_total_tokens = getattr(um, "total_token_count", None)

            if self.last_prompt_tokens is not None:
                self.cumulative_prompt_tokens += self.last_prompt_tokens
            if self.last_completion_tokens is not None:
                self.cumulative_completion_tokens += self.last_completion_tokens
            if self.last_total_tokens is not None:
                self.cumulative_total_tokens += self.last_total_tokens

        return self._format_response(response)

    def _format_response(self, gemini_response: Any) -> Any:
        """Adapts Gemini response object to OpenAI-style response format expected by AgentController."""
        text_content = ""
        tool_calls = []

        candidate = None
        if gemini_response and hasattr(gemini_response, "candidates") and gemini_response.candidates:
            candidate = gemini_response.candidates[0]
            if candidate.content and candidate.content.parts:
                for idx, part in enumerate(candidate.content.parts):
                    if part.text:
                        text_content += part.text
                    if part.function_call:
                        fc = part.function_call
                        tc_id = f"call_gemini_{idx}_{int(time.time()*1000)}"
                        thought_sig = getattr(part, "thought_signature", None)
                        if isinstance(fc.args, dict):
                            args_str = json.dumps(fc.args)
                        elif hasattr(fc.args, "__iter__") and not isinstance(fc.args, (str, bytes)):
                            try:
                                args_str = json.dumps(dict(fc.args))
                            except Exception:
                                args_str = str(fc.args)
                        else:
                            args_str = str(fc.args) if fc.args else "{}"

                        class GeminiFunction:
                            def __init__(self, name: str, arguments: str):
                                self.name = name
                                self.arguments = arguments

                        class GeminiToolCall:
                            def __init__(self, tc_id: str, fn_name: str, fn_args: str, thought_sig: Optional[bytes] = None):
                                self.id = tc_id
                                self.type = "function"
                                self.function = GeminiFunction(fn_name, fn_args)
                                self.thought_signature = thought_sig

                        tool_calls.append(GeminiToolCall(tc_id, fc.name, args_str, thought_sig))

        class GeminiMessage:
            def __init__(self, content: Optional[str], tool_calls_list: Optional[List[Any]], raw_content: Optional[Any] = None):
                self.content = content if content else None
                self.tool_calls = tool_calls_list if tool_calls_list else None
                self.raw_content = raw_content

        class GeminiChoice:
            def __init__(self, message: GeminiMessage):
                self.message = message

        class FormattedResponse:
            def __init__(self, choice: GeminiChoice):
                self.choices = [choice]

        raw_content = candidate.content if candidate else None
        return FormattedResponse(GeminiChoice(GeminiMessage(text_content, tool_calls, raw_content)))
