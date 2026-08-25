"""Résumé tailoring: select, reorder, and rewrite the most JD-relevant parts of
the candidate's profile into a one-page structured resume.

The output is a ``TailoredResume`` — structured, template-agnostic. ``latex.py``
renders it into the candidate's LaTeX template. Grounding is strict: only facts
present in the profile, never an invented metric, and ``handling_notes`` are hard
constraints (never surfaced, and they govern which numbers may be stated).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.config import Task
from app.generation.models import CompanyBrief
from app.listings.models import Listing
from app.llm import LLMClient
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
    dates: str = ""
    bullets: list[str] = Field(default_factory=list)


class SkillGroup(BaseModel):
    label: str  # e.g. "Programming"
    items: str  # e.g. "Python, Google Apps Script, LaTeX"


class TailoredResume(BaseModel):
    """A one-page resume selected + rewritten for one listing.

    Bullets may use ``**bold**`` markers to emphasise key terms; the renderer
    converts them to ``\\textbf{}``. The header (name/contacts) is NOT here — it
    comes verbatim from the candidate record at render time.
    """

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
    "- Choose the experiences, projects, and skills most relevant to THIS role, "
    "and order them most-relevant first.\n"
    "- Write dense, impact-first bullets: lead with the concrete outcome and the "
    "real headline numbers the profile provides (scale, result, recognition, "
    "dataset size, accuracy, placement, team size, adoption). Pack the key metric "
    "INTO a bullet rather than adding more bullets. Don't leave impact vague when "
    "the profile quantifies it; don't write generic responsibility statements.\n"
    "- Emphasise 1-3 key terms or figures per bullet with **double asterisks**.\n\n"
    "NO DUPLICATION:\n"
    "- Every fact appears in exactly ONE place. Never repeat an item across "
    "sections — in particular, hobbies, sports, societies, and clubs appear ONLY "
    "in the 'Hobbies' group, never under Education; a programme, competition, or "
    "award appears once.\n\n"
    "GROUNDING (strict — a resume is unforgiving of invention):\n"
    "- Use only facts, numbers, titles, dates, and outcomes present in the "
    "profile. NEVER invent or inflate a metric (percentages, counts, rankings, "
    "time-saved). If the profile doesn't state a number, don't state one.\n"
    "- handling_notes are HARD CONSTRAINTS: obey every one, never quote them, and "
    "let them govern which figures may appear (e.g. if a note says a number is "
    "unverifiable or must not be stated, omit it). State honest status; never "
    "imply production/adoption the profile doesn't support.\n\n"
    "SHAPE (a tight one page — this layout is known to fit):\n"
    "- 4 experiences, 2-3 dense bullets each (2 is the norm; use a 3rd only for a "
    "standout role that genuinely warrants it).\n"
    "- 3 projects, ~2 bullets each. KEEP the projects section rich — the "
    "candidate's hackathon wins are strong signals; do not shrink projects to "
    "make room. Trim experience detail before projects.\n"
    "- Education: TIGHT — 1-2 short bullets only (a 'relevant modules' line, and "
    "optionally ONE line for a top scholarship/honour). Do NOT list societies, "
    "sports, clubs, extracurriculars, or hobbies under Education.\n"
    "- Skills: 3-5 grouped lines (e.g. Programming / AI-ML / Tools), only real "
    "skills from the profile.\n"
    "- ALWAYS include a final skills group labelled 'Hobbies' with the "
    "candidate's non-technical hobbies from the profile, each with how long "
    "they've done it and any achievement (e.g. 'Fencing (~10 yrs, varsity "
    "medallist, university team); Piano (15 yrs, songwriting)'). This humanises "
    "the resume — never omit it if the profile has hobbies.\n"
    "- Title the projects section 'Hackathon Achievements' if the chosen entries "
    "are competition/hackathon results, else 'Projects'.\n\n"
    "ORDERING:\n"
    "- List EXPERIENCE most-relevant-first (this ranking decides what is kept if "
    "space is tight). For each experience also give 'end_date' as a sortable "
    "'YYYY-MM' (or 'YYYY', or 'present' if ongoing) — the renderer re-sorts the "
    "experience section into reverse-chronological order for display.\n"
    "- List PROJECTS by achievement/relevance weight (kept as given).\n"
    "- Display dates as 'Mon YYYY -- Mon YYYY' or 'Mon YYYY -- Present'."
)


def tailor_resume(
    llm: LLMClient,
    *,
    listing: Listing,
    profile: MasterProfile,
    brief: CompanyBrief | None = None,
) -> TailoredResume:
    """Produce a structured, one-page resume tailored to ``listing``."""
    notes = _handling_notes(profile)
    rules = "\n".join(f"- {n}" for n in notes) or "(none)"

    user = (
        f"# Target role\nCompany: {listing.company}\nTitle: {listing.role_title}\n"
        f"Summary: {listing.jd_summary}\n"
        f"Requirements: {', '.join(listing.requirements) or 'n/a'}\n\n"
        f"# Company brief (for emphasis only — do not add facts from it to the resume)\n"
        f"{(brief.brief if brief else '(none)')}\n\n"
        f"# Candidate profile (the ONLY source of facts)\n{profile_to_markdown(profile)}\n\n"
        "HARD RULES — never violate these handling notes, and never quote them:\n"
        f"{rules}\n\n"
        "Produce the tailored one-page resume now."
    )

    return llm.parse(
        task=Task.GENERATE,
        system=_SYSTEM,
        messages=[{"role": "user", "content": user}],
        output_format=TailoredResume,
        max_tokens=8000,
    )


def trim_one_step(
    resume: TailoredResume,
    *,
    keep_experiences: int = 4,
    keep_projects: int = 3,
    rich_bullets: int = 2,
) -> tuple[TailoredResume, str] | None:
    """Return a copy of ``resume`` with the single least-valuable item removed,
    plus a short description — or ``None`` when nothing more can go.

    Projects (the candidate's hackathon wins) are strong signals, so they are
    protected: trim EXPERIENCE detail before touching projects. Lists are ordered
    most-relevant-first, so "last" is always the least relevant. Escalation:

    1. bullets beyond ``rich_bullets`` on the fattest EXPERIENCE (least damaging);
    2. extra experiences beyond ``keep_experiences``;
    3. extra projects beyond ``keep_projects``;
    4. bullets beyond ``rich_bullets`` on the fattest project;
    5. experiences down to a hard floor of 2;
    6. projects down to a hard floor of 1;
    7. last resort — shave toward a single bullet anywhere.
    """
    r = resume.model_copy(deep=True)

    def _fattest(
        entries: list[ExperienceEntry] | list[ProjectEntry] | list[ExperienceEntry | ProjectEntry],
        floor: int,
    ) -> ExperienceEntry | ProjectEntry | None:
        best: ExperienceEntry | ProjectEntry | None = None
        for entry in entries:
            if len(entry.bullets) > floor and (
                best is None or len(entry.bullets) > len(best.bullets)
            ):
                best = entry
        return best

    def _shave(entry: ExperienceEntry | ProjectEntry) -> tuple[TailoredResume, str]:
        entry.bullets.pop()
        label = getattr(entry, "title", None) or getattr(entry, "name", "an entry")
        return r, f"dropped a bullet from '{label}'"

    # 1) Shave experience detail first (bullets beyond the rich floor).
    fat = _fattest(r.experience, rich_bullets)
    if fat is not None:
        return _shave(fat)
    # 2) Drop extra experiences beyond the keep floor.
    if len(r.experience) > keep_experiences:
        return r, f"dropped experience '{r.experience.pop().title}'"
    # 3) Drop extra projects beyond the keep floor.
    if len(r.projects) > keep_projects:
        return r, f"dropped project '{r.projects.pop().name}'"
    # 4) Shave project bullets beyond the rich floor.
    fat = _fattest(r.projects, rich_bullets)
    if fat is not None:
        return _shave(fat)
    # 5) Drop experiences down to a hard floor of 2.
    if len(r.experience) > 2:
        return r, f"dropped experience '{r.experience.pop().title}'"
    # 6) Drop projects down to a hard floor of 1.
    if len(r.projects) > 1:
        return r, f"dropped project '{r.projects.pop().name}'"
    # 7) Last resort: shave toward a single bullet anywhere.
    everything: list[ExperienceEntry | ProjectEntry] = [*r.experience, *r.projects]
    fat = _fattest(everything, 1)
    if fat is not None:
        return _shave(fat)

    return None


def resume_bullet_texts(resume: TailoredResume) -> list[str]:
    """Flatten every bullet (bold markers stripped) — used to tell the cover
    letter not to restate what the resume already says."""
    out: list[str] = []
    for exp in resume.experience:
        out.extend(exp.bullets)
    for proj in resume.projects:
        out.extend(proj.bullets)
    return [b.replace("**", "").strip() for b in out if b.strip()]
