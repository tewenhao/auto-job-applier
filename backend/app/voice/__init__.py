"""Voice model: distill a style guide from the candidate's writing; keep raw
samples for few-shot use at generation time."""

from app.voice.distill import VoiceDraft, distill_voice, draft_to_voice_profile
from app.voice.harvest import (
    MASTER_DOC_VOICE_SOURCE,
    extract_voice_passages,
    harvest_master_doc_voice,
)

__all__ = [
    "MASTER_DOC_VOICE_SOURCE",
    "VoiceDraft",
    "distill_voice",
    "draft_to_voice_profile",
    "extract_voice_passages",
    "harvest_master_doc_voice",
]
