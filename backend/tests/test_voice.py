"""Tests for the deterministic voice mapping (no LLM)."""

from __future__ import annotations

from uuid import uuid4

from app.voice.distill import VoiceDraft, draft_to_voice_profile

CID = uuid4()


def test_draft_to_voice_profile_maps_guide() -> None:
    draft = VoiceDraft(
        tone="warm, direct",
        summary="Writes with concrete anecdotes and dry humour.",
        rhythm="short punchy sentences with occasional long asides",
        vocabulary=["genuinely", "unglamorous"],
        quirks=["em-dashes", "self-deprecating asides"],
        dos=["use concrete stories"],
        donts=["avoid corporate buzzwords"],
    )
    sid = uuid4()
    voice = draft_to_voice_profile(draft, candidate_id=CID, sample_ids=[sid])

    assert voice.candidate_id == CID
    assert voice.tone == "warm, direct"
    assert voice.guide["rhythm"].startswith("short")
    assert voice.guide["quirks"] == ["em-dashes", "self-deprecating asides"]
    assert voice.guide["donts"] == ["avoid corporate buzzwords"]
    assert voice.built_from == [str(sid)]
