"""LLM-based structured extraction of profile content from raw document text."""

from __future__ import annotations

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
    "possible ('2025', '2025-06', or '2025-06-01'); use null if absent."
)


def extract_profile(llm: LLMClient, text: str, source_type: SourceType) -> ProfileExtraction:
    """Extract contact, experiences, and skills from one document's text."""
    guidance = _DETAIL_GUIDANCE.get(
        source_type, "Extract experiences and skills faithfully."
    )
    user = f"{guidance}\n\n--- DOCUMENT ---\n{text}"
    return llm.parse(
        task=Task.PARSE,
        system=_SYSTEM,
        messages=[{"role": "user", "content": user}],
        output_format=ProfileExtraction,
    )
