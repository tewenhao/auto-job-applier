"""Tests for the LLMClient wrapper (no network)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError

from app.config import Task
from app.llm.client import LLMClient


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
