"""Semantic consolidation of the experience bank.

The natural-key dedup at ingestion time only catches exact ``(kind, org, title)``
matches, so the same real-world engagement described differently across sources
(resume versions + master doc) lands as several rows. This module fixes that
after the fact with an LLM merge pass:

1. **Cluster** — group experiences that refer to the same engagement, even when
   kind/org/title wording differs (Opus; judgment-heavy).
2. **Merge** — for each cluster, combine the detail, union skills/tech/highlights,
   and split any "do not surface" guidance out of ``detail`` into
   ``handling_notes``.

Operates on the *existing* experiences only — it never re-reads source documents,
so it's safe to run repeatedly.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field

from app.config import Task
from app.llm import LLMClient
from app.profile.models import Experience, ExperienceKind, Skill
from app.profile.repository import ProfileRepository


# --- clustering ---
class Cluster(BaseModel):
    members: list[int] = Field(default_factory=list)  # indices into the input list
    primary: int  # index whose detail is richest (prefer master_doc)
    canonical_kind: ExperienceKind
    canonical_org: str | None = None
    canonical_title: str | None = None


class ClusterPlan(BaseModel):
    clusters: list[Cluster] = Field(default_factory=list)


# --- per-cluster merge ---
class MergedContent(BaseModel):
    summary: str | None = None
    detail: str | None = None  # FACTS + VOICE only; no private guidance
    skills: list[str] = Field(default_factory=list)
    tech: list[str] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)
    handling_notes: list[str] = Field(default_factory=list)


_CLUSTER_SYSTEM = (
    "You are consolidating a messy career database. Each entry below may describe "
    "the same real-world engagement as another entry, phrased differently across "
    "resume versions and a master document. Group entries that refer to the SAME "
    "engagement into one cluster, even if their kind, organization, or title "
    "wording differs (e.g. 'First-Year Trading' vs 'First Year Trading'; an org "
    "written two different ways). An award/placement and the project that earned "
    "it are the SAME engagement — cluster them together. Different editions of a "
    "recurring event (e.g. a 2024 vs a 2025 competition) are SEPARATE clusters. "
    "Every index must appear in exactly one cluster; unique entries form a cluster "
    "of one. For each cluster pick the single best kind, org, and title, and the "
    "'primary' index whose detail is richest (prefer the fullest / master-doc "
    "version)."
)

_MERGE_SYSTEM = (
    "Merge these entries — all describing one engagement — into a single record. "
    "Combine everything factual and every authentic first-person voice detail into "
    "'detail', preserving specifics (metrics, names, links, narrative) and dropping "
    "only redundancy. Write a concise resume-style 'summary'. Union and de-duplicate "
    "skills, tech, and highlights.\n\n"
    "Critically: any guidance about how to USE or NOT use the material — anything "
    "marked private, 'do not surface', 'don't claim', 'don't inflate', 'do not "
    "imply', audience-specific framing, or things to avoid saying — must be pulled "
    "OUT of detail and returned as separate 'handling_notes' items. detail and "
    "summary must contain no such meta-guidance; they are candidate-facing content. "
    "handling_notes are constraints for later writing and must never appear in a "
    "resume or cover letter."
)


def _fmt_for_cluster(exp: Experience, idx: int) -> str:
    dates = f"{exp.start_date or '?'}..{exp.end_date or ('present' if exp.is_current else '?')}"
    summary = (exp.summary or exp.detail or "")[:200]
    return f"[{idx}] kind={exp.kind} | title={exp.title!r} | org={exp.org!r} | {dates} | {summary}"


def plan_clusters(llm: LLMClient, experiences: list[Experience]) -> ClusterPlan:
    listing = "\n".join(_fmt_for_cluster(e, i) for i, e in enumerate(experiences))
    plan = llm.parse(
        task=Task.CONSOLIDATE,
        system=_CLUSTER_SYSTEM,
        messages=[{"role": "user", "content": f"Entries:\n{listing}"}],
        output_format=ClusterPlan,
    )
    return _normalize_plan(plan, len(experiences))


def _normalize_plan(plan: ClusterPlan, n: int) -> ClusterPlan:
    """Ensure every index is covered exactly once; drop bad refs, add leftovers."""
    seen: set[int] = set()
    clusters: list[Cluster] = []
    for c in plan.clusters:
        members = [i for i in c.members if 0 <= i < n and i not in seen]
        if not members:
            continue
        seen.update(members)
        primary = c.primary if c.primary in members else members[0]
        clusters.append(
            Cluster(
                members=members,
                primary=primary,
                canonical_kind=c.canonical_kind,
                canonical_org=c.canonical_org,
                canonical_title=c.canonical_title,
            )
        )
    for i in range(n):
        if i not in seen:
            clusters.append(Cluster(members=[i], primary=i, canonical_kind=ExperienceKind.OTHER))
    return ClusterPlan(clusters=clusters)


def _fmt_for_merge(exp: Experience) -> str:
    parts = [
        f"kind: {exp.kind}",
        f"title: {exp.title}",
        f"org: {exp.org}",
        f"summary: {exp.summary}",
        f"detail: {exp.detail}",
    ]
    if exp.highlights:
        parts.append("highlights: " + " | ".join(exp.highlights))
    if exp.skills or exp.tech:
        parts.append("skills/tech: " + ", ".join([*exp.skills, *exp.tech]))
    if exp.handling_notes:
        parts.append("existing handling_notes: " + " | ".join(exp.handling_notes))
    return "\n".join(parts)


def merge_cluster(llm: LLMClient, members: list[Experience]) -> MergedContent:
    blocks = "\n\n---\n\n".join(_fmt_for_merge(e) for e in members)
    return llm.parse(
        task=Task.CONSOLIDATE,
        system=_MERGE_SYSTEM,
        messages=[{"role": "user", "content": f"Entries to merge:\n\n{blocks}"}],
        output_format=MergedContent,
    )


def _merge_dates(members: list[Experience]) -> tuple[date | None, date | None, bool]:
    # LinkedIn dates are exact month/year; resume/master-doc year-only dates
    # default to Jan 1 and can be wrong. Prefer LinkedIn's dates when present.
    linkedin = [m for m in members if m.source and "linkedin" in m.source and m.start_date]
    pool = linkedin or members
    starts = [m.start_date for m in pool if m.start_date]
    ends = [m.end_date for m in pool if m.end_date]
    is_current = any(m.is_current for m in members)
    return (min(starts) if starts else None, max(ends) if ends else None, is_current)


def build_canonical(
    cluster: Cluster,
    members: list[Experience],
    merged: MergedContent,
    *,
    candidate_id: UUID,
) -> Experience:
    """Assemble the single canonical Experience for a cluster (pure)."""
    primary = members[cluster.members.index(cluster.primary)]
    start, end, is_current = _merge_dates(members)
    evidence = [ev for m in members for ev in m.evidence]
    sources = sorted({m.source for m in members if m.source})
    return Experience(
        candidate_id=candidate_id,
        kind=cluster.canonical_kind,
        org=cluster.canonical_org or primary.org,
        title=cluster.canonical_title or primary.title,
        location=primary.location,
        start_date=start,
        end_date=end,
        is_current=is_current,
        summary=merged.summary or primary.summary,
        detail=merged.detail or primary.detail,
        skills=merged.skills,
        tech=merged.tech,
        highlights=merged.highlights,
        handling_notes=merged.handling_notes,
        evidence=evidence,
        source=",".join(sources) if sources else "consolidated",
    )


def consolidate_experiences(
    repo: ProfileRepository, llm: LLMClient, candidate_id: UUID
) -> dict[str, int]:
    """Cluster + merge the candidate's experiences in place."""
    experiences = repo.list_experiences(candidate_id)
    if len(experiences) < 2:
        return {"before": len(experiences), "after": len(experiences)}

    plan = plan_clusters(llm, experiences)
    canonical: list[Experience] = []
    for cluster in plan.clusters:
        members = [experiences[i] for i in cluster.members]
        merged = merge_cluster(llm, members) if len(members) > 1 else _single(members[0], llm)
        canonical.append(build_canonical(cluster, members, merged, candidate_id=candidate_id))

    if not canonical:
        # Never delete the old set if we produced nothing to replace it with.
        return {"before": len(experiences), "after": len(experiences)}

    # Safe replacement: write the merged rows first, then retire the originals.
    # A failure mid-insert leaves the original experiences intact.
    for exp in canonical:
        repo.add_experience(exp)
    repo.delete_experiences_by_ids([e.id for e in experiences if e.id is not None])

    return {"before": len(experiences), "after": len(canonical)}


def _single(exp: Experience, llm: LLMClient) -> MergedContent:
    """A one-member cluster still needs its private guidance split out of detail."""
    return merge_cluster(llm, [exp])


# --- skills normalization ---
class NormalizedSkill(BaseModel):
    name: str
    category: str | None = None
    proficiency: str | None = None


class SkillSet(BaseModel):
    skills: list[NormalizedSkill] = Field(default_factory=list)


_SKILLS_SYSTEM = (
    "Normalize this skill list. De-duplicate (merge entries that are the same skill, "
    "e.g. 'pandas' listed twice, 'Data Analysis' under several categories). Assign "
    "each a single category from a compact, consistent set such as: Languages, "
    "AI/ML, Data, Web/Full-stack, Tools & DevOps, Leadership & PM, Communication, "
    "Domain Knowledge. Drop pure hobbies/sports (e.g. piano, fencing) — those are "
    "tracked as experiences, not skills. Keep real technical and professional skills."
)


def consolidate_skills(
    repo: ProfileRepository, llm: LLMClient, candidate_id: UUID
) -> dict[str, int]:
    """De-duplicate and re-categorize the candidate's skills in place."""
    skills = repo.list_skills(candidate_id)
    if len(skills) < 2:
        return {"before": len(skills), "after": len(skills)}

    listing = "\n".join(f"- {s.name} (category: {s.category})" for s in skills)
    result = llm.parse(
        task=Task.PARSE,
        system=_SKILLS_SYSTEM,
        messages=[{"role": "user", "content": f"Skills:\n{listing}"}],
        output_format=SkillSet,
    )

    repo.clear_skills(candidate_id)
    for ns in result.skills:
        repo.upsert_skill(
            Skill(
                candidate_id=candidate_id,
                name=ns.name,
                category=ns.category,
                proficiency=ns.proficiency,
            )
        )
    return {"before": len(skills), "after": len(result.skills)}
