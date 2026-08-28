"""Cover-letter generation: grounded in the JD + company brief + the candidate's
profile, written in their authentic voice, respecting handling_notes as hard
rules, and deliberately humanified (not LLM-sounding)."""

from __future__ import annotations

import re

from app.config import Task
from app.generation.models import CompanyBrief
from app.listings.models import Listing
from app.llm import LLMClient, cached_text
from app.profile.markdown import profile_to_markdown
from app.profile.models import MasterProfile, VoiceProfile, WritingSample

_MAX_SAMPLE_CHARS = 2500
_ANTI_LLM = (
    "Write like one specific human being, not an AI assistant. Letters that read as "
    "machine-written get discarded, so avoid EVERY common tell:\n"
    "- PUNCTUATION: never use an em dash or en dash (— or –) anywhere. Break the "
    "sentence with a full stop, or join with a comma, a colon, parentheses, or the "
    "word 'and'. Don't use semicolons to stitch clauses together for effect.\n"
    "- BANNED WORDS (they read as AI): delve, leverage, utilise, utilize, harness, "
    "showcase, underscore, spearhead, foster, cultivate, empower, unlock, elevate, "
    "resonate, align, alignment, tapestry, realm, landscape, ecosystem, journey, "
    "testament, pivotal, robust, seamless, holistic, synergy, myriad, plethora, "
    "meticulous, diligent, versatile, invaluable, profound, vibrant, dynamic, "
    "innovative, cutting-edge, passionate, thrilled, excited, eager, keen. Prefer "
    "the plain word: 'use', not 'leverage'; 'build', not 'architect'; 'show', not "
    "'showcase'.\n"
    "- BANNED PHRASES: 'I am writing to express my interest', 'I am excited/thrilled "
    "to apply', 'I believe I would be a great fit', 'this role aligns perfectly', "
    "'I am particularly drawn to', 'in today's fast-paced world', 'at the "
    "forefront', 'a proven track record', 'a wealth of experience', 'hit the ground "
    "running', 'think outside the box', 'commitment to excellence', and any "
    "'thank you for your consideration / for reading' sign-off.\n"
    "- STRUCTURE: no rule-of-three lists (three parallel items strung together for "
    "rhythm), no 'not just X, but Y' constructions, no throat-clearing wind-ups, no "
    "restating the job title back at them, no hollow superlatives. Don't open "
    "several sentences with the same participial shape ('Having...', 'Building "
    "on...'). Vary sentence length; let some run short and blunt. Contractions are "
    "fine and human.\n"
    "- Before you finish, reread and cut any sentence that could sit unchanged in "
    "someone else's letter. It should read as though this candidate wrote it in a "
    "focused hour."
)

# Em/en dashes are a top AI tell. The prompt forbids them; this guarantees it,
# rewriting any that slip through into human punctuation.
_DASH = re.compile(r"[ \t]*[—–][ \t]*")


def _strip_ai_dashes(text: str) -> str:
    """Replace em/en dashes with a comma (the safest universal substitute) and
    tidy the spacing/commas that produces."""
    text = _DASH.sub(", ", text)
    text = re.sub(r"[ \t]+,", ",", text)  # " ," -> ","
    text = re.sub(r",\s*,+", ",", text)  # ",," -> ","
    text = re.sub(r"[ \t]+\n", "\n", text)  # trailing spaces before a newline
    return text

# What a cover letter is FOR — the resume already carries the facts. This is the
# guidance that stops the letter from becoming a prose resume.
_PRINCIPLES = (
    "A cover letter is NOT a prose version of the resume. The resume is attached "
    "and already lists the roles, dates, stacks, and achievements; the reader has "
    "it. So do NOT catalogue experiences or re-state bullet points. The letter's "
    "job is the part a resume structurally cannot carry:\n"
    "- MOTIVATION: a genuine, specific reason this candidate wants THIS company and "
    "THIS role — tied to a real product, team, value, or problem from the company "
    "brief, never generic praise.\n"
    "- FIT: why the candidate's way of thinking and working suits what this team "
    "actually needs (connect to the role's real demands, not a keyword list).\n"
    "- DEPTH OVER BREADTH: pick ONE, at most two, threads from the candidate's "
    "background and go deep on the thinking, the decision, the why — not a tour of "
    "the CV. A resume says what; the letter says why it mattered and what it means "
    "for this employer.\n"
    "- FORWARD-LOOKING: what the candidate would bring and want to contribute here, "
    "not a summary of the past.\n"
    "It is fine to reference an experience the resume also lists — but only to open "
    "up motivation, reasoning, or fit that the resume can't show. If a sentence "
    "would sit equally well as a resume bullet, cut it."
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


def _resume_points_block(points: list[str] | None) -> str:
    if not points:
        return ""
    listed = "\n".join(f"- {p}" for p in points[:20])
    return (
        "\n\n# Already on the resume (the reader will see these) — do NOT restate "
        "these bullets; at most, open ONE of them up into motivation/why the "
        "resume can't show:\n"
        f"{listed}"
    )


def generate_cover_letter(
    llm: LLMClient,
    *,
    listing: Listing,
    profile: MasterProfile,
    voice: VoiceProfile | None,
    samples: list[WritingSample],
    brief: CompanyBrief | None,
    resume_points: list[str] | None = None,
) -> str:
    notes = _handling_notes(profile)
    rules = "\n".join(f"- {n}" for n in notes) or "(none)"

    system = (
        "You write an outstanding, honest cover letter for the candidate.\n\n"
        f"{_PRINCIPLES}\n\n"
        f"{_ANTI_LLM}\n\n"
        "GROUNDING: use only facts, numbers, titles, and outcomes that appear in "
        "the candidate PROFILE below. Never invent or embellish a figure (counts, "
        "percentages, rankings) — if a number isn't in the profile, don't state it. "
        "Connect specifically to the company using the brief's concrete hooks. Do "
        "NOT describe the company with a vague filler noun ('your platform', 'your "
        "organisation', 'your ecosystem') unless the brief shows that is literally "
        "what it is — refer to the actual team, desk, role, or work instead.\n"
        "VOICE SAMPLES ARE STYLE-ONLY: the candidate's past writing is provided "
        "solely to learn HOW they write (tone, rhythm, phrasing). It is NOT a "
        "source of facts. Never lift a claim, achievement, story, name, place, or "
        "detail from the samples — every factual statement must come from the "
        "profile, even if the samples mention something the profile does not.\n\n"
        "REGISTER: this is an application for the role named below, which is an "
        "internship / early-career position. Write as a strong student applying for "
        "an internship — confident and substantive, but never presumptuous: do not "
        "speak as a lateral or experienced hire, do not presume a permanent seat, "
        "and do not bargain over scope. Aim for genuine and grounded, not slick.\n\n"
        "Length: roughly 250-350 words — short and targeted.\n\n"
        "Close with a short forward-looking line that fits a student applying for "
        "THIS internship (e.g. what they'd hope to contribute or learn over the "
        "internship) — not an open-ended offer to 'discuss where this fits'. Then "
        "sign off exactly:\n"
        "Best wishes,\nEn Hao Tew\n\n"
        "The candidate's authentic voice:\n"
        f"{_voice_block(voice)}\n\n"
        "HARD RULES — never violate these handling notes, and never quote them:\n"
        f"{rules}"
    )

    # Profile and writing samples first, behind a cache breakpoint: they are the
    # bulk of the prompt and are the same for every application. The role, the
    # brief, and this draft's resume points follow, so they cost full price only
    # for what actually changed.
    context_block = (
        f"# Candidate profile — this is also what the resume is built from, so the "
        f"reader will see these facts on the resume. Do NOT re-list them; use them "
        f"to find the ONE thread worth opening up on motivation and fit.\n"
        f"{profile_to_markdown(profile)}\n\n"
        f"# The candidate's own past writing — STYLE REFERENCE ONLY (learn the "
        f"voice; take no facts, claims, or details from it)\n"
        f"{_samples_block(samples)}"
    )
    task_block = (
        f"# The role\nCompany: {listing.company}\nTitle: {listing.role_title}\n"
        f"Summary: {listing.jd_summary}\n"
        f"Requirements: {', '.join(listing.requirements) or 'n/a'}\n\n"
        f"# Company brief (mine this for the specific 'why this company' hook)\n"
        f"{(brief.brief if brief else '(none)')}"
        f"{_resume_points_block(resume_points)}\n\n"
        "Write the cover letter now. Output only the letter."
    )

    # Generous ceiling: Opus 5 thinks by default and thinking counts against
    # max_tokens, so a low cap truncates the letter. The model stops at end_turn
    # well before this; it's a ceiling, not a target.
    letter = llm.complete(
        task=Task.GENERATE,
        system=system,
        messages=[
            {
                "role": "user",
                "content": [cached_text(context_block), {"type": "text", "text": task_block}],
            }
        ],
        max_tokens=8000,
        cache_system=True,
    )
    return _strip_ai_dashes(letter.strip())
