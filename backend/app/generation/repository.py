"""Data-access for applications and cached company briefs."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from supabase import Client

from app.db.client import get_supabase
from app.generation.models import Application, CompanyBrief


def _rows(response: Any) -> list[dict[str, Any]]:
    return cast("list[dict[str, Any]]", response.data)


def _first(data: list[dict[str, Any]]) -> dict[str, Any] | None:
    return data[0] if data else None


class GenerationRepository:
    def __init__(self, client: Client | None = None) -> None:
        self.client = client or get_supabase()

    # --- company briefs (cached per company_group) ---
    def get_company_brief(self, candidate_id: UUID, company_group: str) -> CompanyBrief | None:
        row = _first(
            _rows(
                self.client.table("company_briefs")
                .select("*")
                .eq("candidate_id", str(candidate_id))
                .eq("company_group", company_group)
                .execute()
            )
        )
        return CompanyBrief.from_row(row) if row else None

    def set_company_brief(self, brief: CompanyBrief) -> CompanyBrief:
        row = _rows(
            self.client.table("company_briefs")
            .upsert(brief.to_row(), on_conflict="candidate_id,company_group")
            .execute()
        )[0]
        return CompanyBrief.from_row(row)

    # --- applications (one per listing) ---
    def get_application_for_listing(
        self, candidate_id: UUID, listing_id: UUID
    ) -> Application | None:
        row = _first(
            _rows(
                self.client.table("applications")
                .select("*")
                .eq("candidate_id", str(candidate_id))
                .eq("listing_id", str(listing_id))
                .execute()
            )
        )
        return Application.from_row(row) if row else None

    def upsert_application(self, application: Application) -> Application:
        row = _rows(
            self.client.table("applications")
            .upsert(application.to_row(), on_conflict="candidate_id,listing_id")
            .execute()
        )[0]
        return Application.from_row(row)

    def get_application(self, application_id: UUID) -> Application | None:
        row = _first(
            _rows(
                self.client.table("applications")
                .select("*")
                .eq("id", str(application_id))
                .execute()
            )
        )
        return Application.from_row(row) if row else None

    def list_applications(self, candidate_id: UUID) -> list[Application]:
        rows = _rows(
            self.client.table("applications")
            .select("*")
            .eq("candidate_id", str(candidate_id))
            .order("created_at", desc=True)
            .execute()
        )
        return [Application.from_row(r) for r in rows]
