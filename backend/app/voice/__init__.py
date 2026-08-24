"""Voice model: distill a style guide from the candidate's writing; keep raw
samples for few-shot use at generation time."""

from app.voice.distill import VoiceDraft, distill_voice, draft_to_voice_profile

__all__ = ["VoiceDraft", "distill_voice", "draft_to_voice_profile"]
