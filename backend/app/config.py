"""Env-driven application settings.

Everything user- or deployment-specific lives here and is loaded from the
environment (or a local ``.env`` file), never hardcoded — so the repo can be
shared and each user runs it against their own keys, Supabase project, and
GitHub account.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

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
    GENERATE = "generate"  # application generation (cover letter, resume) — quality-critical


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
    model_generate: str = Field(
        "claude-opus-5",
        description="Model for application generation (cover letter, resume).",
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

    # --- Profile ---
    master_doc_path: str = Field(
        "candidate-inputs/master-doc.md",
        description="The master document — the human source of truth. New "
        "entries captured in the dashboard are written here, then re-ingested.",
    )

    # --- Listings (Module 2) ---
    listing_score_threshold: int = Field(
        60, description="Listings scoring at/above this (0-100) are surfaced."
    )
    browser_fallback: bool = Field(
        True,
        description="Render JS/blocked postings with a headless browser when the "
        "plain HTTP fetch comes up empty (needs the 'browser' extra + chromium).",
    )
    browser_executable_path: str = Field(
        "",
        description="Optional chromium path for Playwright (e.g. a preinstalled "
        "build); empty uses Playwright's managed browser.",
    )

    def resolved_master_doc_path(self) -> Path:
        """The master-doc as an absolute path.

        A relative setting is tried against the working directory first, then
        the repository root — the CLI and `ajp serve` are usually run from
        ``backend/``, while the default path is written from the repo root.
        """
        raw = Path(self.master_doc_path).expanduser()
        if raw.is_absolute():
            return raw
        if raw.exists():
            return raw.resolve()
        repo_root = Path(__file__).resolve().parents[2]
        return (repo_root / raw).resolve()

    def model_for(self, task: Task) -> str:
        """Return the configured model id for a given task."""
        return {
            Task.INTERVIEW: self.model_interview,
            Task.PARSE: self.model_parse,
            Task.CONSOLIDATE: self.model_consolidate,
            Task.GENERATE: self.model_generate,
        }[task]


@lru_cache
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance.

    Lazy so that ``--help`` and other no-op CLI paths don't require a populated
    ``.env``; validation happens the first time a command actually needs config.
    """
    return Settings()  # type: ignore[call-arg]
