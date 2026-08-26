r"""Render a generated cover-letter into a self-contained LaTeX PDF.

A pdflatex look-alike of the Awesome-CV cover-letter template
(https://github.com/posquit0/Awesome-CV): the same visual language — a large
name with an accent-coloured surname, a compact contact line, an accent rule, a
right-aligned date, a recipient block, and a titled letter — but built with
standard ``pdflatex`` packages and system fonts, so it compiles with the exact
toolchain the resume already uses (``latexmk``/``pdflatex``). No vendored class
or fonts.

The letter body comes verbatim from ``generate_cover_letter`` (it already
carries its own salutation and sign-off), so this module only frames it; it does
not add or remove wording.
"""

from __future__ import annotations

from pathlib import Path

from app.generation.latex import compile_pdf, latex_escape
from app.listings.models import Listing
from app.profile.models import Candidate

# Awesome-CV's "awesome-emerald" accent, defined inline in the preamble below.
_PREAMBLE = r"""\documentclass[11pt,a4paper]{article}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage[left=1.4cm,right=1.4cm,top=1.6cm,bottom=1.6cm]{geometry}
\usepackage{xcolor}
\usepackage{helvet}
\usepackage[colorlinks=true]{hyperref}
\renewcommand{\familydefault}{\sfdefault}
\definecolor{awesome}{HTML}{00A388}
\hypersetup{urlcolor=awesome, linkcolor=awesome}
\setlength{\parindent}{0pt}
\setlength{\parskip}{0.7em}
\pagestyle{empty}
"""


def _contact_line(candidate: Candidate) -> str:
    """A single accented-separator contact line: phone · email · linkedin · …."""
    bits: list[str] = []
    if candidate.phone:
        bits.append(latex_escape(candidate.phone))
    if candidate.email:
        bits.append(f"\\href{{mailto:{candidate.email}}}{{{latex_escape(candidate.email)}}}")
    if candidate.linkedin_url:
        bits.append(f"\\href{{{candidate.linkedin_url}}}{{{_short(candidate.linkedin_url)}}}")
    if candidate.github_url:
        bits.append(f"\\href{{{candidate.github_url}}}{{{_short(candidate.github_url)}}}")
    if candidate.portfolio_url:
        bits.append(f"\\href{{{candidate.portfolio_url}}}{{{_short(candidate.portfolio_url)}}}")
    sep = r" \quad{\color{awesome}\textbullet}\quad "
    return sep.join(bits)


def _short(url: str) -> str:
    import re

    return latex_escape(re.sub(r"^https?://(www\.)?", "", url).rstrip("/"))


def _name_block(candidate: Candidate) -> str:
    name = (candidate.full_name or "Candidate").strip()
    parts = name.split()
    if len(parts) > 1:
        first, last = " ".join(parts[:-1]), parts[-1]
        heading = f"{{\\Huge {latex_escape(first)} {{\\color{{awesome}}{latex_escape(last)}}}}}"
    else:
        heading = f"{{\\Huge {latex_escape(name)}}}"
    return heading


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
            f"\\noindent{{\\large\\bfseries\\color{{awesome}} Application for {latex_escape(role)}"
            f"{f' at {company}' if company else ''}}}\\par\\vspace{{0.6em}}\n\n"
        )

    # Each block opens with \noindent so the leading \\ / \hfill are always in
    # horizontal mode (avoids "no line here to end"); \par closes the paragraph.
    header = (
        f"\\noindent{_name_block(candidate)}\\\\[4pt]\n"
        f"{{\\small {_contact_line(candidate)}}}\\par\n"
        f"\\vspace{{0.4em}}\n"
        f"\\noindent{{\\color{{awesome}}\\rule{{\\linewidth}}{{1.1pt}}}}\\par\n"
        f"\\vspace{{0.3em}}\n"
        f"\\noindent\\hfill \\today\\par\\vspace{{0.6em}}\n\n"
    )
    recipient_block = f"\\noindent {recipient}\\par\\vspace{{0.6em}}\n\n" if recipient else ""

    return (
        f"{_PREAMBLE}\n"
        "\\begin{document}\n\n"
        f"{header}"
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
