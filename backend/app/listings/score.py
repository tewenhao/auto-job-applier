"""Score a listing against the candidate's preferences.

Hard filters first (deterministic: market mismatch, avoid-list), then an LLM
relevance score (0-100) with a short rationale.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.config import Task
from app.listings.models import Listing
from app.llm import LLMClient
from app.profile.models import Preferences


class ScoreResult(BaseModel):
    score: int = Field(ge=0, le=100)
    rationale: str
    matched: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)


def apply_hard_filters(listing: Listing, prefs: Preferences | None) -> str | None:
    """Return a filter reason if the listing should be dropped, else None."""
    if prefs is None:
        return None

    if prefs.location_markets and listing.market:
        if listing.market.lower() not in {m.lower() for m in prefs.location_markets}:
            return f"market '{listing.market}' not in preferred markets"

    if prefs.avoid:
        haystack = " ".join(
            p.lower()
            for p in (listing.company, listing.role_title, listing.domain, listing.jd_summary)
            if p
        )
        for term in prefs.avoid:
            if term.strip() and term.lower() in haystack:
                return f"matched avoid-list term '{term}'"
    return None


_SYSTEM = (
    "Score how well a job listing fits a candidate's stated preferences and "
    "background, from 0 (poor fit) to 100 (excellent fit). Weigh domain/role "
    "alignment most, then market/industry/company-size fit, then how well the "
    "candidate's experience matches the requirements. Give a one-sentence "
    "rationale and list concrete matched and missing points. Be discerning — "
    "reserve 80+ for genuinely strong fits."
)


def score_listing(
    llm: LLMClient,
    listing: Listing,
    prefs: Preferences | None,
    profile_summary: str,
) -> ScoreResult:
    prefs_text = _format_prefs(prefs)
    reqs = "\n".join(f"- {r}" for r in listing.requirements) or "(none listed)"
    user = (
        f"# Candidate preferences\n{prefs_text}\n\n"
        f"# Candidate background (summary)\n{profile_summary}\n\n"
        f"# Listing\n"
        f"Company: {listing.company}\nRole: {listing.role_title}\n"
        f"Domain: {listing.domain} | Market: {listing.market} | Location: {listing.location}\n"
        f"Summary: {listing.jd_summary}\nRequirements:\n{reqs}"
    )
    return llm.parse(
        task=Task.PARSE,
        system=_SYSTEM,
        messages=[{"role": "user", "content": user}],
        output_format=ScoreResult,
    )


def _format_prefs(prefs: Preferences | None) -> str:
    if prefs is None:
        return "(no preferences set)"
    lines = []
    for label, values in (
        ("Role types", prefs.role_types),
        ("Domains", prefs.domains),
        ("Industries", prefs.industries),
        ("Company sizes", prefs.company_sizes),
        ("Markets", prefs.location_markets),
        ("Avoid", prefs.avoid),
    ):
        if values:
            lines.append(f"- {label}: {', '.join(values)}")
    return "\n".join(lines) or "(no preferences set)"
