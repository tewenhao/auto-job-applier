"""Cover-letter generation: grounded in the JD + company brief + the candidate's
profile, written in their authentic voice, respecting handling_notes as hard
rules, and deliberately humanified (not LLM-sounding)."""

from __future__ import annotations

from app.config import Task
from app.generation.models import CompanyBrief
from app.listings.models import Listing
from app.llm import LLMClient
from app.profile.markdown import profile_to_markdown
from app.profile.models import MasterProfile, VoiceProfile, WritingSample

_MAX_SAMPLE_CHARS = 2500
_ANTI_LLM = (
    "Write like a real person, not an AI. Avoid the usual tells: no 'I am writing "
    "to express my keen interest', no 'In today's fast-paced world', no hollow "
    "superlatives, no throat-clearing wind-ups, no restating the job title back at "
    "them. Vary sentence length. Prefer one concrete, specific story over generic "
    "enthusiasm. It should read as though the candidate wrote it in a focused hour."
)


def _voice_block(voice: VoiceProfile | None) -> str:
    if voice is None:
        return "(no distilled voice profile — infer voice from the writing samples)"
    guide = voice.guide or {}
    parts = [f"Tone: {voice.tone}", voice.summary or ""]
    fields = (("Rhythm", "rhythm"), ("Quirks", "quirks"), ("Do", "dos"), ("Don't", "donts"))
    for label, key in fields:
        value = guide.get(key)
        if value:
            parts.append(f"{label}: {value if isinstance(value, str) else '; '.join(value)}")
    return "\n".join(p for p in parts if p)


def _handling_notes(profile: MasterProfile) -> list[str]:
    notes = list(profile.candidate.handling_notes)
    for exp in profile.experiences:
        notes.extend(exp.handling_notes)
    return notes


def _samples_block(samples: list[WritingSample]) -> str:
    if not samples:
        return "(none)"
    return "\n\n".join(f"[{s.source}] {(s.text or '')[:_MAX_SAMPLE_CHARS]}" for s in samples[:3])


def generate_cover_letter(
    llm: LLMClient,
    *,
    listing: Listing,
    profile: MasterProfile,
    voice: VoiceProfile | None,
    samples: list[WritingSample],
    brief: CompanyBrief | None,
) -> str:
    notes = _handling_notes(profile)
    rules = "\n".join(f"- {n}" for n in notes) or "(none)"

    system = (
        "You write an outstanding, honest cover letter for the candidate.\n\n"
        f"{_ANTI_LLM}\n\n"
        "Ground every claim in the candidate's real experiences below — never "
        "invent achievements. Connect specifically to the company (use the brief's "
        "concrete hooks, not generic praise). Roughly 300-400 words.\n\n"
        "The candidate's authentic voice:\n"
        f"{_voice_block(voice)}\n\n"
        "HARD RULES — never violate these handling notes, and never quote them:\n"
        f"{rules}"
    )

    user = (
        f"# The role\nCompany: {listing.company}\nTitle: {listing.role_title}\n"
        f"Summary: {listing.jd_summary}\n"
        f"Requirements: {', '.join(listing.requirements) or 'n/a'}\n\n"
        f"# Company brief\n{(brief.brief if brief else '(none)')}\n\n"
        f"# Candidate profile\n{profile_to_markdown(profile)}\n\n"
        f"# The candidate's own past writing (imitate this voice, do not copy content)\n"
        f"{_samples_block(samples)}\n\n"
        "Write the cover letter now. Output only the letter."
    )

    # Generous ceiling: Opus 5 thinks by default and thinking counts against
    # max_tokens, so a low cap truncates the letter. The model stops at end_turn
    # well before this; it's a ceiling, not a target.
    return llm.complete(
        task=Task.GENERATE,
        system=system,
        messages=[{"role": "user", "content": user}],
        max_tokens=8000,
    )
