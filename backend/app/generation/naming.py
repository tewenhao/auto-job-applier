"""Names for the generated documents.

A recruiter (or a folder of downloads) should be able to tell whose CV this is
and which firm it was written for, so the default is
``<candidate>-<company>-<kind>`` — e.g. ``en-hao-tew-citadel-resume.pdf``.

``override`` exists for Module 5 (ATS form auto-fill): some upload fields
require a specific filename, and that requirement wins over our convention.
"""

from __future__ import annotations

import re

RESUME = "resume"
COVER_LETTER = "cover_letter"


def slugify(text: str | None, fallback: str = "") -> str:
    """Lowercase, hyphen-separated, filesystem- and URL-safe."""
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug or fallback


def document_stem(
    *, candidate_name: str | None, company: str | None, kind: str = RESUME
) -> str:
    """``<candidate>-<company>-<kind>``, skipping any part we don't know."""
    parts = [
        slugify(candidate_name),
        slugify(company),
        slugify(kind, fallback=RESUME),
    ]
    return "-".join(p for p in parts if p)


def document_filename(
    *,
    candidate_name: str | None,
    company: str | None,
    kind: str = RESUME,
    ext: str = "pdf",
    override: str | None = None,
) -> str:
    """The filename to hand a download or an upload field.

    ``override`` (a name an ATS demands) is used as-is apart from ensuring the
    extension, so form requirements take precedence over our convention.
    """
    ext = ext.lstrip(".")
    if override:
        stem = override[: -(len(ext) + 1)] if override.lower().endswith(f".{ext}") else override
        return f"{slugify(stem, fallback='document')}.{ext}"
    return f"{document_stem(candidate_name=candidate_name, company=company, kind=kind)}.{ext}"
