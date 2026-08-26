"""LinkedIn data-export ingestion (the user's own export, not scraping).

A LinkedIn export is a ZIP of CSVs. It's structured, so we parse it
deterministically — no LLM — which is what preserves the exact month/year dates
that resumes and the master doc lack. Each file maps to a known experience kind.
The entries flow into the same experience bank and get merged with the richer
resume/master-doc versions during consolidation, contributing their precise dates.
"""

from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path

from app.ingestion.schema import ExtractedContact, ExtractedExperience, ExtractedSkill
from app.profile.models import ExperienceKind

Row = dict[str, str]
Tables = dict[str, list[Row]]


def read_linkedin_tables(path: str | Path) -> Tables:
    """Read a LinkedIn export (``.zip`` or a directory of CSVs) into tables
    keyed by lowercased file stem (e.g. ``"positions"``)."""
    p = Path(path)
    tables: Tables = {}
    if p.is_dir():
        for f in sorted(p.glob("*.csv")):
            tables[f.stem.lower()] = _read_csv(f.read_text(encoding="utf-8-sig"))
    elif zipfile.is_zipfile(p):
        with zipfile.ZipFile(p) as z:
            for name in z.namelist():
                if name.lower().endswith(".csv"):
                    stem = Path(name).stem.lower()
                    tables[stem] = _read_csv(z.read(name).decode("utf-8-sig", errors="replace"))
    else:
        raise ValueError(f"LinkedIn export must be a .zip or a directory of CSVs: {p}")
    return tables


def _read_csv(text: str) -> list[Row]:
    return list(csv.DictReader(io.StringIO(text)))


def _col(row: Row, *names: str) -> str | None:
    """Fetch a column value case-insensitively by any of the given names."""
    lower = {k.lower().strip(): (v or "") for k, v in row.items() if k}
    for name in names:
        value = lower.get(name.lower())
        if value and value.strip():
            return value.strip()
    return None


def build_linkedin_extraction(
    tables: Tables,
) -> tuple[ExtractedContact | None, list[ExtractedExperience], list[ExtractedSkill], str | None]:
    """Turn LinkedIn tables into extraction objects (pure — easy to test).

    Returns (contact, experiences, skills, about_text). ``about_text`` is the
    profile summary, kept as a writing sample for voice.
    """
    experiences: list[ExtractedExperience] = []

    for r in tables.get("positions", []):
        experiences.append(
            ExtractedExperience(
                kind=ExperienceKind.WORK,
                org=_col(r, "Company Name"),
                title=_col(r, "Title"),
                location=_col(r, "Location"),
                start=_col(r, "Started On"),
                end=_col(r, "Finished On"),
                is_current=_col(r, "Finished On") is None,
                detail=_col(r, "Description"),
            )
        )

    for r in tables.get("education", []):
        notes = " ".join(p for p in (_col(r, "Notes"), _col(r, "Activities")) if p)
        experiences.append(
            ExtractedExperience(
                kind=ExperienceKind.EDUCATION,
                org=_col(r, "School Name"),
                title=_col(r, "Degree Name", "Degree"),
                start=_col(r, "Start Date"),
                end=_col(r, "End Date"),
                detail=notes or None,
            )
        )

    for r in tables.get("projects", []):
        experiences.append(
            ExtractedExperience(
                kind=ExperienceKind.PROJECT,
                title=_col(r, "Title"),
                start=_col(r, "Started On"),
                end=_col(r, "Finished On"),
                detail=_col(r, "Description"),
            )
        )

    for r in tables.get("honors", []):
        experiences.append(
            ExtractedExperience(
                kind=ExperienceKind.AWARD,
                title=_col(r, "Title"),
                start=_col(r, "Issued On"),
                detail=_col(r, "Description"),
            )
        )

    skills = [
        ExtractedSkill(name=name)
        for r in tables.get("skills", [])
        if (name := _col(r, "Name"))
    ]

    contact, about = _profile_contact(tables.get("profile", []))
    return contact, experiences, skills, about


def _profile_contact(rows: list[Row]) -> tuple[ExtractedContact | None, str | None]:
    if not rows:
        return None, None
    r = rows[0]
    name = " ".join(p for p in (_col(r, "First Name"), _col(r, "Last Name")) if p)
    contact = ExtractedContact(
        full_name=name or None,
        location=_col(r, "Geo Location", "Location"),
    )
    return contact, _col(r, "Summary")


def raw_text_from_tables(tables: Tables) -> str:
    """A readable dump of the export, retained verbatim in source_documents."""
    parts: list[str] = []
    for name, rows in tables.items():
        parts.append(f"## {name} ({len(rows)} rows)")
        for row in rows:
            fields = [f"{k}: {v}" for k, v in row.items() if k and v and str(v).strip()]
            if fields:
                parts.append(" | ".join(fields))
    return "\n".join(parts)


def linkedin_summary(tables: Tables) -> dict[str, int]:
    """Row counts per relevant table, for reporting."""
    return {
        key: len(tables.get(key, []))
        for key in ("positions", "education", "projects", "honors", "skills")
    }
