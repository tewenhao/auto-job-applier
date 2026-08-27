"""FastAPI app: the dashboard's single backend.

Reads (applications, listings, ranking) and actions (generate / steer / approve)
all delegate to the same repositories and pipeline the CLI uses.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.api import service
from app.api.deps import get_gen_repo, get_listings_repo, get_profile_repo
from app.api.schemas import (
    ApplicationDetail,
    ApplicationSummary,
    ApproveRequest,
    CoverLetterUpdate,
    GenerateRequest,
    ListingSummary,
    Preferences,
    PreferencesUpdate,
    RegenerateRequest,
    ResumeUpdate,
)
from app.generation.models import Application, ApplicationStatus
from app.generation.repository import GenerationRepository
from app.generation.resume import RESUME_GUIDANCE_KEY
from app.listings.repository import ListingRepository
from app.profile.models import Preferences as ProfilePreferences
from app.profile.repository import ProfileRepository

app = FastAPI(title="auto-job-applier", version="0.1.0")

# The Next.js dev server runs on :3000; allow it (single-user local tool).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _load(app_id: UUID, gen: GenerationRepository) -> Application:
    application = gen.get_application(app_id)
    if application is None:
        raise HTTPException(status_code=404, detail="No application with that id")
    return application


@app.get("/api/preferences", response_model=Preferences)
def get_preferences(
    profiles: ProfileRepository = Depends(get_profile_repo),
) -> Preferences:
    candidate = profiles.get_or_create_default_candidate()
    assert candidate.id is not None
    prefs = profiles.get_preferences(candidate.id)
    guidance = prefs.extra.get(RESUME_GUIDANCE_KEY) if prefs else None
    return Preferences(resume_guidance=guidance or None)


@app.put("/api/preferences", response_model=Preferences)
def update_preferences(
    body: PreferencesUpdate,
    profiles: ProfileRepository = Depends(get_profile_repo),
) -> Preferences:
    candidate = profiles.get_or_create_default_candidate()
    assert candidate.id is not None
    prefs = profiles.get_preferences(candidate.id) or ProfilePreferences(candidate_id=candidate.id)
    text = body.resume_guidance.strip()
    if text:
        prefs.extra = {**prefs.extra, RESUME_GUIDANCE_KEY: text}
    else:  # empty clears the standing guidance
        prefs.extra = {k: v for k, v in prefs.extra.items() if k != RESUME_GUIDANCE_KEY}
    saved = profiles.set_preferences(prefs)
    return Preferences(resume_guidance=saved.extra.get(RESUME_GUIDANCE_KEY) or None)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/listings", response_model=list[ListingSummary])
def list_listings(
    gen: GenerationRepository = Depends(get_gen_repo),
    listings: ListingRepository = Depends(get_listings_repo),
    profiles: ProfileRepository = Depends(get_profile_repo),
) -> list[ListingSummary]:
    candidate = profiles.get_or_create_default_candidate()
    assert candidate.id is not None
    # One query for the candidate's applications; map listing_id -> application id
    # so each listing can show "generate" vs. "view draft".
    apps_by_listing = {a.listing_id: a.id for a in gen.list_applications(candidate.id)}
    return [
        ListingSummary.build(lst, apps_by_listing.get(lst.id) if lst.id else None)
        for lst in listings.list(candidate.id)
    ]


@app.get("/api/applications", response_model=list[ApplicationSummary])
def list_applications(
    gen: GenerationRepository = Depends(get_gen_repo),
    listings: ListingRepository = Depends(get_listings_repo),
    profiles: ProfileRepository = Depends(get_profile_repo),
) -> list[ApplicationSummary]:
    candidate = profiles.get_or_create_default_candidate()
    assert candidate.id is not None
    out: list[ApplicationSummary] = []
    for a in gen.list_applications(candidate.id):
        out.append(ApplicationSummary.build(a, listings.get(a.listing_id)))
    return out


@app.get("/api/applications/{app_id}", response_model=ApplicationDetail)
def get_application(
    app_id: UUID,
    gen: GenerationRepository = Depends(get_gen_repo),
    listings: ListingRepository = Depends(get_listings_repo),
) -> ApplicationDetail:
    application = _load(app_id, gen)
    return ApplicationDetail.build(application, listings.get(application.listing_id))


@app.post("/api/applications/{app_id}/approve", response_model=ApplicationDetail)
def approve_application(
    app_id: UUID,
    body: ApproveRequest,
    gen: GenerationRepository = Depends(get_gen_repo),
    listings: ListingRepository = Depends(get_listings_repo),
) -> ApplicationDetail:
    application = _load(app_id, gen)
    status = ApplicationStatus.SUBMITTED if body.submitted else ApplicationStatus.APPROVED
    application.status = status.value  # type: ignore[assignment]  # use_enum_values stores the str
    saved = gen.upsert_application(application)
    return ApplicationDetail.build(saved, listings.get(saved.listing_id))


@app.post("/api/applications/{app_id}/regenerate", response_model=ApplicationDetail)
def regenerate_application(
    app_id: UUID,
    body: RegenerateRequest,
    listings: ListingRepository = Depends(get_listings_repo),
) -> ApplicationDetail:
    # Slow: runs the LLM pipeline + LaTeX. The dashboard shows a loading state.
    try:
        saved = service.regenerate(
            app_id,
            steer=body.steer,
            refresh_company=body.refresh_company,
            max_pages=body.max_pages,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="No application with that id") from exc
    except ValueError as exc:
        # e.g. the model's structured output was truncated — a clean, retryable
        # message beats a 500 with a raw traceback.
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ApplicationDetail.build(saved, listings.get(saved.listing_id))


@app.put("/api/applications/{app_id}/resume", response_model=ApplicationDetail)
def save_resume(
    app_id: UUID,
    body: ResumeUpdate,
    listings: ListingRepository = Depends(get_listings_repo),
) -> ApplicationDetail:
    # Deterministic: persist the hand-edited resume and re-render (no LLM).
    try:
        saved = service.save_resume(app_id, body.resume, max_pages=body.max_pages)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="No application with that id") from exc
    return ApplicationDetail.build(saved, listings.get(saved.listing_id))


@app.put("/api/applications/{app_id}/cover_letter", response_model=ApplicationDetail)
def save_cover_letter(
    app_id: UUID,
    body: CoverLetterUpdate,
    listings: ListingRepository = Depends(get_listings_repo),
) -> ApplicationDetail:
    # Deterministic: persist the hand-edited cover letter and re-render (no LLM).
    try:
        saved = service.save_cover_letter(app_id, body.cover_letter)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="No application with that id") from exc
    return ApplicationDetail.build(saved, listings.get(saved.listing_id))


@app.post("/api/generate", response_model=ApplicationDetail)
def generate(
    body: GenerateRequest,
    listings: ListingRepository = Depends(get_listings_repo),
) -> ApplicationDetail:
    if listings.get(body.listing_id) is None:
        raise HTTPException(status_code=404, detail="No listing with that id")
    try:
        saved = service.generate_new(body.listing_id, steer=body.steer, max_pages=body.max_pages)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ApplicationDetail.build(saved, listings.get(saved.listing_id))


@app.get("/api/applications/{app_id}/resume.pdf")
def resume_pdf(
    app_id: UUID,
    gen: GenerationRepository = Depends(get_gen_repo),
) -> FileResponse:
    application = _load(app_id, gen)
    pdf = service.ensure_pdf(application)
    if pdf is None:
        raise HTTPException(
            status_code=404, detail="No PDF (no LaTeX toolchain, or resume not generated)"
        )
    return FileResponse(pdf, media_type="application/pdf", filename="resume.pdf")


@app.get("/api/applications/{app_id}/cover_letter.pdf")
def cover_letter_pdf(
    app_id: UUID,
    gen: GenerationRepository = Depends(get_gen_repo),
) -> FileResponse:
    application = _load(app_id, gen)
    pdf = service.ensure_cover_letter_pdf(application)
    if pdf is None:
        raise HTTPException(
            status_code=404,
            detail="No PDF (no LaTeX toolchain, or no cover letter generated)",
        )
    return FileResponse(pdf, media_type="application/pdf", filename="cover_letter.pdf")
