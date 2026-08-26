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
    GenerateRequest,
    RegenerateRequest,
)
from app.generation.models import Application, ApplicationStatus
from app.generation.repository import GenerationRepository
from app.listings.repository import ListingRepository
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


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


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
    return ApplicationDetail.build(saved, listings.get(saved.listing_id))


@app.post("/api/generate", response_model=ApplicationDetail)
def generate(
    body: GenerateRequest,
    listings: ListingRepository = Depends(get_listings_repo),
) -> ApplicationDetail:
    if listings.get(body.listing_id) is None:
        raise HTTPException(status_code=404, detail="No listing with that id")
    saved = service.generate_new(body.listing_id, steer=body.steer, max_pages=body.max_pages)
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
