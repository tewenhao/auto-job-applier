"""Env-driven application settings.

Everything user- or deployment-specific lives here and is loaded from the
environment (or a local ``.env`` file), never hardcoded — so the repo can be
shared and each user runs it against their own keys, Supabase project, and
GitHub account.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Task(StrEnum):
    """The distinct LLM jobs in the system, each mapped to a model in settings.

    Keeping model choice keyed by *task* (not hardcoded at call sites) lets us
    tune cost/quality per job from config: a capable model for the
    conversational interview, a cheap fast one for bulk extraction.
    """

    INTERVIEW = "interview"  # conversational onboarding — follow-up quality matters
    PARSE = "parse"  # bulk structured extraction (resume/LinkedIn -> JSON), cheap & frequent
    CONSOLIDATE = "consolidate"  # semantic dedup/merge of the experience bank — judgment-heavy


class Settings(BaseSettings):
    """Application configuration, populated from environment / ``.env``."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Our fields intentionally start with ``model_``; opt out of pydantic's
        # protected-namespace warning for them.
        protected_namespaces=(),
    )

    # --- Anthropic (LLM) ---
    anthropic_api_key: str = Field(..., description="Anthropic API key (bring your own).")
    model_interview: str = Field(
        "claude-opus-5",
        description="Model for the onboarding interview (quality-sensitive).",
    )
    model_parse: str = Field(
        "claude-haiku-4-5",
        description="Model for bulk structured extraction (cheap & frequent).",
    )
    model_consolidate: str = Field(
        "claude-opus-5",
        description="Model for semantic dedup/merge of the experience bank.",
    )

    # --- Supabase (source of truth) ---
    supabase_url: str = Field("", description="Supabase project URL.")
    supabase_key: str = Field(
        "",
        description="Supabase service-role key (backend access; keep secret).",
    )

    # --- GitHub (profile ingestion) ---
    github_token: str = Field("", description="GitHub personal access token.")
    github_username: str = Field("", description="GitHub username to ingest.")

    # --- Listings (Module 2) ---
    listing_score_threshold: int = Field(
        60, description="Listings scoring at/above this (0-100) are surfaced."
    )

    def model_for(self, task: Task) -> str:
        """Return the configured model id for a given task."""
        return {
            Task.INTERVIEW: self.model_interview,
            Task.PARSE: self.model_parse,
            Task.CONSOLIDATE: self.model_consolidate,
        }[task]


@lru_cache
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance.

    Lazy so that ``--help`` and other no-op CLI paths don't require a populated
    ``.env``; validation happens the first time a command actually needs config.
    """
    return Settings()  # type: ignore[call-arg]
