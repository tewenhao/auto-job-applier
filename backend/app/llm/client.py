"""A thin wrapper over the Anthropic SDK.

Centralizes client construction and per-task model selection so call sites ask
for a *task* (``Task.INTERVIEW`` / ``Task.PARSE``) rather than hardcoding model
ids. Exposes ``.raw`` for advanced use (streaming, tool use) in later modules.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, TypeVar

import anthropic
import pydantic
from pydantic import BaseModel

from app.config import Settings, Task, get_settings

# Default kept under the SDK's non-streaming HTTP timeout; callers can override.
DEFAULT_MAX_TOKENS = 16000

# The API occasionally returns a generic 400 "Invalid request data" for a
# request that is well-formed — a byte-identical retry succeeds. The SDK retries
# 429s and 5xx but never 4xx, so one flake would surface as a hard failure.
# Only this exact signature is retried: a real malformed request (an unsupported
# parameter, a bad message sequence) names what is wrong and must surface at once.
_TRANSIENT_BAD_REQUEST = "invalid request data"
_TRANSIENT_RETRIES = 3


def _is_transient(exc: anthropic.BadRequestError) -> bool:
    return _TRANSIENT_BAD_REQUEST in str(exc).lower()


T = TypeVar("T", bound=BaseModel)


class LLMClient:
    """Per-task access to Claude."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client = anthropic.Anthropic(api_key=self.settings.anthropic_api_key)

    @property
    def raw(self) -> anthropic.Anthropic:
        """The underlying Anthropic client, for streaming / tools / beta features."""
        return self._client

    def complete(
        self,
        *,
        task: Task,
        messages: list[dict[str, Any]],
        system: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        **kwargs: Any,
    ) -> str:
        """Send a message for ``task`` and return the response's concatenated text.

        Extra keyword args pass straight through to ``messages.create`` (e.g.
        ``thinking``, ``output_config``, ``temperature``) for callers that need
        them. Non-text content blocks (thinking, tool use) are ignored here —
        reach for ``.raw`` when you need them.
        """
        params: dict[str, Any] = {
            "model": self.settings.model_for(task),
            "max_tokens": max_tokens,
            "messages": messages,
            **kwargs,
        }
        if system is not None:
            params["system"] = system

        response = self._retrying(lambda: self._client.messages.create(**params))
        return "".join(block.text for block in response.content if block.type == "text")

    def _retrying(self, call: Callable[[], Any]) -> Any:
        """Run ``call``, retrying the API's transient generic 400."""
        for attempt in range(_TRANSIENT_RETRIES):
            try:
                return call()
            except anthropic.BadRequestError as exc:
                if not _is_transient(exc) or attempt == _TRANSIENT_RETRIES - 1:
                    raise
                time.sleep(0.5 * (attempt + 1))
        raise AssertionError("unreachable")

    def parse(
        self,
        *,
        task: Task,
        messages: list[dict[str, Any]],
        output_format: type[T],
        system: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        **kwargs: Any,
    ) -> T:
        """Structured extraction: return a validated instance of ``output_format``.

        Uses the SDK's ``messages.parse`` with a Pydantic schema so the model's
        output is constrained and validated. The task's model applies (usually
        ``Task.PARSE`` for cheap bulk extraction).
        """
        params: dict[str, Any] = {
            "model": self.settings.model_for(task),
            "max_tokens": max_tokens,
            "messages": messages,
            "output_format": output_format,
            **kwargs,
        }
        if system is not None:
            params["system"] = system

        try:
            response = self._retrying(lambda: self._client.messages.parse(**params))
        except pydantic.ValidationError as exc:
            # A truncated response (model hit max_tokens, thinking included)
            # surfaces as invalid/incomplete JSON. Turn the cryptic parser error
            # into an actionable one rather than a 500 with a raw stack trace.
            if any(e.get("type") == "json_invalid" for e in exc.errors()):
                raise ValueError(
                    f"The model's structured output was cut off before it was "
                    f"valid JSON — it likely hit the {max_tokens}-token ceiling "
                    f"(thinking counts against it). Try again, or raise max_tokens."
                ) from exc
            raise
        parsed = response.parsed_output
        if parsed is None:
            raise ValueError("Structured extraction returned no parsed output.")
        return parsed

    def research(
        self,
        *,
        task: Task,
        messages: list[dict[str, Any]],
        system: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        max_searches: int = 5,
    ) -> str:
        """Answer with the web-search server tool enabled, returning the text.

        Claude runs searches server-side. Handles ``pause_turn`` by resuming a
        few times. Used for company research.
        """
        tools = [
            {"type": "web_search_20260209", "name": "web_search", "max_uses": max_searches}
        ]
        base: dict[str, Any] = {
            "model": self.settings.model_for(task),
            "max_tokens": max_tokens,
            "tools": tools,
        }
        if system is not None:
            base["system"] = system

        convo: list[Any] = list(messages)
        response = None
        for _ in range(4):
            response = self._client.messages.create(messages=convo, **base)
            if response.stop_reason != "pause_turn":
                break
            convo = convo + [{"role": "assistant", "content": response.content}]

        if response is None:
            return ""
        return "".join(block.text for block in response.content if block.type == "text")
