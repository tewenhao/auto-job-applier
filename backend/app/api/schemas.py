"""Request/response shapes for the dashboard API."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from app.generation.models import Application
from app.generation.resume import TailoredResume
from app.listings.models import Listing


class ListingSummary(BaseModel):
    id: UUID
    company: str | None = None
    role_title: str | None = None
    location: str | None = None
    domain: str | None = None
    market: str | None = None
    score: int | None = None
    status: str
    url: str | None = None  # original job-portal posting
    application_id: UUID | None = None  # existing draft for this listing, if any

    @classmethod
    def build(cls, listing: Listing, application_id: UUID | None) -> ListingSummary:
        return cls(
            id=listing.id,  # type: ignore[arg-type]
            company=listing.company,
            role_title=listing.role_title,
            location=listing.location,
            domain=listing.domain,
            market=listing.market,
            score=listing.score,
            status=str(listing.status),
            url=listing.url,
            application_id=application_id,
        )


class ApplicationSummary(BaseModel):
    id: UUID
    listing_id: UUID
    company: str | None = None
    role_title: str | None = None
    status: str

    @classmethod
    def build(cls, app: Application, listing: Listing | None) -> ApplicationSummary:
        return cls(
            id=app.id,  # type: ignore[arg-type]
            listing_id=app.listing_id,
            company=listing.company if listing else None,
            role_title=listing.role_title if listing else None,
            status=str(app.status),
        )


class ApplicationDetail(BaseModel):
    id: UUID
    listing_id: UUID
    company: str | None = None
    role_title: str | None = None
    status: str
    cover_letter: str | None = None
    resume: TailoredResume | None = None  # includes the ranking
    resume_pdf_available: bool = False
    cover_letter_pdf_available: bool = False
    steer: str | None = None  # the standing/per-application steer last used
    posting_url: str | None = None  # original job-portal posting

    @classmethod
    def build(cls, app: Application, listing: Listing | None) -> ApplicationDetail:
        from pathlib import Path

        from app.api.service import COVER_LETTER_PDF_KEY

        resume = TailoredResume.model_validate(app.resume_content) if app.resume_content else None
        pdf = app.resume_pdf_path
        cl_pdf = app.meta.get(COVER_LETTER_PDF_KEY)
        return cls(
            id=app.id,  # type: ignore[arg-type]
            listing_id=app.listing_id,
            company=listing.company if listing else None,
            role_title=listing.role_title if listing else None,
            posting_url=listing.url if listing else None,
            status=str(app.status),
            cover_letter=app.cover_letter,
            resume=resume,
            resume_pdf_available=bool(pdf and Path(pdf).exists()),
            cover_letter_pdf_available=bool(cl_pdf and Path(cl_pdf).exists()),
            steer=app.meta.get("steer"),
        )


class RegenerateRequest(BaseModel):
    steer: str | None = None
    refresh_company: bool = False
    max_pages: int = Field(default=1, ge=1, le=3)


class ApproveRequest(BaseModel):
    submitted: bool = False


class ResumeUpdate(BaseModel):
    resume: TailoredResume  # the hand-edited resume to persist and re-render
    max_pages: int = Field(default=1, ge=1, le=3)


class CoverLetterUpdate(BaseModel):
    cover_letter: str  # the hand-edited cover-letter text to persist and re-render


class GenerateRequest(BaseModel):
    listing_id: UUID
    steer: str | None = None
    max_pages: int = Field(default=1, ge=1, le=3)


class Preferences(BaseModel):
    # Standing résumé-generation guidance: what to prioritise on every resume.
    resume_guidance: str | None = None


class PreferencesUpdate(BaseModel):
    resume_guidance: str = ""  # empty clears the standing guidance


class IngestRequest(BaseModel):
    """One URL (or pasted JD text) to ingest. Kept to a single item per request
    so the dashboard can report progress as each one completes."""

    url: str | None = None
    text: str | None = None


class IngestResult(BaseModel):
    url: str | None = None
    listings: list[ListingSummary] = Field(default_factory=list)
    # A board/index URL that expanded into several roles.
    expanded: bool = False
    # Ingestion failures are per-URL outcomes (like the CLI's "skip"), not
    # server errors, so they come back in the body rather than as a 4xx.
    error: str | None = None


class InterviewTurn(BaseModel):
    role: str  # "assistant" (a question) or "user" (an answer)
    content: str


class InterviewRequest(BaseModel):
    """One step of a saved interview. The server owns the transcript, so a
    session can be resumed later (or continued from the CLI)."""

    answer: str | None = None  # the user's reply to the last question
    fresh: bool = False  # abandon any unfinished session and start over


class InterviewStepResponse(BaseModel):
    session_id: UUID | None = None
    transcript: list[InterviewTurn] = Field(default_factory=list)
    question: str | None = None
    ready: bool = False
    missing: str | None = None
    resumed: bool = False


class DraftResponse(BaseModel):
    section: str = "experience"
    markdown: str


class CommitEntryRequest(BaseModel):
    """The reviewed entry to write. The user can edit `markdown` first — the
    master-doc is theirs, so nothing is written without them seeing it."""

    section: str = "experience"
    markdown: str
    session_id: UUID | None = None  # marked complete once the entry is saved


class CommitEntryResponse(BaseModel):
    master_doc_path: str
    ingested: str  # a human-readable summary of what the re-ingest found


class MasterDocEntry(BaseModel):
    section: str
    heading: str
    markdown: str


class EditEntryRequest(BaseModel):
    """Replace an entry, identified by its heading line. An empty `markdown`
    deletes it — the entry is removed from the master-doc itself."""

    heading: str
    markdown: str = ""
