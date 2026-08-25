"""Orchestrate application generation for a chosen listing."""

from __future__ import annotations

from uuid import UUID

from app.generation.company import research_company
from app.generation.cover_letter import generate_cover_letter
from app.generation.latex import render_resume
from app.generation.models import Application
from app.generation.repository import GenerationRepository
from app.generation.resume import resume_bullet_texts, tailor_resume
from app.listings.models import normalize_company
from app.listings.repository import ListingRepository
from app.llm import LLMClient
from app.profile.repository import ProfileRepository


def _profile_summary(profile) -> str:  # type: ignore[no-untyped-def]
    exps = [f"- {e.title} @ {e.org}" for e in profile.experiences[:20] if e.title]
    skills = ", ".join(s.name for s in profile.skills[:30])
    return "Experiences:\n" + "\n".join(exps) + "\n\nSkills: " + skills


def generate_application(listing_id: UUID, *, refresh_company: bool = False) -> Application:
    """Research the company and generate a cover letter for a listing."""
    listings = ListingRepository()
    gen = GenerationRepository()
    profiles = ProfileRepository()
    llm = LLMClient()

    listing = listings.get(listing_id)
    if listing is None:
        raise ValueError(f"No listing with id {listing_id}")
    candidate_id = listing.candidate_id

    profile = profiles.get_master_profile(candidate_id)
    voice = profiles.get_voice_profile(candidate_id)
    samples = profiles.list_writing_samples(candidate_id)

    brief = research_company(
        llm,
        gen,
        candidate_id=candidate_id,
        company=listing.company,
        company_group=listing.company_group or normalize_company(listing.company) or "unknown",
        role_title=listing.role_title,
        jd_summary=listing.jd_summary,
        profile_summary=_profile_summary(profile),
        refresh=refresh_company,
    )

    # Tailor the resume first, so its bullets can steer the cover letter away
    # from restating them.
    resume = tailor_resume(llm, listing=listing, profile=profile, brief=brief)
    resume_tex = render_resume(resume, profile.candidate)

    letter = generate_cover_letter(
        llm,
        listing=listing,
        profile=profile,
        voice=voice,
        samples=samples,
        brief=brief,
        resume_points=resume_bullet_texts(resume),
    )

    application = gen.get_application_for_listing(candidate_id, listing_id) or Application(
        candidate_id=candidate_id, listing_id=listing_id
    )
    application.cover_letter = letter
    application.resume_content = resume.model_dump(mode="json")
    application.resume_tex = resume_tex
    return gen.upsert_application(application)
