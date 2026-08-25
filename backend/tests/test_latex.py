"""Deterministic tests for the LaTeX resume renderer (no LLM/network)."""

from __future__ import annotations

from app.generation.latex import _render_text, latex_escape, render_resume
from app.generation.resume import (
    EducationEntry,
    ExperienceEntry,
    ProjectEntry,
    SkillGroup,
    TailoredResume,
)
from app.profile.models import Candidate


def test_latex_escape_specials() -> None:
    assert latex_escape("a & b 50% #1 $x_y") == r"a \& b 50\% \#1 \$x\_y"


def test_bold_markers_after_escaping() -> None:
    # The percent inside the bold span must be escaped; the marker becomes \textbf.
    assert _render_text("improved by **15%** overall") == r"improved by \textbf{15\%} overall"


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


def test_empty_sections_are_dropped() -> None:
    tex = render_resume(TailoredResume(), Candidate(full_name="X"))
    assert r"\section{Education}" not in tex
    assert r"\section{Experience}" not in tex
    assert r"\begin{document}" in tex and r"\end{document}" in tex
