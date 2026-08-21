"""Tests for Markdown rendering of the master profile."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

from app.profile.markdown import profile_to_markdown
from app.profile.models import (
    Candidate,
    Experience,
    ExperienceKind,
    GithubProfile,
    MasterProfile,
    Preferences,
    Skill,
)

CID = uuid4()


def _profile() -> MasterProfile:
    return MasterProfile(
        candidate=Candidate(
            id=CID, full_name="Jordan Lee", email="j@example.com", github_url="https://github.com/jlee"
        ),
        experiences=[
            Experience(
                candidate_id=CID,
                kind=ExperienceKind.WORK,
                org="Acme",
                title="SWE Intern",
                start_date=date(2025, 6, 1),
                is_current=True,
                summary="Built stuff.",
                detail="Longer elaboration of the work.",
                highlights=["Shipped X", "Cut latency 30%"],
                skills=["Python"],
                tech=["FastAPI"],
            )
        ],
        skills=[Skill(candidate_id=CID, name="Python", category="Languages")],
        github=GithubProfile(
            candidate_id=CID, username="jlee", repos=[{"name": "a"}], languages={"Python": 90}
        ),
        preferences=Preferences(candidate_id=CID, domains=["swe", "ml"], avoid=["crypto"]),
    )


def test_renders_core_sections() -> None:
    md = profile_to_markdown(_profile())
    assert "# Jordan Lee" in md
    assert "## Experience" in md
    assert "SWE Intern · Acme" in md
    assert "2025-06-01 – present" in md
    assert "Longer elaboration" in md  # detail (the superset) is included
    assert "- Shipped X" in md
    assert "## Skills" in md and "**Languages**: Python" in md
    assert "## GitHub" in md and "@jlee" in md
    assert "## Preferences" in md and "swe, ml" in md
    assert md.endswith("\n")


def test_minimal_profile_has_no_empty_sections() -> None:
    md = profile_to_markdown(MasterProfile(candidate=Candidate(id=CID)))
    assert md.startswith("# Candidate profile")
    assert "## Experience" not in md
    assert "## Skills" not in md
