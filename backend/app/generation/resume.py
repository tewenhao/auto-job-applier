"""Résumé tailoring: select, reorder, and rewrite the most JD-relevant parts of
the candidate's profile into a one-page structured resume.

The output is a ``TailoredResume`` — structured, template-agnostic. ``latex.py``
renders it into the candidate's LaTeX template. Grounding is strict: only facts
present in the profile, never an invented metric, and ``handling_notes`` are hard
constraints (never surfaced, and they govern which numbers may be stated).
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from app.config import Task
from app.generation.models import CompanyBrief
from app.listings.models import Listing
from app.llm import LLMClient, cached_text
from app.profile.markdown import profile_to_markdown
from app.profile.models import MasterProfile


class EducationEntry(BaseModel):
    school: str
    location: str = ""
    degree: str = ""
    dates: str = ""
    bullets: list[str] = Field(default_factory=list)


class ExperienceEntry(BaseModel):
    title: str
    org: str = ""
    location: str = ""
    dates: str = ""  # display string, e.g. "Sep 2024 -- Feb 2025"
    end_date: str = ""  # sortable key: "YYYY-MM", "YYYY", or "present" (for ongoing)
    bullets: list[str] = Field(default_factory=list)


class ProjectEntry(BaseModel):
    name: str
    tools: str = ""  # short tool/tech list; rendered after the name as \emph{...}
    dates: str = ""  # display string, e.g. "Sep 2025" or "2024 -- 2025"
    end_date: str = ""  # sortable key: "YYYY-MM", "YYYY", or "present"
    bullets: list[str] = Field(default_factory=list)


class SkillGroup(BaseModel):
    label: str  # e.g. "Programming"
    items: str  # e.g. "Python, Google Apps Script, LaTeX"


class RankedItem(BaseModel):
    """The model's relevance judgement for one experience or project, so the
    selection is inspectable and steerable rather than a black box."""

    kind: str  # "experience" | "project"
    label: str  # human-readable, e.g. "AI Engineer @ RSAF RAiD" or "SMU LIT Hackathon"
    score: int = Field(ge=0, le=100)  # relevance to THIS role
    included: bool  # did it make the one-page resume?
    rationale: str  # one or two sentences: why this score, and why in or out


class TailoredResume(BaseModel):
    """A one-page resume selected + rewritten for one listing.

    Bullets may use ``**bold**`` markers to emphasise key terms; the renderer
    converts them to ``\\textbf{}``. The header (name/contacts) is NOT here — it
    comes verbatim from the candidate record at render time.
    """

    ranking: list[RankedItem] = Field(default_factory=list)  # inspectable selection
    education: list[EducationEntry] = Field(default_factory=list)
    experience: list[ExperienceEntry] = Field(default_factory=list)
    projects: list[ProjectEntry] = Field(default_factory=list)
    projects_title: str = "Projects"  # e.g. "Hackathon Achievements"
    skills: list[SkillGroup] = Field(default_factory=list)


def _handling_notes(profile: MasterProfile) -> list[str]:
    notes = list(profile.candidate.handling_notes)
    for exp in profile.experiences:
        notes.extend(exp.handling_notes)
    return notes


_SYSTEM = (
    "You tailor a candidate's one-page resume for a specific role. You SELECT, "
    "REORDER, and REWRITE from the candidate's real profile — you never author "
    "new achievements.\n\n"
    "TAILORING:\n"
    "- Choose the experiences, projects, and skills for THIS role by a blend of "
    "RELEVANCE and SUBSTANCE, and order them best-first.\n"
    "- SUBSTANCE FIRST: weighty, credible items — real or paid roles, published / "
    "peer-reviewed work, competition placements and awards, and sustained "
    "high-impact projects — outrank small solo or learning projects (a weekend "
    "build, a toy app), EVEN WHEN the small project matches a role keyword. A "
    "keyword match alone does not make an item substantial, and must never push a "
    "lightweight project above a real experience.\n"
    "- Rewrite each bullet to foreground what this employer cares about (from the "
    "role's requirements), using the candidate's real work. Lead with impact.\n"
    "- Emphasise 1-3 key terms or figures per bullet with **double asterisks**.\n\n"
    "GROUNDING (strict — a resume is unforgiving of invention):\n"
    "- Use only facts, numbers, titles, dates, and outcomes present in the "
    "profile. NEVER invent or inflate a metric (percentages, counts, rankings, "
    "time-saved). If the profile doesn't state a number, don't state one.\n"
    "- handling_notes are HARD CONSTRAINTS: obey every one, never quote them, and "
    "let them govern which figures may appear (e.g. if a note says a number is "
    "unverifiable or must not be stated, omit it). State honest status; never "
    "imply production/adoption the profile doesn't support.\n"
    "- Every fact appears in exactly one place; never list the same item twice "
    "across sections.\n"
    "- Do NOT list a programming language or skill on the strength of GitHub "
    "'repo language bytes' alone — those count generated/vendored/dependency code "
    "and are not proof the candidate uses it. A language belongs on the resume "
    "only if it appears in the candidate's Skills or in an actual experience or "
    "project.\n\n"
    "SHAPE — FILL a full page (a sparse, half-empty resume looks worse than a "
    "full one; use the whole page):\n"
    "- Include the most relevant experiences — aim for 4-5 — with 3 substantive "
    "bullets each.\n"
    "- Include 3-4 projects/achievements, 2-3 bullets each.\n"
    "- ERR ON THE SIDE OF MORE real, relevant content: the system trims any "
    "overflow back to exactly one page, so a slightly-too-long draft is ideal — a "
    "sparse one is a failure. Never hold back relevant material to stay short.\n"
    "- Education: the candidate's real schools; a short 'relevant modules' style "
    "bullet only where it helps. Keep societies, sports, and hobbies out of "
    "Education — those belong only in the Hobbies group.\n"
    "- Skills: 4-5 grouped lines (e.g. Programming / AI-ML / Tools), only real "
    "skills from the profile.\n"
    "- Include a final skills group labelled 'Hobbies' with the candidate's "
    "non-technical hobbies from the profile (each with how long they've done it "
    "and any achievement), if the profile has any.\n"
    "- Title the projects section 'Hackathon Achievements' if the chosen entries "
    "are competition/hackathon results, else 'Projects'.\n\n"
    "ORDERING:\n"
    "- List experiences AND projects most-relevant-first (this ranking decides "
    "what is kept if space is tight); also give each a sortable 'end_date' "
    "('YYYY-MM', 'YYYY', or 'present') — the renderer displays both experience and "
    "projects in reverse-chronological order.\n"
    "- Dates as 'Mon YYYY -- Mon YYYY' or 'Mon YYYY -- Present'.\n\n"
    "RANKING (make your selection transparent, and let it be steered):\n"
    "- Also return 'ranking': EVERY experience and project in the profile you "
    "considered — both the ones you included and the ones you left off — each with "
    "kind ('experience'/'project'), a human-readable label, a 0-100 score, an "
    "'included' flag, and a one-line rationale for the score and the in/out "
    "decision. The score reflects BOTH relevance to the role AND substance/"
    "credibility (per SUBSTANCE FIRST above): a lightweight keyword match scores "
    "LOWER than a substantial experience. Order the ranking by score, highest "
    "first; 'included' must match the experience/projects sections.\n"
    "- STEERING NOTES (when the user provides them) are explicit instructions that "
    "OVERRIDE your default judgment. They MUST visibly change the affected items' "
    "scores and 'included' flags — never return an unchanged ranking when steered "
    "— and each affected item's rationale must say it was adjusted for the steer "
    "(e.g. 'boosted to 90 per your note to prioritise substantial roles')."
)


def tailor_resume(
    llm: LLMClient,
    *,
    listing: Listing,
    profile: MasterProfile,
    brief: CompanyBrief | None = None,
    steer: str | None = None,
) -> TailoredResume:
    """Produce a structured, one-page resume tailored to ``listing``.

    ``steer`` is optional free-text guidance from the user on what to include,
    exclude, or rank higher/lower — used to regenerate after reviewing the
    ranking.
    """
    notes = _handling_notes(profile)
    rules = "\n".join(f"- {n}" for n in notes) or "(none)"
    steer_block = (
        f"# STEERING NOTES from the candidate (override selection/ranking accordingly)\n{steer}\n\n"
        if steer and steer.strip()
        else ""
    )

    # The profile comes FIRST and is cached: it is ~17k tokens, identical for
    # every listing, and would otherwise be re-read at full price on every
    # generation. Everything that varies per listing — the role, the brief, the
    # steer — goes after the breakpoint, where it invalidates nothing.
    profile_block = (
        f"# Candidate profile (the ONLY source of facts)\n{profile_to_markdown(profile)}"
    )
    task_block = (
        f"# Target role\nCompany: {listing.company}\nTitle: {listing.role_title}\n"
        f"Summary: {listing.jd_summary}\n"
        f"Requirements: {', '.join(listing.requirements) or 'n/a'}\n\n"
        f"# Company brief (for emphasis only — do not add facts from it to the resume)\n"
        f"{(brief.brief if brief else '(none)')}\n\n"
        f"{steer_block}"
        "HARD RULES — never violate these handling notes, and never quote them:\n"
        f"{rules}\n\n"
        "Produce the tailored one-page resume now, including the ranking."
    )

    # Generous ceiling: the tailored resume is a large structured payload (a
    # ranking with a rationale for every experience/project, plus rewritten
    # bullets and skills), and Opus 5 thinks by default with thinking counting
    # against max_tokens. A low cap truncates the JSON mid-string — worse when
    # steering makes the model reason and write more. The model stops at
    # end_turn well before this; it's a ceiling, not a target.
    return llm.parse(
        task=Task.GENERATE,
        system=_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": [cached_text(profile_block), {"type": "text", "text": task_block}],
            }
        ],
        output_format=TailoredResume,
        max_tokens=16000,
        cache_system=True,
    )


def _tokens(text: str | None) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", (text or "").lower()) if t}


def _ranked_score(label: str, ranking: list[RankedItem], kind: str, position: int) -> int:
    """The model's score for the entry described by ``label``.

    ``ranking`` labels are free text ("AI Engineer @ RSAF RAiD"), so match them
    to entries by token overlap. When an entry can't be matched, fall back to a
    position-derived score, which preserves the old "the list is best-first"
    assumption for that entry only.
    """
    tokens = _tokens(label)
    best_score: int | None = None
    best_overlap = 0.0
    for item in ranking:
        if item.kind != kind:
            continue
        other = _tokens(item.label)
        if not tokens or not other:
            continue
        overlap = len(tokens & other) / min(len(tokens), len(other))
        if overlap > best_overlap:
            best_overlap, best_score = overlap, item.score
    if best_score is not None and best_overlap >= 0.5:
        return best_score
    return max(0, 100 - position)


def _weakest_index(labels: list[str], ranking: list[RankedItem], kind: str) -> int:
    """Index of the lowest-ranked entry; ties resolve to the later one."""
    scored = [
        (_ranked_score(label, ranking, kind, i), i) for i, label in enumerate(labels)
    ]
    return min(scored, key=lambda pair: (pair[0], -pair[1]))[1]


# A rendered bullet line holds roughly this many characters: \textwidth is
# ~7.5in at \small in the template. Merging two bullets only saves a line when
# the result still fits on one — beyond that it just re-wraps.
ONE_LINE_CHARS = 110


def _plain(text: str) -> str:
    """Bullet length as rendered — the ``**`` emphasis markers don't print."""
    return text.replace("**", "")


def _bullet_value(bullet: str) -> tuple[int, int]:
    """How much a bullet is worth keeping: a concrete figure beats prose, and
    among equals the longer bullet says more."""
    return (1 if re.search(r"\d", bullet) else 0, len(_plain(bullet)))


def _mergeable(entry: ExperienceEntry | ProjectEntry) -> int | None:
    """Index of the first of an adjacent pair that would still fit one line."""
    best_index, best_len = None, ONE_LINE_CHARS + 1
    for i in range(len(entry.bullets) - 1):
        combined = len(_plain(entry.bullets[i])) + len(_plain(entry.bullets[i + 1])) + 1
        if combined <= ONE_LINE_CHARS and combined < best_len:
            best_index, best_len = i, combined
    return best_index


def _join(first: str, second: str) -> str:
    """Two bullets as one. Keep both sentences intact so nothing is reworded."""
    first = first.rstrip()
    if not first.endswith((".", "!", "?", ";")):
        first += "."
    return f"{first} {second}"


def trim_one_step(
    resume: TailoredResume,
    *,
    min_projects: int = 1,
    min_experiences: int = 2,
    rich_bullets: int = 2,
) -> tuple[TailoredResume, str] | None:
    """Return a copy of ``resume`` with one trim applied and a short description
    of it — or ``None`` when nothing more can go.

    Steps are ordered by how much they cost the reader, cheapest first, rather
    than treating whole entries and bullets as strictly ranked:

    1. merge two short bullets that still fit one line — saves a line, loses
       nothing;
    2. drop an entry's least informative bullet (prose before figures) while it
       still has ``rich_bullets``, so entries thin out before any is deleted;
    3. drop the weakest whole project, down to ``min_projects``;
    4. drop the weakest whole experience, down to ``min_experiences``;
    5. keep shaving bullets toward one each;
    6. drop what remains, projects before experiences.

    "Weakest" is the lowest score in ``resume.ranking`` — the same scores
    steering moves — so a steered-up item is not cut for sitting late in a list.
    """
    r = resume.model_copy(deep=True)
    entries: list[ExperienceEntry | ProjectEntry] = [*r.experience, *r.projects]

    def _label(entry: ExperienceEntry | ProjectEntry) -> str:
        name = entry.title if isinstance(entry, ExperienceEntry) else entry.name
        return name or "an entry"

    def _drop_project(index: int) -> tuple[TailoredResume, str]:
        gone = r.projects.pop(index)
        score = _ranked_score(gone.name, r.ranking, "project", index)
        return r, f"dropped project '{gone.name}' (rank {score})"

    def _drop_experience(index: int) -> tuple[TailoredResume, str]:
        gone = r.experience.pop(index)
        label = f"{gone.title} {gone.org}".strip()
        score = _ranked_score(label, r.ranking, "experience", index)
        return r, f"dropped experience '{gone.title}' (rank {score})"

    def _shave(floor: int) -> tuple[TailoredResume, str] | None:
        """Drop the least informative bullet from the entry carrying the most."""
        fattest = max(
            (e for e in entries if len(e.bullets) > floor),
            key=lambda e: len(e.bullets),
            default=None,
        )
        if fattest is None:
            return None
        i = min(
            range(len(fattest.bullets)),
            key=lambda j: (_bullet_value(fattest.bullets[j]), -j),
        )
        fattest.bullets.pop(i)
        return r, f"dropped a bullet from '{_label(fattest)}'"

    # 1) Free: merge two short bullets into one line.
    for entry in entries:
        pair = _mergeable(entry)
        if pair is not None:
            entry.bullets[pair] = _join(entry.bullets[pair], entry.bullets[pair + 1])
            entry.bullets.pop(pair + 1)
            return r, f"merged two bullets in '{_label(entry)}'"

    # 2) Thin the fattest entry before deleting anything outright.
    shaved = _shave(rich_bullets)
    if shaved is not None:
        return shaved

    # 3) Drop the weakest project (whole), keeping a floor.
    if len(r.projects) > min_projects:
        return _drop_project(_weakest_index([p.name for p in r.projects], r.ranking, "project"))
    # 4) Drop the weakest experience (whole), keeping a floor.
    if len(r.experience) > min_experiences:
        labels = [f"{e.title} {e.org}".strip() for e in r.experience]
        return _drop_experience(_weakest_index(labels, r.ranking, "experience"))
    # 5) Keep shaving toward one bullet each.
    shaved = _shave(1)
    if shaved is not None:
        return shaved
    # 6) Nothing left to shave — drop remaining projects, then experiences.
    if r.projects:
        return _drop_project(_weakest_index([p.name for p in r.projects], r.ranking, "project"))
    if len(r.experience) > 1:
        labels = [f"{e.title} {e.org}".strip() for e in r.experience]
        return _drop_experience(_weakest_index(labels, r.ranking, "experience"))

    return None


RESUME_GUIDANCE_KEY = "resume_guidance"


def compose_steer(standing: str | None, steer: str | None) -> str | None:
    """Combine the candidate's standing generation guidance (a persisted
    preference applied to every resume) with a per-application ``steer`` (a
    one-off override that takes precedence). Either may be absent."""
    parts: list[str] = []
    if standing and standing.strip():
        parts.append(f"Standing preferences (apply to every resume): {standing.strip()}")
    if steer and steer.strip():
        parts.append(f"For THIS application (takes precedence if it conflicts): {steer.strip()}")
    return "\n".join(parts) or None


def resume_bullet_texts(resume: TailoredResume) -> list[str]:
    """Flatten every bullet (bold markers stripped) — used to tell the cover
    letter not to restate what the resume already says."""
    out: list[str] = []
    for exp in resume.experience:
        out.extend(exp.bullets)
    for proj in resume.projects:
        out.extend(proj.bullets)
    return [b.replace("**", "").strip() for b in out if b.strip()]
