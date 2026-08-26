"""LLM-facing extraction schemas.

Lightweight Pydantic models the parser fills from raw document text. Deliberately
separate from the DB models in ``app.profile.models``: the LLM should only supply
*content*, not ids, timestamps, ``candidate_id``, or provenance — those are
attached during mapping (``app.ingestion.mapping``).

Dates are free-form strings (``"2025"``, ``"2025-06"``, ``"2025-06-01"``) because
resumes rarely give full dates; mapping normalizes them.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.profile.models import ExperienceKind


class ExtractedContact(BaseModel):
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    github_url: str | None = None
    linkedin_url: str | None = None
    portfolio_url: str | None = None


class ExtractedExperience(BaseModel):
    kind: ExperienceKind
    org: str | None = None
    title: str | None = None
    location: str | None = None
    start: str | None = None  # free-form; mapping normalizes to a date
    end: str | None = None
    is_current: bool = False
    summary: str | None = None  # concise, resume-style
    detail: str | None = None  # richer elaboration (FACTS + VOICE), no private guidance
    skills: list[str] = Field(default_factory=list)
    tech: list[str] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)
    handling_notes: list[str] = Field(default_factory=list)  # PRIVATE / do-not-surface guidance


class ExtractedSkill(BaseModel):
    name: str
    category: str | None = None
    proficiency: str | None = None
    years: float | None = None


class ProfileExtraction(BaseModel):
    """The full result of extracting one document."""

    contact: ExtractedContact | None = None
    experiences: list[ExtractedExperience] = Field(default_factory=list)
    skills: list[ExtractedSkill] = Field(default_factory=list)
