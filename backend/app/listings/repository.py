"""Data-access layer for job listings."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from supabase import Client

from app.db.client import get_supabase
from app.listings.models import Listing, ListingStatus


def _rows(response: Any) -> list[dict[str, Any]]:
    return cast("list[dict[str, Any]]", response.data)


def _first(data: list[dict[str, Any]]) -> dict[str, Any] | None:
    return data[0] if data else None


class ListingRepository:
    def __init__(self, client: Client | None = None) -> None:
        self.client = client or get_supabase()

    def get_by_url(self, candidate_id: UUID, url: str) -> Listing | None:
        row = _first(
            _rows(
                self.client.table("listings")
                .select("*")
                .eq("candidate_id", str(candidate_id))
                .eq("url", url)
                .execute()
            )
        )
        return Listing.from_row(row) if row else None

    def upsert(self, listing: Listing) -> Listing:
        """Insert, or update the existing row with the same URL (when present)."""
        if listing.url:
            existing = self.get_by_url(listing.candidate_id, listing.url)
            if existing is not None:
                row = _rows(
                    self.client.table("listings")
                    .update(listing.to_row())
                    .eq("id", str(existing.id))
                    .execute()
                )[0]
                return Listing.from_row(row)
        row = _rows(self.client.table("listings").insert(listing.to_row()).execute())[0]
        return Listing.from_row(row)

    def get(self, listing_id: UUID) -> Listing | None:
        row = _first(
            _rows(self.client.table("listings").select("*").eq("id", str(listing_id)).execute())
        )
        return Listing.from_row(row) if row else None

    def list(
        self,
        candidate_id: UUID,
        *,
        status: ListingStatus | None = None,
        min_score: int | None = None,
    ) -> list[Listing]:
        query = self.client.table("listings").select("*").eq("candidate_id", str(candidate_id))
        if status is not None:
            query = query.eq("status", status.value)
        if min_score is not None:
            query = query.gte("score", min_score)
        rows = _rows(query.order("score", desc=True).execute())
        return [Listing.from_row(r) for r in rows]

    def set_status(self, listing_id: UUID, status: ListingStatus) -> None:
        self.client.table("listings").update({"status": status.value}).eq(
            "id", str(listing_id)
        ).execute()
