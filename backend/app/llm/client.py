"""A thin wrapper over the Anthropic SDK.

Centralizes client construction and per-task model selection so call sites ask
for a *task* (``Task.INTERVIEW`` / ``Task.PARSE``) rather than hardcoding model
ids. Exposes ``.raw`` for advanced use (streaming, tool use) in later modules.

It also owns prompt caching. Caching is a *prefix* match — the rendered prompt
is tools, then system, then messages, and a breakpoint caches everything before
it — so the only thing a call site has to get right is order: stable, expensive
context first, per-request content last. ``cache_system=True`` marks the system
prompt; :func:`cached_text` marks a block inside a message.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

import anthropic
import pydantic
from pydantic import BaseModel

from app.config import Settings, Task, get_settings

log = logging.getLogger(__name__)

# Default kept under the SDK's non-streaming HTTP timeout; callers can override.
DEFAULT_MAX_TOKENS = 16000

# 5-minute TTL. A read refreshes the timer for free, so back-to-back calls
# sharing a prefix keep the entry alive; the 1-hour TTL costs twice as much to
# write and would only pay off if we left gaps longer than five minutes between
# calls that share a prefix, which the generation pipeline doesn't.
_EPHEMERAL: dict[str, Any] = {"type": "ephemeral"}


def cached_text(text: str) -> dict[str, Any]:
    """A message text block marked as a cache breakpoint.

    Everything *before* the block — tools, system, and any earlier blocks — is
    cached along with it. Put the stable, expensive context (the candidate
    profile, the writing samples) in one of these and the per-request tail after
    it, or the cache is written on every request and never read.
    """
    return {"type": "text", "text": text, "cache_control": dict(_EPHEMERAL)}


@dataclass
class TokenUsage:
    """Running token totals for one client, so caching can be verified.

    Caching fails silently — requests still succeed, the bill is just higher —
    so the usage numbers are the only ground truth that it is working.
    """

    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0
    calls: int = 0

    def add(self, usage: Any) -> None:
        if usage is None:
            return
        self.calls += 1
        self.input += getattr(usage, "input_tokens", 0) or 0
        self.output += getattr(usage, "output_tokens", 0) or 0
        self.cache_read += getattr(usage, "cache_read_input_tokens", 0) or 0
        self.cache_write += getattr(usage, "cache_creation_input_tokens", 0) or 0

    def summary(self) -> str:
        """One line, for the CLI and the logs."""
        prompt = self.input + self.cache_read + self.cache_write
        hit = f"{100 * self.cache_read / prompt:.0f}%" if prompt else "n/a"
        return (
            f"{self.calls} call(s): {prompt} prompt tokens "
            f"({self.cache_read} cached / {self.cache_write} written / {self.input} full price, "
            f"{hit} from cache), {self.output} output"
        )

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
        self.usage = TokenUsage()

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
        effort: str | None = None,
        cache_system: bool = False,
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
        if effort is not None:
            params["output_config"] = {**params.get("output_config", {}), "effort": effort}
        if system is not None:
            params["system"] = self._system_param(system, cache_system)

        response = self._retrying(lambda: self._client.messages.create(**params))
        return "".join(block.text for block in response.content if block.type == "text")

    def _retrying(self, call: Callable[[], Any]) -> Any:
        """Run ``call``, retrying the API's transient generic 400."""
        for attempt in range(_TRANSIENT_RETRIES):
            try:
                response = call()
            except anthropic.BadRequestError as exc:
                if not _is_transient(exc) or attempt == _TRANSIENT_RETRIES - 1:
                    raise
                time.sleep(0.5 * (attempt + 1))
            else:
                self._record(response)
                return response
        raise AssertionError("unreachable")

    @staticmethod
    def _system_param(system: str, cache: bool) -> Any:
        """The ``system`` parameter, as a cached block when asked.

        A system prompt below the model's minimum cacheable prefix (512 tokens
        on Opus 5, 4096 on Haiku 4.5) is simply not cached — no error, and no
        charge for the attempt.
        """
        return [cached_text(system)] if cache else system

    def _record(self, response: Any) -> None:
        """Accumulate token usage, so a cache regression is visible."""
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        self.usage.add(usage)
        log.debug(
            "usage: input=%s cache_read=%s cache_write=%s output=%s",
            getattr(usage, "input_tokens", 0),
            getattr(usage, "cache_read_input_tokens", 0),
            getattr(usage, "cache_creation_input_tokens", 0),
            getattr(usage, "output_tokens", 0),
        )

    def parse(
        self,
        *,
        task: Task,
        messages: list[dict[str, Any]],
        output_format: type[T],
        system: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        effort: str | None = None,
        cache_system: bool = False,
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
        if effort is not None:
            # How hard the model thinks before answering. Thinking counts
            # against max_tokens, so a simple task left at the default can burn
            # the whole budget and truncate its own output.
            params["output_config"] = {**params.get("output_config", {}), "effort": effort}
        if system is not None:
            params["system"] = self._system_param(system, cache_system)

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
        cache_system: bool = False,
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
            base["system"] = self._system_param(system, cache_system)

        convo: list[Any] = list(messages)
        response = None
        for _ in range(4):
            response = self._client.messages.create(messages=convo, **base)
            self._record(response)
            if response.stop_reason != "pause_turn":
                break
            convo = convo + [{"role": "assistant", "content": response.content}]

        if response is None:
            return ""
        return "".join(block.text for block in response.content if block.type == "text")
