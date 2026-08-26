"""Typed models mirroring the candidate-profile schema.

These Pydantic models are the shared contract: every downstream module imports
them as the "context base for all generation." They map 1:1 to the tables in
``supabase/migrations`` — field names match columns so ``to_row()`` / ``from_row``
round-trip cleanly through the Supabase REST API.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# --- Enumerations (mirror the SQL CHECK constraints) ---
class SourceType(StrEnum):
    RESUME = "resume"
    LINKEDIN_EXPORT = "linkedin_export"
    ESSAY = "essay"
    COVER_LETTER = "cover_letter"
    MASTER_DOC = "master_doc"
    PORTFOLIO = "portfolio"
    OTHER = "other"


class ExperienceKind(StrEnum):
    WORK = "work"
    PROJECT = "project"
    EDUCATION = "education"
    LEADERSHIP = "leadership"
    AWARD = "award"
    OPEN_SOURCE = "open_source"
    OTHER = "other"


class InterviewRole(StrEnum):
    ASSISTANT = "assistant"
    USER = "user"


class InterviewStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class ProfileBase(BaseModel):
    """Base for all table-backed models: id plus row (de)serialization helpers.

    ``created_at`` is declared per-model (not here) because not every table has
    that column — ``interview_sessions`` uses ``started_at`` instead.
    """

    model_config = ConfigDict(use_enum_values=True)

    id: UUID | None = None

    def to_row(self) -> dict[str, Any]:
        """Serialize to a Supabase-insertable dict.

        Drops unset fields and server-managed timestamps so the database fills
        in ids/defaults. JSON mode renders UUID/datetime/date as strings, which
        PostgREST expects.
        """
        return self.model_dump(
            mode="json",
            exclude_none=True,
            exclude={"created_at", "updated_at"},
        )

    @classmethod
    def from_row(cls, row: dict[str, Any]):
        """Build a model from a Supabase row dict."""
        return cls.model_validate(row)


class Evidence(BaseModel):
    """A pointer from a profile fact back to where it came from."""

    type: str  # e.g. "github_repo" | "source_document"
    ref: str | None = None  # repo name, document id, url, ...
    span: str | None = None  # optional locator within the ref


class Candidate(ProfileBase):
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    github_url: str | None = None
    linkedin_url: str | None = None
    portfolio_url: str | None = None
    links: dict[str, Any] = Field(default_factory=dict)
    handling_notes: list[str] = Field(default_factory=list)  # global "do not surface" guidance
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SourceDocument(ProfileBase):
    candidate_id: UUID
    type: SourceType
    filename: str | None = None
    raw_text: str | None = None
    storage_path: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
    parsed_at: datetime | None = None
    created_at: datetime | None = None


class Experience(ProfileBase):
    candidate_id: UUID
    kind: ExperienceKind
    org: str | None = None
    title: str | None = None
    location: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    is_current: bool = False
    summary: str | None = None  # concise (resume-style)
    detail: str | None = None  # rich elaboration (the superset)
    skills: list[str] = Field(default_factory=list)
    tech: list[str] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    source: str | None = None  # which input, or "interview"
    source_document_id: UUID | None = None
    confidence: float | None = None
    handling_notes: list[str] = Field(default_factory=list)  # constraints, never surfaced
    created_at: datetime | None = None
    updated_at: datetime | None = None


class Skill(ProfileBase):
    candidate_id: UUID
    name: str
    category: str | None = None
    proficiency: str | None = None
    years: float | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class GithubProfile(ProfileBase):
    candidate_id: UUID
    username: str | None = None
    repos: list[dict[str, Any]] = Field(default_factory=list)
    languages: dict[str, Any] = Field(default_factory=dict)
    stats: dict[str, Any] = Field(default_factory=dict)
    pulled_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class WritingSample(ProfileBase):
    candidate_id: UUID
    text: str
    source: str | None = None
    source_document_id: UUID | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: datetime | None = None


class VoiceProfile(ProfileBase):
    candidate_id: UUID
    tone: str | None = None
    summary: str | None = None
    guide: dict[str, Any] = Field(default_factory=dict)  # rhythm, vocab, quirks, do/don't
    built_from: list[str] = Field(default_factory=list)  # writing_sample ids
    created_at: datetime | None = None
    updated_at: datetime | None = None


class Preferences(ProfileBase):
    candidate_id: UUID
    role_types: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    company_sizes: list[str] = Field(default_factory=list)
    location_markets: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
    weights: dict[str, Any] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class InterviewSession(ProfileBase):
    candidate_id: UUID
    status: InterviewStatus = InterviewStatus.IN_PROGRESS
    started_at: datetime | None = None
    completed_at: datetime | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class InterviewTurn(ProfileBase):
    session_id: UUID
    candidate_id: UUID
    seq: int
    role: InterviewRole
    content: str
    created_at: datetime | None = None


class MasterProfile(BaseModel):
    """The assembled superset — what downstream generation reads from."""

    candidate: Candidate
    experiences: list[Experience] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)
    github: GithubProfile | None = None
    writing_samples: list[WritingSample] = Field(default_factory=list)
    voice: VoiceProfile | None = None
    preferences: Preferences | None = None
