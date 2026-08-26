"""Derive candidate job preferences from the master profile.

The master doc is rich with preference signal (domains, target markets, the
tech-for-good lean, the deliberate quant caveat), so we draft preferences from
it with the model, then let the user edit them — rather than making them type
everything from scratch.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from app.config import Task
from app.llm import LLMClient
from app.profile.markdown import profile_to_markdown
from app.profile.models import MasterProfile, Preferences


class PreferencesDraft(BaseModel):
    role_types: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)  # swe | ml | quant | product | data | ...
    industries: list[str] = Field(default_factory=list)
    company_sizes: list[str] = Field(default_factory=list)  # startup | midsize | large | ...
    location_markets: list[str] = Field(default_factory=list)  # uk | sg | us | cn
    avoid: list[str] = Field(default_factory=list)


_SYSTEM = (
    "Infer the candidate's job-search preferences from their profile, for filtering "
    "and scoring internship listings. Fill: role_types, domains (from swe, ml, quant, "
    "product, data, hardware, design), industries, company_sizes (startup/midsize/"
    "large), location_markets (uk, sg, us, cn), and avoid (things to steer away from). "
    "Read the handling notes and any stated leanings carefully — e.g. a tech-for-good "
    "orientation, or a deliberate note about how to treat quant/finance. Only include "
    "what the profile actually supports; leave a list empty rather than guessing."
)


def derive_preferences(llm: LLMClient, profile: MasterProfile) -> PreferencesDraft:
    """Draft preferences from the assembled profile (includes handling notes)."""
    profile_md = profile_to_markdown(profile, include_handling_notes=True)
    return llm.parse(
        task=Task.CONSOLIDATE,
        system=_SYSTEM,
        messages=[{"role": "user", "content": f"# Candidate profile\n\n{profile_md}"}],
        output_format=PreferencesDraft,
    )


def draft_to_preferences(draft: PreferencesDraft, *, candidate_id: UUID) -> Preferences:
    return Preferences(
        candidate_id=candidate_id,
        role_types=draft.role_types,
        domains=draft.domains,
        industries=draft.industries,
        company_sizes=draft.company_sizes,
        location_markets=draft.location_markets,
        avoid=draft.avoid,
    )
