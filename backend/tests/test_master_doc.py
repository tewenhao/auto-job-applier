"""Tests for writing new entries into the master-doc (no LLM/network)."""

from __future__ import annotations

from app.profile.master_doc import append_entry, find_section_span

DOC = """# master document on X

## motivations/goals

why i do things

## experience

### Old Role — Org, Singapore. Jan 2025 - Feb 2025

**FACTS:**
- did things

## current/previous projects

### a project

## education

### Uni
"""

ENTRY = "### New Role — NewOrg, London. Mar 2026 - Present\n\n**FACTS:**\n- new things"


def test_appends_to_the_end_of_the_named_section() -> None:
    out = append_entry(DOC, "experience", ENTRY)
    # lands inside experience, after the existing entry, before the next H2
    assert out.index("New Role") > out.index("Old Role")
    assert out.index("New Role") < out.index("## current/previous projects")
    assert "did things" in out  # existing content untouched


def test_section_aliases_match_the_real_headings() -> None:
    # "projects" must find "## current/previous projects"
    assert find_section_span(DOC, "projects") is not None
    out = append_entry(DOC, "projects", "### another project")
    assert out.index("another project") < out.index("## education")


def test_missing_section_is_created_at_the_end() -> None:
    out = append_entry(DOC, "awards", "### 2nd place, Some Hackathon, 2026")
    assert out.rstrip().endswith("### 2nd place, Some Hackathon, 2026")
    assert "## awards" in out


def test_existing_entries_are_never_disturbed() -> None:
    out = append_entry(DOC, "experience", ENTRY)
    for line in ("## motivations/goals", "why i do things", "### a project", "### Uni"):
        assert line in out
