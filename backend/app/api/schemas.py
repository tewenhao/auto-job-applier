"""Request/response shapes for the dashboard API."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from app.generation.models import Application
from app.generation.resume import TailoredResume
from app.listings.models import Listing


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
    steer: str | None = None  # the standing/per-application steer last used

    @classmethod
    def build(cls, app: Application, listing: Listing | None) -> ApplicationDetail:
        from pathlib import Path

        resume = TailoredResume.model_validate(app.resume_content) if app.resume_content else None
        pdf = app.resume_pdf_path
        return cls(
            id=app.id,  # type: ignore[arg-type]
            listing_id=app.listing_id,
            company=listing.company if listing else None,
            role_title=listing.role_title if listing else None,
            status=str(app.status),
            cover_letter=app.cover_letter,
            resume=resume,
            resume_pdf_available=bool(pdf and Path(pdf).exists()),
            steer=app.meta.get("steer"),
        )


class RegenerateRequest(BaseModel):
    steer: str | None = None
    refresh_company: bool = False
    max_pages: int = Field(default=1, ge=1, le=3)


class ApproveRequest(BaseModel):
    submitted: bool = False


class GenerateRequest(BaseModel):
    listing_id: UUID
    steer: str | None = None
    max_pages: int = Field(default=1, ge=1, le=3)
