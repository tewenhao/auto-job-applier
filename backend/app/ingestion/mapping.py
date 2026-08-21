"""Map LLM extraction results onto the DB models (attach identity + provenance)."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from app.ingestion.schema import ExtractedContact, ExtractedExperience, ExtractedSkill
from app.profile.models import Candidate, Experience, Skill

_DATE_FORMATS = ("%Y-%m-%d", "%Y-%m", "%Y")


def normalize_date(value: str | None) -> date | None:
    """Parse a free-form date string to a ``date``.

    Missing day/month default to the 1st / January, so '2025' -> 2025-01-01 and
    '2025-06' -> 2025-06-01. Returns None if unparseable.
    """
    if not value:
        return None
    value = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def to_experience(
    x: ExtractedExperience,
    *,
    candidate_id: UUID,
    source: str,
    source_document_id: UUID | None = None,
) -> Experience:
    return Experience(
        candidate_id=candidate_id,
        kind=x.kind,
        org=x.org,
        title=x.title,
        location=x.location,
        start_date=normalize_date(x.start),
        end_date=normalize_date(x.end),
        is_current=x.is_current,
        summary=x.summary,
        detail=x.detail,
        skills=x.skills,
        tech=x.tech,
        highlights=x.highlights,
        source=source,
        source_document_id=source_document_id,
    )


def to_skill(x: ExtractedSkill, *, candidate_id: UUID) -> Skill:
    return Skill(
        candidate_id=candidate_id,
        name=x.name,
        category=x.category,
        proficiency=x.proficiency,
        years=x.years,
    )


def apply_contact(candidate: Candidate, contact: ExtractedContact) -> Candidate:
    """Fill in any candidate fields that are currently empty, without clobbering
    values the user already has. Returns a new Candidate to persist."""
    data = candidate.model_dump()
    for field, value in contact.model_dump().items():
        if value and not data.get(field):
            data[field] = value
    return Candidate.model_validate(data)
