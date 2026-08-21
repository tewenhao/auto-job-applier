"""A thin wrapper over the Anthropic SDK.

Centralizes client construction and per-task model selection so call sites ask
for a *task* (``Task.INTERVIEW`` / ``Task.PARSE``) rather than hardcoding model
ids. Exposes ``.raw`` for advanced use (streaming, tool use) in later modules.
"""

from __future__ import annotations

from typing import Any

import anthropic

from app.config import Settings, Task, get_settings

# Default kept under the SDK's non-streaming HTTP timeout; callers can override.
DEFAULT_MAX_TOKENS = 16000


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

        response = self._client.messages.create(**params)
        return "".join(block.text for block in response.content if block.type == "text")
