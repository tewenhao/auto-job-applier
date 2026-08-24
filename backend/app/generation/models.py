"""Typed models for generated applications and cached company research."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ApplicationStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    SUBMITTED = "submitted"


class CompanyBrief(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: UUID | None = None
    candidate_id: UUID
    company_group: str
    company: str | None = None
    brief: str | None = None
    hooks: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def to_row(self) -> dict[str, Any]:
        return self.model_dump(
            mode="json", exclude_none=True, exclude={"created_at", "updated_at"}
        )

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> CompanyBrief:
        return cls.model_validate(row)


class Application(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: UUID | None = None
    candidate_id: UUID
    listing_id: UUID
    status: ApplicationStatus = ApplicationStatus.DRAFT
    cover_letter: str | None = None
    resume_content: dict[str, Any] | None = None
    resume_tex: str | None = None
    resume_pdf_path: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def to_row(self) -> dict[str, Any]:
        return self.model_dump(
            mode="json", exclude_none=True, exclude={"created_at", "updated_at"}
        )

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> Application:
        return cls.model_validate(row)
