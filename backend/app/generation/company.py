"""Company research: build (and cache) a grounded brief for cover letters."""

from __future__ import annotations

from uuid import UUID

from app.config import Task
from app.generation.models import CompanyBrief
from app.generation.repository import GenerationRepository
from app.llm import LLMClient

_SYSTEM = (
    "You research a company so a candidate can write a specific, grounded cover "
    "letter. Search the web for: (1) the company's mission and values; (2) two to "
    "four RECENT, concrete, verifiable signals — a product launch, initiative, "
    "funding, or news, with rough dates; (3) engineering culture or tech stack if "
    "findable. Then propose two to four concrete hooks the candidate could "
    "authentically reference, given their background. Output concise markdown. "
    "Include only facts you actually found; never fabricate. If a section has "
    "nothing solid, omit it."
)


def _prompt(
    company: str | None, role_title: str | None, jd_summary: str | None, profile: str
) -> str:
    return (
        f"Company: {company}\nRole: {role_title}\n"
        f"Job summary: {jd_summary}\n\n"
        f"Candidate background (for choosing relevant hooks):\n{profile}"
    )


def research_company(
    llm: LLMClient,
    repo: GenerationRepository,
    *,
    candidate_id: UUID,
    company: str | None,
    company_group: str,
    role_title: str | None,
    jd_summary: str | None,
    profile_summary: str,
    refresh: bool = False,
) -> CompanyBrief:
    """Return a cached brief for the company, researching it if needed."""
    if not refresh:
        cached = repo.get_company_brief(candidate_id, company_group)
        if cached is not None and cached.brief:
            return cached

    prompt = _prompt(company, role_title, jd_summary, profile_summary)
    try:
        brief_text = llm.research(
            task=Task.CONSOLIDATE,
            system=_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception:  # noqa: BLE001 - web search may be unavailable; degrade gracefully
        # Fallback: no web access — synthesize a thin brief from the JD alone.
        brief_text = llm.complete(
            task=Task.PARSE,
            system=(
                "Summarize what can be inferred about the company from the job "
                "posting alone (no web access). Be explicit that this is JD-only."
            ),
            messages=[{"role": "user", "content": prompt}],
        )

    brief = CompanyBrief(
        candidate_id=candidate_id,
        company_group=company_group,
        company=company,
        brief=brief_text,
    )
    return repo.set_company_brief(brief)
