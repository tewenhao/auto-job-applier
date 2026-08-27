"""LLM-based structured extraction of profile content from raw document text."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor

from app.config import Task
from app.ingestion.schema import ProfileExtraction
from app.llm import LLMClient
from app.profile.models import SourceType

# The master doc is the "superset" input: preserve detail rather than compressing.
_DETAIL_GUIDANCE = {
    SourceType.RESUME: (
        "This is a concise resume. Extract each role/project/education/award as an "
        "experience with a tight summary. Only fill 'detail' if the resume itself "
        "gives more than a one-line description — do not invent elaboration."
    ),
    SourceType.MASTER_DOC: (
        "This is a free-form 'master document' where the candidate elaborates on "
        "everything they've done, beyond what fits on a resume. Capture the full "
        "richness: put the long-form narrative in 'detail' and a tight version in "
        "'summary'. Prefer more detail over less; do not compress it away."
    ),
}

_SYSTEM = (
    "You extract structured career data from documents. Be faithful to the source: "
    "never invent organizations, titles, dates, or achievements that aren't stated "
    "or clearly implied. Leave a field null when the source doesn't provide it. "
    "Classify each experience's kind accurately. Normalize dates to ISO where "
    "possible ('2025', '2025-06', or '2025-06-01'); use null if absent.\n\n"
    "Separate content from guidance. Put factual descriptions and authentic voice "
    "into 'detail'. Any instruction about how to USE or NOT use the material — "
    "phrases like 'PRIVATE', 'do not surface', 'don't claim', 'don't inflate', "
    "'frame carefully', audience-specific framing, or things to avoid saying — must "
    "go into 'handling_notes' as separate items, NOT into detail/summary. "
    "handling_notes are constraints for later writing; they must never leak into a "
    "resume or cover letter."
)


# Above this many characters a document is extracted section by section. One
# call cannot emit structured output for a long master-doc: the model quietly
# returns a subset (in practice only the first section), so entries go missing.
CHUNK_OVER_CHARS = 12000
# Concurrent section extractions. Enough to keep ingest brisk, low enough to
# stay clear of rate limits.
MAX_PARALLEL_SECTIONS = 4

_H2 = re.compile(r"^##\s+.*$", re.M)


def split_sections(text: str) -> list[str]:
    """Split a document into its ``##`` sections, each keeping its heading.

    Anything before the first ``##`` (title, preamble) leads the first chunk.
    """
    heads = list(_H2.finditer(text))
    if not heads:
        return [text]
    chunks = []
    preamble = text[: heads[0].start()].strip()
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        chunk = text[h.start() : end].strip()
        if i == 0 and preamble:
            chunk = f"{preamble}\n\n{chunk}"
        chunks.append(chunk)
    return chunks


def _extract_one(llm: LLMClient, text: str, guidance: str) -> ProfileExtraction:
    return llm.parse(
        task=Task.PARSE,
        system=_SYSTEM,
        messages=[{"role": "user", "content": f"{guidance}\n\n--- DOCUMENT ---\n{text}"}],
        output_format=ProfileExtraction,
    )


def merge_extractions(parts: list[ProfileExtraction]) -> ProfileExtraction:
    """Combine per-section extractions: keep every experience, de-duplicate
    skills by name, and take the first contact block found."""
    merged = ProfileExtraction()
    seen_skills: set[str] = set()
    for part in parts:
        if merged.contact is None and part.contact is not None:
            merged.contact = part.contact
        merged.experiences.extend(part.experiences)
        for skill in part.skills:
            key = (skill.name or "").strip().lower()
            if key and key not in seen_skills:
                seen_skills.add(key)
                merged.skills.append(skill)
    return merged


def extract_profile(llm: LLMClient, text: str, source_type: SourceType) -> ProfileExtraction:
    """Extract contact, experiences, and skills from one document's text.

    A long document is extracted one ``##`` section at a time and merged, so
    every section is covered instead of the model silently dropping most of
    them to fit a single response.
    """
    guidance = _DETAIL_GUIDANCE.get(source_type, "Extract experiences and skills faithfully.")
    sections = split_sections(text) if len(text) > CHUNK_OVER_CHARS else [text]
    if len(sections) == 1:
        return _extract_one(llm, sections[0], guidance)
    # The sections are independent, so extract them concurrently — sequentially
    # this turns one slow call into many and makes ingest painful.
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_SECTIONS) as pool:
        parts = list(pool.map(lambda sec: _extract_one(llm, sec, guidance), sections))
    return merge_extractions(parts)
