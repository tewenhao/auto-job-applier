"""Tests for env-driven settings and per-task model resolution."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings, Task


def _settings(**overrides: str) -> Settings:
    base = {"anthropic_api_key": "test-key"}
    base.update(overrides)
    # Pass values explicitly so the test never depends on a real .env / environment.
    return Settings(_env_file=None, **base)  # type: ignore[arg-type]


def test_defaults_are_populated() -> None:
    settings = _settings()
    assert settings.anthropic_api_key == "test-key"
    assert settings.model_interview == "claude-opus-5"
    assert settings.model_parse == "claude-haiku-4-5"


def test_model_for_maps_tasks() -> None:
    settings = _settings(model_interview="m-interview", model_parse="m-parse")
    assert settings.model_for(Task.INTERVIEW) == "m-interview"
    assert settings.model_for(Task.PARSE) == "m-parse"


def test_optional_fields_default_empty() -> None:
    settings = _settings()
    assert settings.supabase_url == ""
    assert settings.github_username == ""


def test_missing_api_key_raises() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]
