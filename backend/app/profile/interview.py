"""The gap-aware interview for adding one new entry to the master-doc.

Rather than a form, this asks the candidate about a new experience the way a
good friend would — one question at a time, pushing for the specifics a resume
needs (their contribution as distinct from the team's, honest status, real
figures) — and then drafts the entry in the master-doc's canonical format.

The draft is returned for review, never written silently: the master-doc is the
candidate's own source of truth.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from app.config import Task
from app.llm import LLMClient

# Sections a drafted entry can go into (mirrors master_doc.SECTION_ALIASES).
Section = Literal["experience", "projects", "education", "awards", "volunteering", "hobbies"]

MAX_QUESTIONS = 12


class InterviewStep(BaseModel):
    """One turn: either the next question, or a signal there's enough."""

    question: str | None = None
    ready: bool = False
    missing: str | None = None  # what still needs covering, for the UI


class DraftedEntry(BaseModel):
    section: Section = "experience"
    markdown: str  # the full entry, starting with its '### ' heading


_FORMAT = (
    "The master-doc entry format, which is parsed literally:\n"
    "```\n"
    "### <Role> — <Org>, <Location>. <Start> - <End|Present>\n"
    "\n"
    "**FACTS:**\n"
    "- **The problem / context**: what was true; honest scale anchors.\n"
    "- **My role**: the precise contribution — theirs vs the team's.\n"
    "- **Stack / how it works**: tools and architecture.\n"
    "- **Status**: honest — shipped / demoed / in development / pre-trial.\n"
    "\n"
    "**VOICE:**\n"
    "- why it mattered or what it taught them, in their own reflective voice.\n"
    "\n"
    "**PRIVATE — do not surface externally:**\n"
    "- anything not to claim publicly (omit this block if there is nothing).\n"
    "```\n"
    "The heading carries identity: a role/name, an org or context, and dates. "
    "Dates MUST parse as one of 'YYYY', 'YYYY-MM', 'Mon YYYY' (e.g. 'Jun 2026') "
    "or 'Month YYYY' — never 'Summer 2025' or 'AY24/25'. An ongoing entry ends "
    "with 'Present'."
)

_INTERVIEW_SYSTEM = (
    "You are helping a candidate add ONE new entry to their master document — "
    "the superset record every future resume and cover letter is written from.\n\n"
    "Ask ONE short question at a time, and make it specific to what they just "
    "said. You are drawing out what a resume needs and people leave out:\n"
    "- the role, organisation, location and dates (dates precise enough to parse);\n"
    "- what the problem actually was;\n"
    "- THEIR contribution as distinct from the team's;\n"
    "- the stack / how it worked;\n"
    "- honest status — shipped, demoed, abandoned, still in progress;\n"
    "- any real figures (scale, time saved, placement), and never press for a "
    "number that doesn't exist;\n"
    "- why it mattered to them, in their own words (this feeds the voice model).\n\n"
    "Never invent details or suggest impressive-sounding numbers. If they don't "
    "know something, move on. Set ready=true as soon as you could write an "
    "honest, specific entry — usually 4-8 questions. Don't interrogate.\n\n"
    "Always return EITHER a question OR ready=true. Never both empty.\n\n"
    f"{_FORMAT}"
)

_DRAFT_SYSTEM = (
    "Write ONE master-doc entry from the interview transcript below.\n\n"
    "Use ONLY what the candidate said. Never add a figure, tool, or outcome "
    "they did not state. If something is unknown, leave it out rather than "
    "hedging in prose. Keep their phrasing in the VOICE block — that block is a "
    "voice sample, so it should sound like them, not like a resume.\n\n"
    "Choose the section this belongs in: experience, projects, education, "
    "awards, volunteering, or hobbies.\n\n"
    f"{_FORMAT}"
)


def _messages(transcript: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Interview turns as an Anthropic message list."""
    return [
        {
            "role": "assistant" if t.get("role") == "assistant" else "user",
            "content": str(t.get("content", "")),
        }
        for t in transcript
        if str(t.get("content", "")).strip()
    ]


def next_step(
    llm: LLMClient, transcript: list[dict[str, Any]], *, profile_markdown: str = ""
) -> InterviewStep:
    """The next question, or ready=True when there's enough for an entry."""
    messages = _messages(transcript)
    if not messages:
        # Opening turn — nothing said yet.
        return InterviewStep(
            question=(
                "What would you like to add? A sentence on what it is and where is plenty to start."
            )
        )
    asked = sum(1 for m in messages if m["role"] == "assistant")
    if asked >= MAX_QUESTIONS:
        return InterviewStep(ready=True, missing="reached the question limit")

    context = (
        f"# What the profile already holds (avoid re-asking)\n{profile_markdown[:4000]}\n\n"
        if profile_markdown
        else ""
    )
    messages = [
        {"role": "user", "content": f"{context}Interview me about the new entry."},
        *messages,
    ]
    if messages[-1]["role"] == "assistant":
        # The API requires the conversation to end with a user turn, and a
        # transcript ends on a question whenever the last one went unanswered
        # (a reload, or the candidate asking to draft early).
        messages.append(
            {
                "role": "user",
                "content": (
                    "(No answer to that one.) If there is enough here for an honest "
                    "entry, set ready. Otherwise ask something else."
                ),
            }
        )
    step = llm.parse(
        task=Task.INTERVIEW,
        system=_INTERVIEW_SYSTEM,
        messages=messages,
        output_format=InterviewStep,
        max_tokens=4000,
    )
    if not step.ready and not (step.question or "").strip():
        # Neither a question nor a ready signal would stall the interview.
        # Having asked something already, treat silence as "enough".
        return InterviewStep(ready=True, missing=step.missing)
    return step


def draft_entry(llm: LLMClient, transcript: list[dict[str, Any]]) -> DraftedEntry:
    """Draft the master-doc entry from the transcript, for the user to review."""
    conversation = "\n\n".join(
        f"{'Q' if t.get('role') == 'assistant' else 'A'}: {t.get('content', '')}"
        for t in transcript
    )
    return llm.parse(
        task=Task.GENERATE,
        system=_DRAFT_SYSTEM,
        messages=[{"role": "user", "content": f"# Transcript\n{conversation}"}],
        output_format=DraftedEntry,
        max_tokens=8000,
    )


# --- persistence: sessions are resumable, so an interview can be picked up
# later (or continued in the CLI after starting in the dashboard) ---
def load_transcript(repo: Any, session_id: Any) -> list[dict[str, str]]:
    """The stored turns as the plain transcript the prompts take."""
    return [
        {"role": str(t.role), "content": t.content}
        for t in repo.list_interview_turns(session_id)
    ]


def record_turn(repo: Any, session: Any, role: str, content: str) -> None:
    """Append one turn, numbering it after whatever is already stored."""
    from app.profile.models import InterviewRole
    from app.profile.models import InterviewTurn as TurnRow

    seq = len(repo.list_interview_turns(session.id))
    repo.add_interview_turn(
        TurnRow(
            session_id=session.id,
            candidate_id=session.candidate_id,
            seq=seq,
            role=InterviewRole(role),
            content=content,
        )
    )


def open_or_resume(repo: Any, candidate_id: Any, *, resume: bool = True) -> tuple[Any, bool]:
    """Return (session, resumed). An unfinished session is continued unless
    ``resume`` is False, in which case it is abandoned and a new one started."""
    existing = repo.get_open_interview_session(candidate_id)
    if existing is not None:
        if resume:
            return existing, True
        repo.abandon_interview_session(existing.id)
    return repo.create_interview_session(candidate_id), False
