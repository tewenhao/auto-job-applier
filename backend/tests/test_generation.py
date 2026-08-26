"""Tests for the deterministic generation helpers (no LLM/network)."""

from __future__ import annotations

from uuid import uuid4

from app.generation.cover_letter import (
    _handling_notes,
    _samples_block,
    _strip_ai_dashes,
    _voice_block,
)
from app.generation.models import Application, ApplicationStatus, CompanyBrief
from app.profile.models import (
    Candidate,
    Experience,
    ExperienceKind,
    MasterProfile,
    VoiceProfile,
    WritingSample,
)

CID = uuid4()


def test_strip_ai_dashes_removes_em_and_en_dashes() -> None:
    assert _strip_ai_dashes("I built X — it mattered.") == "I built X, it mattered."
    assert _strip_ai_dashes("a tight—join") == "a tight, join"
    assert _strip_ai_dashes("one – two – three") == "one, two, three"
    # no dash: untouched
    assert _strip_ai_dashes("plain, clean text.") == "plain, clean text."


def test_strip_ai_dashes_preserves_signoff_and_paragraphs() -> None:
    # the sign-off comma must survive, and paragraph breaks must not collapse
    assert _strip_ai_dashes("Best wishes,\nEn Hao Tew") == "Best wishes,\nEn Hao Tew"
    assert _strip_ai_dashes("Para one —\n\nPara two") == "Para one,\n\nPara two"


def test_application_round_trip() -> None:
    app = Application(candidate_id=CID, listing_id=uuid4(), cover_letter="Dear team,")
    row = app.to_row()
    assert row["status"] == "draft"
    back = Application.from_row({**row, "id": str(uuid4())})
    assert back.cover_letter == "Dear team," and back.status == ApplicationStatus.DRAFT


def test_company_brief_round_trip() -> None:
    brief = CompanyBrief(candidate_id=CID, company_group="acme", brief="They build things.")
    row = brief.to_row()
    assert row["company_group"] == "acme"
    assert CompanyBrief.from_row({**row, "id": str(uuid4())}).brief == "They build things."


def test_handling_notes_gathers_candidate_and_experiences() -> None:
    profile = MasterProfile(
        candidate=Candidate(id=CID, handling_notes=["global rule"]),
        experiences=[
            Experience(candidate_id=CID, kind=ExperienceKind.WORK, handling_notes=["exp rule 1"]),
            Experience(
                candidate_id=CID, kind=ExperienceKind.PROJECT, handling_notes=["exp rule 2"]
            ),
        ],
    )
    assert _handling_notes(profile) == ["global rule", "exp rule 1", "exp rule 2"]


def test_voice_block_handles_missing_and_present() -> None:
    assert "no distilled voice" in _voice_block(None)
    voice = VoiceProfile(
        candidate_id=CID, tone="warm", summary="Concrete and dry.",
        guide={"quirks": ["em-dashes"], "donts": ["buzzwords"]},
    )
    block = _voice_block(voice)
    assert "warm" in block and "em-dashes" in block and "buzzwords" in block


def test_samples_block_truncates_and_limits() -> None:
    samples = [WritingSample(candidate_id=CID, text="x" * 5000, source="essay")]
    block = _samples_block(samples)
    assert block.startswith("[essay]") and len(block) < 3000
    assert _samples_block([]) == "(none)"
