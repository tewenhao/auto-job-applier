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


def test_document_filename_defaults_and_override() -> None:
    from app.generation.naming import COVER_LETTER, document_filename

    assert (
        document_filename(candidate_name="En Hao Tew", company="Citadel")
        == "en-hao-tew-citadel-resume.pdf"
    )
    assert (
        document_filename(
            candidate_name="En Hao Tew", company="The D. E. Shaw Group", kind=COVER_LETTER
        )
        == "en-hao-tew-the-d-e-shaw-group-cover-letter.pdf"
    )
    # unknown parts are skipped rather than left as empty separators
    assert document_filename(candidate_name="En Hao Tew", company=None) == "en-hao-tew-resume.pdf"
    assert document_filename(candidate_name=None, company=None) == "resume.pdf"
    assert (
        document_filename(candidate_name="En Hao Tew", company="Citadel", ext="tex")
        == "en-hao-tew-citadel-resume.tex"
    )
    # an ATS-required name wins (Module 5), extension still enforced
    assert (
        document_filename(candidate_name="X", company="Y", override="Resume_2027.pdf")
        == "resume-2027.pdf"
    )


class _CapturingLLM:
    """Records the request instead of sending it."""

    def __init__(self, result: object = None) -> None:
        self.result = result
        self.kwargs: dict = {}

    def parse(self, **kwargs):  # noqa: ANN003, ANN201
        self.kwargs = kwargs
        return self.result

    def complete(self, **kwargs):  # noqa: ANN003, ANN201
        self.kwargs = kwargs
        return "Dear team, ..."


def _profile() -> MasterProfile:
    return MasterProfile(
        candidate=Candidate(id=CID, full_name="En Hao Tew"),
        experiences=[
            Experience(
                candidate_id=CID,
                kind=ExperienceKind.WORK,
                title="Intern",
                org="Acme",
                summary="Did a thing.",
            )
        ],
    )


def _listing():  # noqa: ANN202
    from app.listings.models import Listing, ListingSource

    return Listing(
        candidate_id=CID,
        source=ListingSource.MANUAL,
        url="https://example.com/job",
        company="Globex",
        role_title="SWE Intern",
        jd_summary="Build things.",
        requirements=["python"],
    )


def _blocks(llm: _CapturingLLM) -> list[dict]:
    (message,) = llm.kwargs["messages"]
    return message["content"]


def test_resume_prompt_caches_the_profile_ahead_of_the_per_listing_tail() -> None:
    """The profile is ~17k tokens and identical for every listing. Caching is a
    prefix match, so it only pays if it comes BEFORE anything role-specific —
    put the company first and every listing writes a fresh entry and reads none.
    """
    from app.generation.resume import tailor_resume

    llm = _CapturingLLM(result=object())
    tailor_resume(llm, listing=_listing(), profile=_profile(), brief=None)  # type: ignore[arg-type]

    first, second = _blocks(llm)
    assert first["cache_control"] == {"type": "ephemeral"}
    assert "Candidate profile" in first["text"] and "En Hao Tew" in first["text"]
    assert "cache_control" not in second
    assert "Globex" in second["text"]  # the volatile half, after the breakpoint
    assert "Globex" not in first["text"]
    assert llm.kwargs["cache_system"] is True


def test_cover_letter_prompt_caches_profile_and_samples_ahead_of_the_role() -> None:
    from app.generation.cover_letter import generate_cover_letter

    llm = _CapturingLLM()
    generate_cover_letter(  # type: ignore[arg-type]
        llm,
        listing=_listing(),
        profile=_profile(),
        voice=None,
        samples=[WritingSample(candidate_id=CID, source="essay", text="I write like this.")],
        brief=None,
        resume_points=["shipped a thing"],
    )

    first, second = _blocks(llm)
    assert first["cache_control"] == {"type": "ephemeral"}
    assert "En Hao Tew" in first["text"] and "I write like this." in first["text"]
    assert "Globex" not in first["text"]
    assert "cache_control" not in second
    assert "Globex" in second["text"] and "shipped a thing" in second["text"]
    assert llm.kwargs["cache_system"] is True
