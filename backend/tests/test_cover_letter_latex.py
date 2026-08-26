"""Tests for the pdflatex cover-letter renderer (no toolchain needed)."""

from __future__ import annotations

from uuid import uuid4

from app.generation.cover_letter_latex import render_cover_letter
from app.listings.models import Listing, ListingSource
from app.profile.models import Candidate

CID = uuid4()


def _candidate() -> Candidate:
    return Candidate(
        id=CID,
        full_name="En Hao Tew",
        email="enhaotew@gmail.com",
        linkedin_url="https://linkedin.com/in/enhaotew",
    )


def _listing() -> Listing:
    return Listing(
        id=uuid4(),
        candidate_id=CID,
        source=ListingSource.MANUAL,
        company="Citadel",
        role_title="Quant Intern",
        location="London, UK",
    )


def test_renders_header_recipient_and_title() -> None:
    body = "Dear team,\n\nHi.\n\nBest wishes,\nEn Hao Tew"
    tex = render_cover_letter(body, _candidate(), _listing())
    assert tex.startswith("\\documentclass")
    assert "\\begin{document}" in tex and "\\end{document}" in tex
    # shares the resume's Charter font and small-caps header, with no colour
    assert "\\usepackage{charter}" in tex
    assert "\\scshape En Hao Tew" in tex
    assert "color" not in tex
    # recipient + title from the listing
    assert "Citadel" in tex
    assert "Application for Quant Intern at Citadel" in tex
    # email hyperlink
    assert "\\href{mailto:enhaotew@gmail.com}" in tex


def test_escapes_specials_and_keeps_signoff_linebreak() -> None:
    body = "Dear team,\n\nI improved it 50% & shipped #1.\n\nBest wishes,\nEn Hao Tew"
    tex = render_cover_letter(body, _candidate(), _listing())
    assert "50\\% \\& shipped \\#1" in tex
    # the sign-off's internal newline becomes a LaTeX line break
    assert "Best wishes, \\\\\nEn Hao Tew" in tex


def test_no_listing_and_single_name() -> None:
    cand = Candidate(id=CID, full_name="Madonna", email="m@x.com")
    tex = render_cover_letter("Dear team,\n\nHi.", cand, None)
    # no listing -> no title/recipient; name still in the shared header
    assert "\\scshape Madonna" in tex
    assert "Application for" not in tex
