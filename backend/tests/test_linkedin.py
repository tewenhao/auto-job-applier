"""Tests for LinkedIn export parsing (deterministic, no LLM/network)."""

from __future__ import annotations

import zipfile
from datetime import date
from pathlib import Path
from uuid import uuid4

from app.ingestion.consolidate import _merge_dates
from app.ingestion.linkedin import build_linkedin_extraction, read_linkedin_tables
from app.ingestion.mapping import normalize_date
from app.profile.models import Experience, ExperienceKind

CID = uuid4()

POSITIONS = (
    "Company Name,Title,Description,Location,Started On,Finished On\n"
    "Jane Street,Trading Intern,Did trading things,London,Apr 2026,\n"
    "IMDA,AI Engineer Intern,Built BIM stuff,Singapore,Jul 2026,Sep 2026\n"
)
EDUCATION = (
    "School Name,Start Date,End Date,Notes,Degree Name\n"
    "University of Cambridge,2025,2028,Reading CS,BA (Hons) Computer Science\n"
)
SKILLS = "Name\nPython\nLangGraph\n"
PROFILE = "First Name,Last Name,Geo Location,Summary\nEn Hao,Tew,Singapore,I build tech for good.\n"


def _make_zip(tmp_path: Path) -> Path:
    p = tmp_path / "linkedin.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("Positions.csv", POSITIONS)
        z.writestr("Education.csv", EDUCATION)
        z.writestr("Skills.csv", SKILLS)
        z.writestr("Profile.csv", PROFILE)
    return p


def test_normalize_date_month_names() -> None:
    assert normalize_date("Apr 2026") == date(2026, 4, 1)
    assert normalize_date("June 2023") == date(2023, 6, 1)


def test_read_and_build_from_zip(tmp_path: Path) -> None:
    tables = read_linkedin_tables(_make_zip(tmp_path))
    assert set(tables) >= {"positions", "education", "skills", "profile"}

    contact, experiences, skills, about = build_linkedin_extraction(tables)

    assert contact is not None
    assert contact.full_name == "En Hao Tew"
    assert contact.location == "Singapore"
    assert about == "I build tech for good."

    kinds = {(e.kind, e.org, e.title) for e in experiences}
    assert (ExperienceKind.WORK, "Jane Street", "Trading Intern") in kinds
    cambridge = (ExperienceKind.EDUCATION, "University of Cambridge", "BA (Hons) Computer Science")
    assert cambridge in kinds

    jane = next(e for e in experiences if e.org == "Jane Street")
    assert jane.start == "Apr 2026" and jane.end is None and jane.is_current is True

    imda = next(e for e in experiences if e.org == "IMDA")
    assert imda.is_current is False and imda.end == "Sep 2026"

    assert {s.name for s in skills} == {"Python", "LangGraph"}


def test_read_from_directory(tmp_path: Path) -> None:
    (tmp_path / "Skills.csv").write_text(SKILLS, encoding="utf-8")
    tables = read_linkedin_tables(tmp_path)
    assert len(tables["skills"]) == 2


def test_merge_dates_prefers_linkedin() -> None:
    # master-doc entry defaulted to Jan 1; LinkedIn has the real month.
    members = [
        Experience(
            candidate_id=CID, kind=ExperienceKind.WORK, source="master_doc",
            start_date=date(2026, 1, 1), end_date=date(2026, 1, 1),
        ),
        Experience(
            candidate_id=CID, kind=ExperienceKind.WORK, source="linkedin",
            start_date=date(2026, 7, 1), end_date=date(2026, 9, 1),
        ),
    ]
    start, end, _ = _merge_dates(members)
    assert start == date(2026, 7, 1)  # LinkedIn's precise date wins, not the earlier default
    assert end == date(2026, 9, 1)
