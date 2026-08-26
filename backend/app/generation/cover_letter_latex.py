r"""Render a generated cover-letter into a self-contained LaTeX PDF.

Matches the resume's template (jakegut/resume): the same Charter serif font and
the same centred, small-caps name + ``$|$``-separated contact header, with no
colour, so the resume and cover letter read as one set. Compiles with the same
``latexmk``/``pdflatex`` toolchain as the resume; no vendored class or fonts.

The letter body comes verbatim from ``generate_cover_letter`` (it already
carries its own salutation and sign-off), so this module only frames it; it does
not add or remove wording.
"""

from __future__ import annotations

from pathlib import Path

from app.generation.latex import _render_header, compile_pdf, latex_escape
from app.listings.models import Listing
from app.profile.models import Candidate

# Same font/links setup as the resume template, minus the resume-specific
# section macros and the tight full-page margins (a letter wants normal ones).
_PREAMBLE = r"""\documentclass[letterpaper,11pt]{article}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage[margin=1in]{geometry}
\usepackage{charter}
\usepackage[hidelinks]{hyperref}
\urlstyle{same}
\setlength{\parindent}{0pt}
\setlength{\parskip}{0.7em}
\pagestyle{empty}
"""


def _body_paragraphs(body: str) -> str:
    r"""Split the letter on blank lines into paragraphs; within a paragraph,
    preserve single newlines as line breaks (so the "Best wishes, / En Hao Tew"
    sign-off keeps its two lines)."""
    out: list[str] = []
    for block in body.strip().split("\n\n"):
        lines = [latex_escape(line.strip()) for line in block.splitlines() if line.strip()]
        if lines:
            out.append(" \\\\\n".join(lines))
    return "\n\n".join(out)


def render_cover_letter(body: str, candidate: Candidate, listing: Listing | None) -> str:
    """Render the full cover-letter ``.tex`` document string."""
    company = latex_escape(listing.company) if listing and listing.company else ""
    location = latex_escape(listing.location) if listing and listing.location else ""
    role = listing.role_title if listing and listing.role_title else None

    recipient_lines = [x for x in (company, location) if x]
    recipient = " \\\\\n".join(recipient_lines)

    title = ""
    if role:
        title = (
            f"\\noindent\\textbf{{Application for {latex_escape(role)}"
            f"{f' at {company}' if company else ''}}}\\par\\vspace{{0.8em}}\n\n"
        )

    # The centred, small-caps name + contact header is shared with the resume.
    header = f"{_render_header(candidate)}\n\n\\vspace{{1.2em}}\n\n"
    date_block = "\\noindent\\hfill \\today\\par\\vspace{0.8em}\n\n"
    recipient_block = f"\\noindent {recipient}\\par\\vspace{{0.8em}}\n\n" if recipient else ""

    return (
        f"{_PREAMBLE}\n"
        "\\begin{document}\n\n"
        f"{header}"
        f"{date_block}"
        f"{recipient_block}"
        f"{title}"
        f"{_body_paragraphs(body)}\n\n"
        "\\end{document}\n"
    )


def compile_cover_letter(
    body: str, candidate: Candidate, listing: Listing | None, tex_path: Path
) -> tuple[str, Path | None]:
    """Render + write the ``.tex`` and compile a PDF if a toolchain exists.

    Returns ``(tex_source, pdf_path_or_None)``. The ``.tex`` is always written so
    it is usable on its own even without a LaTeX toolchain.
    """
    tex_path = Path(tex_path)
    tex = render_cover_letter(body, candidate, listing)
    tex_path.write_text(tex)
    return tex, compile_pdf(tex_path)
