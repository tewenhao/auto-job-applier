"""FastAPI app: the dashboard's single backend.

Reads (applications, listings, ranking) and actions (generate / steer / approve)
all delegate to the same repositories and pipeline the CLI uses.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app.api import service
from app.api.deps import (
    get_gen_repo,
    get_listing_ingestor,
    get_listings_repo,
    get_profile_repo,
)
from app.api.errors import Problem, as_http, diagnose, generic
from app.api.schemas import (
    ApplicationDetail,
    ApplicationSummary,
    ApproveRequest,
    CommitEntryRequest,
    CommitEntryResponse,
    CoverLetterUpdate,
    DraftResponse,
    EditEntryRequest,
    GenerateRequest,
    IngestRequest,
    IngestResult,
    InterviewRequest,
    InterviewStepResponse,
    InterviewTurn,
    ListingSummary,
    MasterDocEntry,
    Preferences,
    PreferencesUpdate,
    RegenerateRequest,
    RescoreResult,
    ResumeUpdate,
)
from app.generation.models import Application, ApplicationStatus
from app.generation.naming import COVER_LETTER, RESUME, document_filename
from app.generation.repository import GenerationRepository
from app.generation.resume import RESUME_GUIDANCE_KEY
from app.listings.ingest import ListingIngestor
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

log = logging.getLogger(__name__)


# --- errors ------------------------------------------------------------------
# Every failure leaves here in one shape — {"detail": {code, title, message,
# fixes}} — so the dashboard has exactly one thing to render, and always has
# something to suggest. Without these handlers an unexpected failure reaches the
# browser as "500: Internal Server Error", which tells the user nothing.
def _problem_response(problem: Problem) -> JSONResponse:
    return JSONResponse(status_code=problem.status, content={"detail": problem.as_detail()})


@app.exception_handler(HTTPException)
async def _handle_http_exception(_request: Request, exc: HTTPException) -> JSONResponse:
    """Endpoints may raise a structured Problem or a plain string; normalise both."""
    if isinstance(exc.detail, dict) and "code" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return _problem_response(generic(exc.status_code, str(exc.detail)))


@app.exception_handler(RequestValidationError)
async def _handle_validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
    fields = ", ".join(".".join(str(p) for p in e["loc"][1:]) or "body" for e in exc.errors())
    return _problem_response(
        Problem(
            code="invalid_request",
            title="The form couldn't be submitted",
            message=f"The request was missing or malformed in: {fields}.",
            fixes=[
                "Check the fields above and try again.",
                "If the page looks stale, reload it — the UI may be out of date with the API.",
            ],
            status=422,
        )
    )


@app.exception_handler(Exception)
async def _handle_unexpected(_request: Request, exc: Exception) -> JSONResponse:
    """Anything not raised deliberately: diagnose it rather than return a bare 500."""
    log.exception("Unhandled error serving the dashboard")
    return _problem_response(diagnose(exc))


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
    return Preferences.build(profiles.get_preferences(candidate.id))


@app.put("/api/preferences", response_model=Preferences)
def update_preferences(
    body: PreferencesUpdate,
    profiles: ProfileRepository = Depends(get_profile_repo),
) -> Preferences:
    candidate = profiles.get_or_create_default_candidate()
    assert candidate.id is not None
    prefs = profiles.get_preferences(candidate.id) or ProfilePreferences(candidate_id=candidate.id)

    if body.resume_guidance is not None:
        text = body.resume_guidance.strip()
        if text:
            prefs.extra = {**prefs.extra, RESUME_GUIDANCE_KEY: text}
        else:  # empty clears the standing guidance
            prefs.extra = {k: v for k, v in prefs.extra.items() if k != RESUME_GUIDANCE_KEY}

    # Same semantics as `ajp preferences set`: a field you send replaces that
    # list outright; a field you omit is left exactly as it was.
    for name in PreferencesUpdate.LIST_FIELDS:
        value = getattr(body, name)
        if value is not None:
            setattr(prefs, name, [v.strip() for v in value if v.strip()])

    return Preferences.build(profiles.set_preferences(prefs))


@app.get("/api/profile")
def get_profile(profiles: ProfileRepository = Depends(get_profile_repo)) -> dict[str, str]:
    """The whole profile as readable Markdown (same view as `ajp profile show`)."""
    from app.profile.markdown import profile_to_markdown

    candidate = profiles.get_or_create_default_candidate()
    assert candidate.id is not None
    return {"markdown": profile_to_markdown(profiles.get_master_profile(candidate.id))}


@app.get("/api/profile/entries", response_model=list[MasterDocEntry])
def list_profile_entries() -> list[MasterDocEntry]:
    """The master-doc's entries, so they can be reviewed and edited."""
    try:
        return [MasterDocEntry(**e) for e in service.list_master_doc_entries()]
    except FileNotFoundError as exc:
        # diagnose() knows this one: it names MASTER_DOC_PATH and the fact that
        # a relative path resolves from the repo root, which is the usual trip-up.
        raise as_http(diagnose(exc)) from exc


@app.put("/api/profile/entries")
def edit_profile_entry(
    body: EditEntryRequest,
    profiles: ProfileRepository = Depends(get_profile_repo),
) -> CommitEntryResponse:
    """Edit or delete one master-doc entry, then re-ingest."""
    candidate = profiles.get_or_create_default_candidate()
    assert candidate.id is not None
    try:
        path, summary = service.edit_master_doc_entry(
            body.heading, body.markdown, candidate_id=candidate.id
        )
    except FileNotFoundError as exc:
        # diagnose() knows this one: it names MASTER_DOC_PATH and the fact that
        # a relative path resolves from the repo root, which is the usual trip-up.
        raise as_http(diagnose(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return CommitEntryResponse(master_doc_path=path, ingested=summary)


@app.post("/api/profile/ingest")
def ingest_profile_document(
    file: UploadFile = File(...),
    source_type: str = Form("resume"),
    profiles: ProfileRepository = Depends(get_profile_repo),
) -> dict[str, object]:
    """Ingest an uploaded resume / essay / cover letter / master-doc.

    The same pipeline as `ajp ingest`, with dedup on, so re-uploading a document
    updates rather than duplicating. LinkedIn exports are deliberately not here:
    they are large zips better handled by the CLI.
    """
    import shutil
    import tempfile
    from pathlib import Path as _Path

    from app.ingestion import Ingestor
    from app.ingestion.documents import SUPPORTED_SUFFIXES
    from app.llm import LLMClient
    from app.profile.models import SourceType

    try:
        kind = SourceType(source_type)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=f"Unknown source type '{source_type}'."
        ) from exc
    if kind is SourceType.LINKEDIN_EXPORT:
        raise HTTPException(
            status_code=400, detail="Use `ajp ingest --linkedin` for LinkedIn exports."
        )

    name = _Path(file.filename or "upload.txt").name
    if _Path(name).suffix.lower() not in SUPPORTED_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Accepted: {', '.join(sorted(SUPPORTED_SUFFIXES))}.",
        )

    candidate = profiles.get_or_create_default_candidate()
    assert candidate.id is not None
    with tempfile.TemporaryDirectory() as tmp:
        dest = _Path(tmp) / name
        with dest.open("wb") as out:
            shutil.copyfileobj(file.file, out)
        summary = Ingestor(profiles, LLMClient()).ingest_document(
            dest, kind, candidate_id=candidate.id, dedup=True
        )
    return {"filename": name, "source_type": kind.value, "summary": summary}


@app.post("/api/profile/ingest/github")
def ingest_profile_github(
    profiles: ProfileRepository = Depends(get_profile_repo),
) -> dict[str, object]:
    """Pull GitHub repo metadata, using GITHUB_USERNAME / GITHUB_TOKEN."""
    from app.config import get_settings
    from app.ingestion import Ingestor
    from app.llm import LLMClient

    settings = get_settings()
    if not settings.github_username:
        raise HTTPException(status_code=400, detail="GITHUB_USERNAME is not set in .env.")
    candidate = profiles.get_or_create_default_candidate()
    assert candidate.id is not None
    summary = Ingestor(profiles, LLMClient()).ingest_github(
        settings.github_username, settings.github_token or None, candidate_id=candidate.id
    )
    return {"username": settings.github_username, "summary": summary}


@app.get("/api/profile/interview", response_model=InterviewStepResponse)
def profile_interview_state(
    profiles: ProfileRepository = Depends(get_profile_repo),
) -> InterviewStepResponse:
    """Any unfinished interview, so the page can resume it."""
    from app.profile.interview import load_transcript

    candidate = profiles.get_or_create_default_candidate()
    assert candidate.id is not None
    session = profiles.get_open_interview_session(candidate.id)
    if session is None:
        return InterviewStepResponse()
    turns = load_transcript(profiles, session.id)
    return InterviewStepResponse(
        session_id=session.id,
        transcript=[InterviewTurn(**t) for t in turns],
        question=turns[-1]["content"] if turns and turns[-1]["role"] == "assistant" else None,
        resumed=True,
    )


@app.post("/api/profile/interview", response_model=InterviewStepResponse)
def profile_interview(
    body: InterviewRequest,
    profiles: ProfileRepository = Depends(get_profile_repo),
) -> InterviewStepResponse:
    """Record the answer (if any) and return the next question.

    The transcript is stored, so the interview survives a reload and can be
    continued from `ajp interview`.
    """
    from app.llm import LLMClient
    from app.profile.interview import load_transcript, next_step, open_or_resume, record_turn
    from app.profile.markdown import profile_to_markdown

    candidate = profiles.get_or_create_default_candidate()
    assert candidate.id is not None
    session, resumed = open_or_resume(profiles, candidate.id, resume=not body.fresh)
    transcript = load_transcript(profiles, session.id)

    if body.answer and body.answer.strip():
        record_turn(profiles, session, "user", body.answer.strip())
        transcript.append({"role": "user", "content": body.answer.strip()})

    existing = profile_to_markdown(profiles.get_master_profile(candidate.id))
    step = next_step(LLMClient(), transcript, profile_markdown=existing)
    if not step.ready and step.question:
        record_turn(profiles, session, "assistant", step.question)
        transcript.append({"role": "assistant", "content": step.question})

    return InterviewStepResponse(
        session_id=session.id,
        transcript=[InterviewTurn(**t) for t in transcript],
        question=step.question,
        ready=step.ready,
        missing=step.missing,
        resumed=resumed,
    )


@app.post("/api/profile/interview/draft", response_model=DraftResponse)
def profile_interview_draft(
    body: InterviewRequest,
    profiles: ProfileRepository = Depends(get_profile_repo),
) -> DraftResponse:
    """Draft the master-doc entry from the stored transcript, for review."""
    from app.llm import LLMClient
    from app.profile.interview import draft_entry, load_transcript

    candidate = profiles.get_or_create_default_candidate()
    assert candidate.id is not None
    session = profiles.get_open_interview_session(candidate.id)
    if session is None:
        raise HTTPException(status_code=400, detail="No interview in progress.")
    drafted = draft_entry(LLMClient(), load_transcript(profiles, session.id))
    return DraftResponse(section=drafted.section, markdown=drafted.markdown)


@app.post("/api/profile/entries", response_model=CommitEntryResponse)
def commit_profile_entry(
    body: CommitEntryRequest,
    profiles: ProfileRepository = Depends(get_profile_repo),
) -> CommitEntryResponse:
    """Write the reviewed entry into the master-doc and re-ingest it."""
    candidate = profiles.get_or_create_default_candidate()
    assert candidate.id is not None
    try:
        path, summary = service.commit_master_doc_entry(
            body.section, body.markdown, candidate_id=candidate.id
        )
    except FileNotFoundError as exc:
        # diagnose() knows this one: it names MASTER_DOC_PATH and the fact that
        # a relative path resolves from the repo root, which is the usual trip-up.
        raise as_http(diagnose(exc)) from exc
    if body.session_id is not None:
        profiles.complete_interview_session(body.session_id)
    return CommitEntryResponse(master_doc_path=path, ingested=summary)


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


@app.post("/api/listings/rescore", response_model=RescoreResult)
def rescore_listings(
    ingestor: ListingIngestor = Depends(get_listing_ingestor),
    profiles: ProfileRepository = Depends(get_profile_repo),
) -> RescoreResult:
    """Re-score stored listings against the current preferences.

    Nothing is fetched or re-parsed. Listings already chosen, dismissed or
    applied to keep their status; one that the current hard filters would now
    drop comes back flagged instead.
    """
    candidate = profiles.get_or_create_default_candidate()
    assert candidate.id is not None
    results = ingestor.rescore(candidate.id)
    return RescoreResult(
        total=len(results),
        changed=sum(1 for r in results if r.score_changed or r.status_changed),
        flagged=[ListingSummary.build(r.listing, None) for r in results if r.flagged],
    )


@app.post("/api/listings/ingest", response_model=IngestResult)
def ingest_listing(
    body: IngestRequest,
    ingestor: ListingIngestor = Depends(get_listing_ingestor),
    profiles: ProfileRepository = Depends(get_profile_repo),
) -> IngestResult:
    """Ingest one URL (expanding boards) or pasted JD text.

    Slow: fetches, parses with the LLM, and scores. A failure is reported in
    the body so the dashboard can render it as a per-URL skip.
    """
    if not body.url and not body.text:
        raise HTTPException(status_code=400, detail="Provide a url or text.")
    candidate = profiles.get_or_create_default_candidate()
    assert candidate.id is not None
    try:
        if body.url:
            listings = ingestor.ingest_url(body.url, candidate_id=candidate.id)
        else:
            listings = [ingestor.ingest_manual(candidate_id=candidate.id, text=body.text)]
    except Exception as exc:  # noqa: BLE001 - surfaced to the user as a skip
        return IngestResult(url=body.url, error=str(exc))
    return IngestResult(
        url=body.url,
        listings=[ListingSummary.build(x, None) for x in listings],
        expanded=len(listings) > 1,
    )


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


def _download_name(
    application: Application,
    kind: str,
    listings: ListingRepository,
    profiles: ProfileRepository,
) -> str:
    """``<candidate>-<company>-<kind>.pdf``, so a folder of downloads is
    self-explanatory."""
    listing = listings.get(application.listing_id)
    candidate = profiles.get_candidate(application.candidate_id)
    return document_filename(
        candidate_name=candidate.full_name if candidate else None,
        company=listing.company if listing else None,
        kind=kind,
    )


@app.get("/api/applications/{app_id}/resume.pdf")
def resume_pdf(
    app_id: UUID,
    gen: GenerationRepository = Depends(get_gen_repo),
    listings: ListingRepository = Depends(get_listings_repo),
    profiles: ProfileRepository = Depends(get_profile_repo),
) -> FileResponse:
    application = _load(app_id, gen)
    pdf = service.ensure_pdf(application)
    if pdf is None:
        raise HTTPException(
            status_code=404, detail="No PDF (no LaTeX toolchain, or resume not generated)"
        )
    return FileResponse(
        pdf,
        media_type="application/pdf",
        filename=_download_name(application, RESUME, listings, profiles),
    )


@app.get("/api/applications/{app_id}/cover_letter.pdf")
def cover_letter_pdf(
    app_id: UUID,
    gen: GenerationRepository = Depends(get_gen_repo),
    listings: ListingRepository = Depends(get_listings_repo),
    profiles: ProfileRepository = Depends(get_profile_repo),
) -> FileResponse:
    application = _load(app_id, gen)
    pdf = service.ensure_cover_letter_pdf(application)
    if pdf is None:
        raise HTTPException(
            status_code=404,
            detail="No PDF (no LaTeX toolchain, or no cover letter generated)",
        )
    return FileResponse(
        pdf,
        media_type="application/pdf",
        filename=_download_name(application, COVER_LETTER, listings, profiles),
    )
