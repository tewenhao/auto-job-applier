"""Distill a reusable voice profile from the candidate's own writing.

Analyzes the retained writing samples (essays, past cover letters, LinkedIn
summary) into a structured style guide. Downstream generation uses this guide
*and* the raw samples as few-shot examples, so cover letters read in the
candidate's authentic voice rather than a generic LLM register.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from app.config import Task
from app.llm import LLMClient
from app.profile.models import VoiceProfile, WritingSample

# Keep each sample bounded so the prompt stays reasonable across many samples.
_MAX_SAMPLE_CHARS = 4000


class VoiceDraft(BaseModel):
    tone: str  # e.g. "warm, direct, self-aware"
    summary: str  # a short paragraph describing the voice
    rhythm: str  # sentence length/cadence patterns
    vocabulary: list[str] = Field(default_factory=list)  # characteristic words/phrases
    quirks: list[str] = Field(default_factory=list)  # habits: em-dashes, asides, etc.
    dos: list[str] = Field(default_factory=list)
    donts: list[str] = Field(default_factory=list)


_SYSTEM = (
    "Analyze the candidate's authentic writing voice from their own samples, so it "
    "can be reproduced in cover letters and essays. Identify tone, rhythm/cadence, "
    "characteristic vocabulary and phrases, and stylistic quirks (e.g. em-dashes, "
    "self-deprecating asides, concrete anecdotes). Give actionable do/don't guidance "
    "for writing as this person. Base everything ONLY on the samples — do not invent "
    "traits. The goal is writing that reads as genuinely human and specific to them, "
    "never as generic AI prose."
)


def distill_voice(llm: LLMClient, samples: list[WritingSample]) -> VoiceDraft:
    blocks = []
    for s in samples:
        text = (s.text or "")[:_MAX_SAMPLE_CHARS]
        blocks.append(f"--- sample (source: {s.source}) ---\n{text}")
    corpus = "\n\n".join(blocks)
    return llm.parse(
        task=Task.CONSOLIDATE,
        system=_SYSTEM,
        messages=[{"role": "user", "content": f"Writing samples:\n\n{corpus}"}],
        output_format=VoiceDraft,
    )


def draft_to_voice_profile(
    draft: VoiceDraft, *, candidate_id: UUID, sample_ids: list[UUID]
) -> VoiceProfile:
    return VoiceProfile(
        candidate_id=candidate_id,
        tone=draft.tone,
        summary=draft.summary,
        guide={
            "rhythm": draft.rhythm,
            "vocabulary": draft.vocabulary,
            "quirks": draft.quirks,
            "dos": draft.dos,
            "donts": draft.donts,
        },
        built_from=[str(i) for i in sample_ids],
    )
