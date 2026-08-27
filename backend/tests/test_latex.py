"""Deterministic tests for the LaTeX resume renderer (no LLM/network)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.generation.latex import (
    _render_text,
    compile_to_page_limit,
    latex_escape,
    render_resume,
)
from app.generation.resume import (
    EducationEntry,
    ExperienceEntry,
    ProjectEntry,
    RankedItem,
    SkillGroup,
    TailoredResume,
    trim_one_step,
)
from app.profile.models import Candidate


def test_latex_escape_specials() -> None:
    assert latex_escape("a & b 50% #1 $x_y") == r"a \& b 50\% \#1 \$x\_y"


def test_bold_markers_after_escaping() -> None:
    # The percent inside the bold span must be escaped; the marker becomes \textbf.
    assert _render_text("improved by **15%** overall") == r"improved by \textbf{15\%} overall"


def test_approximate_tilde_becomes_math_sim() -> None:
    # "~" before a number -> $\sim$; a bare "~" stays a literal tilde.
    assert _render_text("1 of ~75 participants") == r"1 of $\sim$75 participants"
    assert _render_text("~10 years") == r"$\sim$10 years"
    assert _render_text("path a~b") == r"path a\textasciitilde{}b"


def test_render_resume_slot_mapping_and_structure() -> None:
    candidate = Candidate(
        full_name="En Hao Tew",
        email="a@b.com",
        phone="+44 123",
        linkedin_url="https://www.linkedin.com/in/en-hao-tew",
        github_url="https://github.com/tewenhao",
    )
    resume = TailoredResume(
        education=[
            EducationEntry(
                school="University of Cambridge",
                location="Cambridge, UK",
                degree="BA Computer Science",
                dates="Oct 2025 -- Jun 2028",
                bullets=["Relevant modules: Algorithms"],
            )
        ],
        experience=[
            ExperienceEntry(
                title="AI Engineer",
                org="RSAF RAiD",
                location="Singapore",
                dates="Sep 2024 -- Feb 2025",
                bullets=["Built a **modular search framework**"],
            )
        ],
        projects=[
            ProjectEntry(
                name="SMU LIT Hackathon",
                tools="LangGraph",
                dates="Sep 2025",
                bullets=["**First Place Overall**"],
            )
        ],
        projects_title="Hackathon Achievements",
        skills=[SkillGroup(label="Programming", items="Python, LaTeX")],
    )
    tex = render_resume(resume, candidate)

    # Header + preamble kept.
    assert r"\documentclass[letterpaper,10pt]{article}" in tex
    assert r"\Huge \scshape En Hao Tew" in tex
    assert tex.strip().endswith(r"\end{document}")

    # Education slot mapping: {school}{location} then {degree}{dates}.
    assert r"{University of Cambridge}{Cambridge, UK}" in tex
    assert r"{BA Computer Science}{Oct 2025 -- Jun 2028}" in tex

    # Experience slot mapping: {title}{dates} then {org}{location}.
    assert r"{AI Engineer}{Sep 2024 -- Feb 2025}" in tex
    assert r"{RSAF RAiD}{Singapore}" in tex

    # Project heading + bold conversion.
    assert r"\textbf{SMU LIT Hackathon} $|$ \emph{LangGraph}" in tex
    assert r"\resumeItem{\textbf{First Place Overall}}" in tex
    assert r"\section{Hackathon Achievements}" in tex

    # Skills line.
    assert r"\textbf{Programming}{: Python, \LaTeX}" not in tex  # LLM gives plain text
    assert r"\textbf{Programming}{: Python, LaTeX}" in tex


def test_ranking_is_carried_but_not_rendered() -> None:
    # The ranking is metadata for review/steering; it must never leak into the .tex.
    resume = TailoredResume(
        ranking=[
            RankedItem(
                kind="experience", label="RSAF RAiD", score=95, included=True, rationale="core"
            ),
            RankedItem(
                kind="project", label="panic button", score=20, included=False, rationale="weak"
            ),
        ],
        experience=[ExperienceEntry(title="AI Engineer", org="RSAF", bullets=["x"])],
    )
    tex = render_resume(resume, Candidate(full_name="X"))
    assert "panic button" not in tex and "rationale" not in tex
    # Round-trips through JSON persistence (resume_content is a dict).
    assert TailoredResume.model_validate(resume.model_dump(mode="json")).ranking[0].score == 95


def test_ranked_item_score_bounds() -> None:
    with pytest.raises(ValidationError):
        RankedItem(kind="experience", label="x", score=150, included=True, rationale="y")


def test_compose_steer_combines_standing_and_per_call() -> None:
    from app.generation.resume import compose_steer

    assert compose_steer(None, None) is None
    assert compose_steer("  ", "") is None
    assert compose_steer("prioritise real roles", None) == (
        "Standing preferences (apply to every resume): prioritise real roles"
    )
    both = compose_steer("prioritise real roles", "keep the RSAF paper")
    assert both is not None
    assert "Standing preferences" in both and "For THIS application" in both
    assert both.index("Standing") < both.index("For THIS")  # standing first, per-call after


def test_empty_sections_are_dropped() -> None:
    tex = render_resume(TailoredResume(), Candidate(full_name="X"))
    assert r"\section{Education}" not in tex
    assert r"\section{Experience}" not in tex
    assert r"\begin{document}" in tex and r"\end{document}" in tex


def test_experience_rendered_reverse_chronological() -> None:
    # Given out of order + varied end_date formats, display is newest-first.
    resume = TailoredResume(
        experience=[
            ExperienceEntry(title="Oldest", end_date="2023-06", bullets=["x"]),
            ExperienceEntry(title="Ongoing", end_date="present", bullets=["x"]),
            ExperienceEntry(title="Middle", end_date="2025", bullets=["x"]),
        ]
    )
    tex = render_resume(resume, Candidate(full_name="X"))
    order = [tex.index("{Ongoing}"), tex.index("{Middle}"), tex.index("{Oldest}")]
    assert order == sorted(order)  # Ongoing before Middle before Oldest


def test_projects_rendered_reverse_chronological() -> None:
    resume = TailoredResume(
        projects=[
            ProjectEntry(name="OldProj", end_date="2023", bullets=["x"]),
            ProjectEntry(name="NewProj", end_date="2025-09", bullets=["x"]),
            ProjectEntry(name="MidProj", end_date="2024", bullets=["x"]),
        ]
    )
    tex = render_resume(resume, Candidate(full_name="X"))
    order = [tex.index("NewProj"), tex.index("MidProj"), tex.index("OldProj")]
    assert order == sorted(order)  # newest project first


def _resume_for_trim() -> TailoredResume:
    return TailoredResume(
        experience=[
            ExperienceEntry(title="A", bullets=["a1", "a2", "a3"]),
            ExperienceEntry(title="B", bullets=["b1"]),
            ExperienceEntry(title="C", bullets=["c1"]),
        ],
        projects=[ProjectEntry(name="P", bullets=["p1", "p2"])],
    )


def test_trim_drops_whole_projects_before_experiences_before_shaving() -> None:
    # 4 experiences + 3 projects, all with full bullets. Whole projects go first
    # (weakest last), then whole experiences — no bullet is shaved while entries
    # remain, so survivors keep their numbers and elaboration.
    r = TailoredResume(
        experience=[ExperienceEntry(title=t, bullets=["1", "2", "3"]) for t in "ABCD"],
        projects=[ProjectEntry(name=f"P{i}", bullets=["x", "y"]) for i in range(1, 4)],
    )
    r1, n1 = trim_one_step(r)  # type: ignore[misc]
    assert n1.startswith("dropped project 'P3'")  # weakest (last) project first
    assert len(r1.projects) == 2
    # Nothing shaved: every surviving entry keeps all its bullets.
    assert all(len(e.bullets) == 3 for e in r1.experience)

    r2, n2 = trim_one_step(r1)  # type: ignore[misc]
    assert n2.startswith("dropped project 'P2'")  # projects continue down to the floor of 1

    r3, n3 = trim_one_step(r2)  # type: ignore[misc]
    assert n3.startswith("dropped experience 'D'")  # only then whole experiences
    assert len(r3.projects) == 1 and all(len(e.bullets) == 3 for e in r3.experience)


def test_trim_shaves_only_at_floors_then_stops() -> None:
    # At the floors (2 experiences, 1 project) but still 3 bullets each: only now
    # does it shave a bullet — from the fattest entry — as a last resort.
    r = TailoredResume(
        experience=[ExperienceEntry(title=t, bullets=["1", "2", "3"]) for t in "AB"],
        projects=[ProjectEntry(name="P", bullets=["x", "y"])],
    )
    r1, n1 = trim_one_step(r)  # type: ignore[misc]
    assert "bullet" in n1  # whole-entry drops exhausted; now shaving
    assert (len(r1.experience), len(r1.projects)) == (2, 1)


def test_trim_reaches_bare_minimum_then_stops() -> None:
    # 2 single-bullet experiences + 1 single-bullet project: projects go, then
    # experiences down to 1, then nothing.
    r = TailoredResume(
        experience=[ExperienceEntry(title=t, bullets=["1"]) for t in "AB"],
        projects=[ProjectEntry(name="P", bullets=["x"])],
    )
    r1, n1 = trim_one_step(r)  # type: ignore[misc]
    assert n1.startswith("dropped project 'P'")
    r2, n2 = trim_one_step(r1)  # type: ignore[misc]
    assert n2.startswith("dropped experience 'B'")
    assert trim_one_step(r2) is None  # 1 experience, no projects — bare minimum


def test_compile_to_page_limit_without_toolchain_writes_tex(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # Force the no-toolchain path (deterministic regardless of whether the machine
    # running the tests has latexmk/pdflatex installed): it must write the .tex,
    # never trim, and report an unknown page count.
    import app.generation.latex as latex_mod

    monkeypatch.setattr(latex_mod, "has_latex_toolchain", lambda: False)
    r = _resume_for_trim()
    tex_path = tmp_path / "resume.tex"
    result = compile_to_page_limit(r, Candidate(full_name="X"), tex_path)
    assert tex_path.exists()
    assert result.pages is None  # unverifiable without compiling
    assert result.trims == []  # never trim blindly
    assert result.resume == r


def test_trim_drops_by_ranking_not_list_position() -> None:
    """A steered-up item is not cut just because it sits late in the list.

    Steering moves the scores in `ranking`; the entry lists are not guaranteed
    to be reordered to match, so trimming has to read the scores.
    """
    from app.generation.resume import RankedItem, trim_one_step

    resume = TailoredResume(
        experience=[
            ExperienceEntry(title="Barista", org="Cafe", bullets=["Made coffee"]),
            ExperienceEntry(title="Tutor", org="School", bullets=["Taught"]),
            # steered to the top, but last in the list
            ExperienceEntry(title="AI Engineer", org="RSAF", bullets=["Shipped ASR"]),
        ],
        projects=[],
        ranking=[
            RankedItem(kind="experience", label="AI Engineer @ RSAF", score=95,
                       included=True, rationale="steered up"),
            RankedItem(kind="experience", label="Tutor, School", score=40,
                       included=True, rationale="ok"),
            RankedItem(kind="experience", label="Barista at Cafe", score=10,
                       included=True, rationale="weak"),
        ],
    )

    trimmed, note = trim_one_step(resume, min_projects=0, min_experiences=2)
    titles = [e.title for e in trimmed.experience]
    assert "AI Engineer" in titles  # the steered item survives
    assert "Barista" not in titles  # the lowest-ranked one goes
    assert "rank 10" in note  # and the note says why
