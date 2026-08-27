"""Writing new entries into the master-doc.

The master-doc is the human source of truth; the database is built from it. So
a new experience captured in the dashboard is written *into the doc* and then
re-ingested, rather than inserted straight into the database — otherwise the
two drift, and `ajp ingest --fresh` (which clears experiences first) would wipe
anything that only ever existed in the database.
"""

from __future__ import annotations

import re
from pathlib import Path

# The H2 sections a drafted entry can belong to, and how they are titled in the
# doc. Matching is loose (case-insensitive substring) so "projects" finds
# "## current/previous projects".
SECTION_ALIASES: dict[str, tuple[str, ...]] = {
    "experience": ("experience",),
    "projects": ("project",),
    "education": ("education",),
    "awards": ("achievement", "award"),
    "volunteering": ("volunteer",),
    "hobbies": ("hobb",),
}

_H2 = re.compile(r"^##\s+(.*)$", re.M)


def find_section_span(text: str, section: str) -> tuple[int, int] | None:
    """Character span of an H2 section's body, or None if it isn't there.

    The span starts after the heading line and ends at the next H2 (or EOF), so
    an entry appended at ``end`` lands inside the right section.
    """
    wanted = SECTION_ALIASES.get(section.lower(), (section.lower(),))
    matches = list(_H2.finditer(text))
    for i, m in enumerate(matches):
        title = m.group(1).strip().lower()
        if any(alias in title for alias in wanted):
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            return start, end
    return None


def append_entry(text: str, section: str, entry: str) -> str:
    """Return ``text`` with ``entry`` appended to the end of ``section``.

    A section that doesn't exist yet is created at the end of the document.
    """
    entry = entry.strip("\n")
    span = find_section_span(text, section)
    if span is None:
        heading = section.strip().lower()
        return f"{text.rstrip()}\n\n## {heading}\n\n{entry}\n"
    _, end = span
    body = text[:end].rstrip()
    rest = text[end:].lstrip("\n")
    return f"{body}\n\n{entry}\n\n{rest}".rstrip() + "\n"


def append_entry_to_file(path: str | Path, section: str, entry: str) -> Path:
    """Write the entry into the master-doc on disk, keeping a .bak of the
    previous version — this edits the user's own source of truth."""
    p = Path(path)
    original = p.read_text(encoding="utf-8")
    p.with_suffix(p.suffix + ".bak").write_text(original, encoding="utf-8")
    p.write_text(append_entry(original, section, entry), encoding="utf-8")
    return p
