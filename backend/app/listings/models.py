"""Typed model for job listings (mirrors the ``listings`` table)."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ListingSource(StrEnum):
    MANUAL = "manual"
    SCRAPED = "scraped"


class ListingStatus(StrEnum):
    NEW = "new"  # ingested, not yet scored
    SURFACED = "surfaced"  # scored above threshold, awaiting user
    FILTERED = "filtered"  # dropped by a hard filter (market / avoid-list)
    CHOSEN = "chosen"  # user picked this to pursue (HITL gate)
    DISMISSED = "dismissed"  # user passed
    APPLIED = "applied"  # application submitted


class Listing(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: UUID | None = None
    candidate_id: UUID

    source: ListingSource
    source_name: str | None = None
    url: str | None = None
    ats: str | None = None

    company: str | None = None
    company_group: str | None = None  # normalized company (one-role-per-company)
    role_title: str | None = None
    domain: str | None = None
    market: str | None = None
    location: str | None = None

    jd_text: str | None = None
    jd_summary: str | None = None
    requirements: list[str] = Field(default_factory=list)
    posted_at: date | None = None
    deadline: date | None = None

    score: int | None = None
    score_rationale: str | None = None
    score_breakdown: dict[str, Any] = Field(default_factory=dict)

    status: ListingStatus = ListingStatus.NEW

    created_at: datetime | None = None
    updated_at: datetime | None = None

    def to_row(self) -> dict[str, Any]:
        return self.model_dump(
            mode="json", exclude_none=True, exclude={"created_at", "updated_at"}
        )

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> Listing:
        return cls.model_validate(row)


def normalize_company(name: str | None) -> str | None:
    """A loose grouping key for the one-role-per-company rule."""
    if not name:
        return None
    cleaned = name.lower().strip()
    for suffix in (" inc", " inc.", " ltd", " ltd.", " llc", " limited", " plc", " pte", " gmbh"):
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)]
    return " ".join(cleaned.split()) or None
