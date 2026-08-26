"""Harvest authentic-voice passages out of the master document.

The master doc marks its most human, first-person writing with ``VOICE`` headers
(and quotes past essays verbatim), but ingestion folds that prose into experience
detail — so the voice model never sees it. This pulls those passages back out,
verbatim, into writing samples tagged ``source="master_doc"`` so ``voice build``
can learn from them.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from app.config import Task
from app.llm import LLMClient
from app.profile.models import SourceType, WritingSample
from app.profile.repository import ProfileRepository

MASTER_DOC_VOICE_SOURCE = "master_doc"


class VoicePassages(BaseModel):
    passages: list[str] = Field(default_factory=list)


_SYSTEM = (
    "Extract, VERBATIM, the passages of the author's own authentic first-person "
    "writing from this document. Include: text under 'VOICE' headers or marked "
    "'VOICE —', and any quoted personal essays or reflections in their own words. "
    "Exclude structured FACTS, LINKS, and PRIVATE/instruction notes, and anything "
    "written as guidance rather than as the author's natural prose. Copy each "
    "passage exactly — do not paraphrase, summarize, or merge them."
)


def extract_voice_passages(llm: LLMClient, master_doc_text: str) -> list[str]:
    result = llm.parse(
        task=Task.PARSE,
        system=_SYSTEM,
        messages=[{"role": "user", "content": master_doc_text}],
        output_format=VoicePassages,
    )
    return [p.strip() for p in result.passages if p.strip()]


def harvest_master_doc_voice(llm: LLMClient, repo: ProfileRepository, candidate_id: UUID) -> int:
    """Extract master-doc VOICE passages into writing samples (idempotent).

    Returns the number of passages harvested. Replaces any previously harvested
    master-doc voice samples so re-running doesn't duplicate them.
    """
    docs = [
        d
        for d in repo.list_source_documents(candidate_id)
        if d.type == SourceType.MASTER_DOC and d.raw_text
    ]
    if not docs:
        return 0

    text = "\n\n".join(d.raw_text or "" for d in docs)
    passages = extract_voice_passages(llm, text)

    repo.delete_writing_samples_by_source(candidate_id, MASTER_DOC_VOICE_SOURCE)
    for passage in passages:
        repo.add_writing_sample(
            WritingSample(
                candidate_id=candidate_id,
                text=passage,
                source=MASTER_DOC_VOICE_SOURCE,
                tags=["voice"],
            )
        )
    return len(passages)
