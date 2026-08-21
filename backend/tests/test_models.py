"""Tests for the profile models: row serialization and enum handling."""

from __future__ import annotations

from datetime import date
from uuid import UUID, uuid4

from app.profile.models import (
    Evidence,
    Experience,
    ExperienceKind,
    SourceDocument,
    SourceType,
)

CANDIDATE_ID = uuid4()


def test_to_row_drops_none_id_and_timestamps() -> None:
    exp = Experience(
        candidate_id=CANDIDATE_ID,
        kind=ExperienceKind.WORK,
        org="Acme",
        title="SWE Intern",
    )
    row = exp.to_row()
    assert "id" not in row  # unset -> DB assigns
    assert "created_at" not in row and "updated_at" not in row
    assert row["candidate_id"] == str(CANDIDATE_ID)  # UUID -> str for PostgREST
    assert row["kind"] == "work"  # enum -> value


def test_dates_and_nested_evidence_serialize_json() -> None:
    exp = Experience(
        candidate_id=CANDIDATE_ID,
        kind=ExperienceKind.PROJECT,
        start_date=date(2025, 6, 1),
        evidence=[Evidence(type="github_repo", ref="me/proj")],
    )
    row = exp.to_row()
    assert row["start_date"] == "2025-06-01"
    # exclude_none recurses into nested models, so span=None is dropped.
    assert row["evidence"] == [{"type": "github_repo", "ref": "me/proj"}]


def test_from_row_round_trip() -> None:
    row = {
        "id": str(uuid4()),
        "candidate_id": str(CANDIDATE_ID),
        "type": "resume",
        "filename": "cv.pdf",
        "raw_text": "hello",
    }
    doc = SourceDocument.from_row(row)
    assert doc.type == SourceType.RESUME
    assert isinstance(doc.id, UUID)
    assert doc.candidate_id == CANDIDATE_ID
    assert doc.meta == {}  # default filled in


def test_enum_value_used_in_dump() -> None:
    exp = Experience(candidate_id=CANDIDATE_ID, kind=ExperienceKind.OPEN_SOURCE)
    assert exp.to_row()["kind"] == "open_source"
