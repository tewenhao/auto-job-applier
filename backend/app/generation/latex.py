r"""Render a ``TailoredResume`` into the candidate's LaTeX resume template
(jakegut/resume, https://github.com/jakegut/resume) and optionally compile a PDF.

The preamble and custom macros are kept verbatim from the candidate's own
``.tex``; only the header (name/contacts) is parametrised. Each section emits the
template's macros with the correct per-section slot mapping:

    Education  \resumeSubheading{school}{location}{degree}{dates}
    Experience \resumeSubheading{title}{date}{org}{location}
    Projects   \resumeProjectHeading{\textbf{name} $|$ \emph{tools}}{dates}
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from app.generation.resume import (
    EducationEntry,
    ExperienceEntry,
    ProjectEntry,
    TailoredResume,
    trim_one_step,
)
from app.profile.models import Candidate

# Preamble + custom commands, verbatim from the candidate's template. Ends just
# before \begin{document}; the body (header + sections) is appended after it.
_PREAMBLE = r"""%-------------------------
% Resume in Latex
% Based off of: https://github.com/jakegut/resume
% License : MIT
%------------------------

\documentclass[letterpaper,10pt]{article}

\usepackage{latexsym}
\usepackage[empty]{fullpage}
\usepackage{titlesec}
\usepackage{marvosym}
\usepackage[usenames,dvipsnames]{color}
\usepackage{verbatim}
\usepackage{enumitem}
\usepackage[hidelinks]{hyperref}
\usepackage{fancyhdr}
\usepackage[english]{babel}
\usepackage{tabularx}
\input{glyphtounicode}

\usepackage{charter}

\pagestyle{fancy}
\fancyhf{}
\fancyfoot{}
\renewcommand{\headrulewidth}{0pt}
\renewcommand{\footrulewidth}{0pt}

\addtolength{\oddsidemargin}{-0.5in}
\addtolength{\evensidemargin}{-0.5in}
\addtolength{\textwidth}{1in}
\addtolength{\topmargin}{-.5in}
\addtolength{\textheight}{1.0in}

\urlstyle{same}

\raggedbottom
\raggedright
\setlength{\tabcolsep}{0in}

% A ragged-right flexible column. Plain `X` justifies, which stretches the word
% spacing of a wrapped heading and looks nothing like the rest of the document
% (\raggedright above); the headings use this instead.
\newcolumntype{L}{>{\raggedright\arraybackslash}X}

\titleformat{\section}{
  \vspace{-4pt}\scshape\raggedright\large
}{}{0em}{}[\color{black}\titlerule \vspace{-5pt}]

\pdfgentounicode=1

\newcommand{\resumeItem}[1]{
  \item\small{
    {#1 \vspace{-2pt}}
  }
}

% The left column is an `L` (wrapping) column, not `l`. An `l` column is a
% single unbreakable line, so a long project name plus its tool list ran off the
% right edge of the page instead of wrapping — LaTeX reports it as an overfull
% \hbox and prints it anyway. `L` takes whatever width the dates leave and wraps
% within it; the 1em gap keeps a wrapped heading off the dates.
\newcommand{\resumeSubheading}[4]{
  \vspace{-2pt}\item
    \begin{tabularx}{0.97\textwidth}[t]{@{}L@{\hspace{1em}}r@{}}
      \textbf{#1} & #2 \\
      \textit{\small#3} & \textit{\small #4} \\
    \end{tabularx}\vspace{-7pt}
}

\newcommand{\resumeSubSubheading}[2]{
    \item
    \begin{tabularx}{0.97\textwidth}[t]{@{}L@{\hspace{1em}}r@{}}
      \textit{\small#1} & \textit{\small #2} \\
    \end{tabularx}\vspace{-7pt}
}

\newcommand{\resumeProjectHeading}[2]{
    \item
    \begin{tabularx}{0.97\textwidth}[t]{@{}L@{\hspace{1em}}r@{}}
      \small#1 & #2 \\
    \end{tabularx}\vspace{-7pt}
}

\newcommand{\resumeSubItem}[1]{\resumeItem{#1}\vspace{-4pt}}

\renewcommand\labelitemii{$\vcenter{\hbox{\tiny$\bullet$}}$}

\newcommand{\resumeSubHeadingListStart}{\begin{itemize}[leftmargin=0.15in, label={}]}
\newcommand{\resumeSubHeadingListEnd}{\end{itemize}}
\newcommand{\resumeItemListStart}{\begin{itemize}}
\newcommand{\resumeItemListEnd}{\end{itemize}\vspace{-5pt}}
"""

# LaTeX special characters that must be escaped in body text (order matters:
# backslash first so we don't double-escape the replacements).
_ESCAPES: tuple[tuple[str, str], ...] = (
    ("\\", r"\textbackslash{}"),
    ("&", r"\&"),
    ("%", r"\%"),
    ("$", r"\$"),
    ("#", r"\#"),
    ("_", r"\_"),
    ("{", r"\{"),
    ("}", r"\}"),
    ("~", r"\textasciitilde{}"),
    ("^", r"\textasciicircum{}"),
)

_BOLD = re.compile(r"\*\*(.+?)\*\*")
# A tilde that means "approximately" (precedes a number) should render as the
# math tilde $\sim$, not the upright \textasciitilde. Protect it through escaping
# with a sentinel that contains no LaTeX specials.
_APPROX_TILDE = re.compile(r"~(?=\s*\d)")
_SIM_SENTINEL = "\x00SIM\x00"


def latex_escape(text: str) -> str:
    """Escape LaTeX specials in plain body text."""
    for ch, rep in _ESCAPES:
        text = text.replace(ch, rep)
    return text


def _render_text(text: str) -> str:
    """Escape a bullet, then turn ``**bold**`` markers into ``\\textbf{}``.

    Escape first (the marker asterisks survive it), so any specials inside the
    bolded span are escaped too. An "approximately" tilde (``~`` before a number)
    becomes ``$\\sim$``; any other ``~`` stays a literal tilde.
    """
    text = _APPROX_TILDE.sub(_SIM_SENTINEL, text)
    text = latex_escape(text).replace(_SIM_SENTINEL, r"$\sim$")
    return _BOLD.sub(r"\\textbf{\1}", text)


def _items(bullets: list[str]) -> str:
    if not bullets:
        return ""
    lines = "\n".join(f"        \\resumeItem{{{_render_text(b)}}}" for b in bullets)
    return "\n      \\resumeItemListStart\n" + lines + "\n      \\resumeItemListEnd"


def _render_header(candidate: Candidate) -> str:
    name = candidate.full_name or "Candidate"
    bits: list[str] = []
    if candidate.phone:
        bits.append(latex_escape(candidate.phone))
    if candidate.email:
        bits.append(
            f"\\href{{mailto:{candidate.email}}}{{\\underline{{{latex_escape(candidate.email)}}}}}"
        )
    if candidate.linkedin_url:
        bits.append(
            f"\\href{{{candidate.linkedin_url}}}{{\\underline{{{_display_url(candidate.linkedin_url)}}}}}"
        )
    if candidate.github_url:
        bits.append(
            f"\\href{{{candidate.github_url}}}{{\\underline{{{_display_url(candidate.github_url)}}}}}"
        )
    contact = " $|$\n    ".join(bits)
    return (
        "\\begin{center}\n"
        f"    \\textbf{{\\Huge \\scshape {latex_escape(name)}}} \\\\ \\vspace{{1pt}}\n"
        f"    \\small {contact}\n"
        "\\end{center}"
    )


def _display_url(url: str) -> str:
    """Strip scheme/www for a compact clickable label."""
    label = re.sub(r"^https?://(www\.)?", "", url).rstrip("/")
    return latex_escape(label)


def _render_education(entries: list[EducationEntry]) -> str:
    if not entries:
        return ""
    blocks = []
    for e in entries:
        sub = (
            "    \\resumeSubheading\n"
            f"      {{{_render_text(e.school)}}}{{{_render_text(e.location)}}}\n"
            f"      {{{_render_text(e.degree)}}}{{{_render_text(e.dates)}}}"
        )
        blocks.append(sub + _items(e.bullets))
    body = "\n".join(blocks)
    return (
        "%-----------EDUCATION-----------\n"
        "\\section{Education}\n"
        "  \\resumeSubHeadingListStart\n"
        f"{body}\n"
        "  \\resumeSubHeadingListEnd"
    )


def _end_date_key(end_date: str) -> tuple[int, int]:
    """Reverse-chronological sort key from an ``end_date`` (newest first).

    Ongoing ('present'/'current'/blank) sorts newest; a parseable 'YYYY-MM' or
    'YYYY' sorts by (year, month); anything unparseable sorts oldest.
    """
    raw = (end_date or "").strip().lower()
    if raw in {"present", "current", "ongoing", "now", ""}:
        return (9999, 13)
    m = re.match(r"(\d{4})(?:-(\d{1,2}))?", raw)
    if not m:
        return (0, 0)
    return (int(m.group(1)), int(m.group(2)) if m.group(2) else 12)


def _render_experience(entries: list[ExperienceEntry]) -> str:
    if not entries:
        return ""
    # Display reverse-chronologically; the input order (relevance) is preserved
    # upstream for selection/trimming, so this only affects presentation.
    entries = sorted(entries, key=lambda e: _end_date_key(e.end_date), reverse=True)
    blocks = []
    for e in entries:
        sub = (
            "    \\resumeSubheading\n"
            f"      {{{_render_text(e.title)}}}{{{_render_text(e.dates)}}}\n"
            f"      {{{_render_text(e.org)}}}{{{_render_text(e.location)}}}"
        )
        blocks.append(sub + _items(e.bullets))
    body = "\n\n".join(blocks)
    return (
        "%-----------EXPERIENCE-----------\n"
        "\\section{Experience}\n"
        "  \\resumeSubHeadingListStart\n\n"
        f"{body}\n"
        "  \\resumeSubHeadingListEnd"
    )


def _render_projects(entries: list[ProjectEntry], title: str) -> str:
    if not entries:
        return ""
    # Display reverse-chronologically, like experience; input order (relevance)
    # is preserved upstream for selection/trimming.
    entries = sorted(entries, key=lambda p: _end_date_key(p.end_date), reverse=True)
    blocks = []
    for p in entries:
        heading_left = f"\\textbf{{{_render_text(p.name)}}}"
        if p.tools:
            heading_left += f" $|$ \\emph{{{_render_text(p.tools)}}}"
        head = (
            f"    \\resumeProjectHeading\n          {{{heading_left}}}{{{_render_text(p.dates)}}}"
        )
        blocks.append(head + _items(p.bullets))
    body = "\n\n".join(blocks)
    return (
        "%-----------PROJECTS-----------\n"
        f"\\section{{{latex_escape(title)}}}\n"
        "  \\resumeSubHeadingListStart\n\n"
        f"{body}\n"
        "  \\resumeSubHeadingListEnd"
    )


def _render_skills(groups: list) -> str:  # type: ignore[type-arg]
    if not groups:
        return ""
    lines = " \\\\\n".join(
        f"     \\textbf{{{_render_text(g.label)}}}{{: {_render_text(g.items)}}}" for g in groups
    )
    return (
        "%-----------SKILLS-----------\n"
        "\\section{Skills \\& Hobbies}\n"
        " \\begin{itemize}[leftmargin=0.15in, label={}]\n"
        "    \\small{\\item{\n"
        f"{lines}\n"
        "    }}\n"
        " \\end{itemize}"
    )


def render_resume(resume: TailoredResume, candidate: Candidate) -> str:
    """Render the full ``.tex`` document string."""
    sections = [
        _render_education(resume.education),
        _render_experience(resume.experience),
        _render_projects(resume.projects, resume.projects_title),
        _render_skills(resume.skills),
    ]
    body = "\n\n\n".join(s for s in sections if s)
    return (
        f"{_PREAMBLE}\n"
        "\\begin{document}\n\n"
        f"{_render_header(candidate)}\n\n\n"
        f"{body}\n\n"
        "\\end{document}\n"
    )


def compile_pdf(tex_path: Path) -> Path | None:
    """Compile ``tex_path`` to a PDF if a LaTeX toolchain is available.

    Returns the PDF path on success, or ``None`` if no toolchain is present or
    compilation fails (the ``.tex`` is always usable on its own).
    """
    tex_path = Path(tex_path)
    engine = shutil.which("latexmk") or shutil.which("pdflatex")
    if engine is None:
        return None
    if engine.endswith("latexmk"):
        cmd = [engine, "-pdf", "-interaction=nonstopmode", "-halt-on-error", tex_path.name]
    else:
        cmd = [engine, "-interaction=nonstopmode", "-halt-on-error", tex_path.name]
    try:
        subprocess.run(cmd, cwd=tex_path.parent, capture_output=True, timeout=120, check=True)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    pdf = tex_path.with_suffix(".pdf")
    return pdf if pdf.exists() else None


def has_latex_toolchain() -> bool:
    """Whether a LaTeX engine is available to compile PDFs."""
    return bool(shutil.which("latexmk") or shutil.which("pdflatex"))


def page_count(pdf_path: Path) -> int | None:
    """Number of pages in a PDF, or ``None`` if it can't be read."""
    try:
        from pypdf import PdfReader

        return len(PdfReader(str(pdf_path)).pages)
    except Exception:  # noqa: BLE001 - a broken/locked PDF should not crash generation
        return None


@dataclass
class OnePageResult:
    """Outcome of rendering a resume to a page limit."""

    resume: TailoredResume  # possibly trimmed to fit
    tex: str  # the final rendered .tex (matches ``resume``)
    pdf_path: Path | None  # compiled PDF, or None (no toolchain / compile failed)
    pages: int | None  # final page count, or None if not compiled/countable
    trims: list[str] = field(default_factory=list)  # what was removed, in order
    within_limit: bool = False  # True iff compiled and pages <= max_pages


def compile_to_page_limit(
    resume: TailoredResume,
    candidate: Candidate,
    tex_path: Path,
    *,
    max_pages: int = 1,
    max_iterations: int = 20,
) -> OnePageResult:
    """Render ``resume``, compile, and trim-and-recompile until it fits within
    ``max_pages`` (or nothing more can be trimmed).

    Always writes the final ``.tex`` to ``tex_path``. If no LaTeX toolchain is
    present, writes the untrimmed ``.tex`` and returns with ``pages=None`` — page
    count can't be verified without compiling, so no trimming is attempted.
    """
    tex_path = Path(tex_path)

    def _write(r: TailoredResume) -> str:
        tex = render_resume(r, candidate)
        tex_path.write_text(tex)
        return tex

    current = resume
    tex = _write(current)

    if not has_latex_toolchain():
        return OnePageResult(resume=current, tex=tex, pdf_path=None, pages=None)

    trims: list[str] = []
    for _ in range(max_iterations):
        pdf = compile_pdf(tex_path)
        pages = page_count(pdf) if pdf else None

        # Compile failed or page count unreadable: stop, don't trim blindly.
        if pages is None:
            return OnePageResult(current, tex, pdf, None, trims, within_limit=False)
        if pages <= max_pages:
            return OnePageResult(current, tex, pdf, pages, trims, within_limit=True)

        step = trim_one_step(current)
        if step is None:  # at the content floor and still over — hand back best effort
            return OnePageResult(current, tex, pdf, pages, trims, within_limit=False)
        current, note = step
        trims.append(note)
        tex = _write(current)

    # Ran out of iterations; report the last compiled state.
    pdf = compile_pdf(tex_path)
    pages = page_count(pdf) if pdf else None
    return OnePageResult(
        current, tex, pdf, pages, trims, within_limit=bool(pages and pages <= max_pages)
    )
