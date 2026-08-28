"""Tests for the LLMClient wrapper (no network)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError

from app.config import Task
from app.llm.client import LLMClient, TokenUsage


class _Out(BaseModel):
    a: int
    b: str


def _make_client(parse_impl) -> LLMClient:  # noqa: ANN001
    """An LLMClient whose Anthropic client is faked, bypassing __init__."""
    client = object.__new__(LLMClient)
    client.settings = SimpleNamespace(model_for=lambda task: "fake-model")  # type: ignore[attr-defined]
    client._client = SimpleNamespace(  # type: ignore[attr-defined]
        messages=SimpleNamespace(parse=parse_impl)
    )
    client.usage = TokenUsage()  # normally set by __init__
    return client


def test_parse_truncated_json_raises_clear_error() -> None:
    # Reproduce the exact failure: a response cut off mid-string yields a
    # ValidationError of type json_invalid when the SDK parses it.
    def parse_impl(**_kw):  # noqa: ANN003, ANN202
        TypeAdapter(_Out).validate_json('{"a": 1, "b": "unterminated')

    client = _make_client(parse_impl)
    with pytest.raises(ValueError, match="cut off before it was valid JSON"):
        client.parse(task=Task.GENERATE, messages=[], output_format=_Out, max_tokens=8000)


def test_parse_other_validation_error_propagates() -> None:
    # A genuine schema mismatch (valid JSON, wrong shape) must not be masked.
    def parse_impl(**_kw):  # noqa: ANN003, ANN202
        TypeAdapter(_Out).validate_json('{"a": "not-an-int", "b": "ok"}')

    client = _make_client(parse_impl)
    with pytest.raises(ValidationError):
        client.parse(task=Task.GENERATE, messages=[], output_format=_Out, max_tokens=8000)


def test_parse_returns_parsed_output() -> None:
    def parse_impl(**_kw):  # noqa: ANN003, ANN202
        return SimpleNamespace(parsed_output=_Out(a=1, b="ok"))

    client = _make_client(parse_impl)
    result = client.parse(task=Task.GENERATE, messages=[], output_format=_Out)
    assert result == _Out(a=1, b="ok")


def _bad_request(message: str) -> Exception:
    """A BadRequestError as the SDK raises it, without a live response."""
    import anthropic

    return anthropic.BadRequestError.__new__(anthropic.BadRequestError, message)


def test_transient_invalid_request_data_is_retried() -> None:
    """The API occasionally 400s a well-formed request; an identical retry
    succeeds. The SDK never retries 4xx, so we do."""
    calls = {"n": 0}

    def parse_impl(**_kw):  # noqa: ANN003, ANN202
        calls["n"] += 1
        if calls["n"] == 1:
            raise _bad_request("Error code: 400 - Invalid request data")
        return SimpleNamespace(parsed_output=_Out(a=1, b="ok"))

    client = _make_client(parse_impl)
    assert client.parse(task=Task.GENERATE, messages=[], output_format=_Out) == _Out(a=1, b="ok")
    assert calls["n"] == 2  # retried once, then succeeded


def test_a_real_bad_request_is_not_retried() -> None:
    """A genuine 400 names what is wrong and must surface immediately."""
    import anthropic

    calls = {"n": 0}

    def parse_impl(**_kw):  # noqa: ANN003, ANN202
        calls["n"] += 1
        raise _bad_request("Error code: 400 - This model does not support assistant prefill")

    client = _make_client(parse_impl)
    with pytest.raises(anthropic.BadRequestError):
        client.parse(task=Task.GENERATE, messages=[], output_format=_Out)
    assert calls["n"] == 1  # no retry


def test_system_prompt_is_sent_as_a_cached_block_when_asked() -> None:
    """Caching is opt-in per route, and the marker has to reach the request."""
    sent: dict[str, object] = {}

    def parse_impl(**kw):  # noqa: ANN003, ANN202
        sent.update(kw)
        return SimpleNamespace(parsed_output=_Out(a=1, b="ok"))

    client = _make_client(parse_impl)
    client.parse(
        task=Task.GENERATE,
        messages=[],
        output_format=_Out,
        system="the instructions",
        cache_system=True,
    )
    assert sent["system"] == [
        {
            "type": "text",
            "text": "the instructions",
            "cache_control": {"type": "ephemeral"},
        }
    ]


def test_system_prompt_is_a_plain_string_by_default() -> None:
    sent: dict[str, object] = {}

    def parse_impl(**kw):  # noqa: ANN003, ANN202
        sent.update(kw)
        return SimpleNamespace(parsed_output=_Out(a=1, b="ok"))

    client = _make_client(parse_impl)
    client.parse(task=Task.GENERATE, messages=[], output_format=_Out, system="plain")
    assert sent["system"] == "plain"


def test_usage_totals_accumulate_across_calls() -> None:
    """A cache regression is silent — requests still succeed, the bill is just
    higher — so the usage numbers are the only ground truth we have."""

    def parse_impl(**_kw):  # noqa: ANN003, ANN202
        return SimpleNamespace(
            parsed_output=_Out(a=1, b="ok"),
            usage=SimpleNamespace(
                input_tokens=100,
                output_tokens=20,
                cache_read_input_tokens=900,
                cache_creation_input_tokens=0,
            ),
        )

    client = _make_client(parse_impl)
    client.parse(task=Task.GENERATE, messages=[], output_format=_Out)
    client.parse(task=Task.GENERATE, messages=[], output_format=_Out)
    assert client.usage.calls == 2
    assert client.usage.cache_read == 1800
    assert client.usage.input == 200
    assert "90% from cache" in client.usage.summary()
