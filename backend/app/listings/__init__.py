"""Module 2 — job listing ingestion: fetch/parse/score listings against
the candidate's preferences and surface them for selection."""

from app.listings.models import Listing, ListingSource, ListingStatus
from app.listings.repository import ListingRepository

__all__ = ["Listing", "ListingRepository", "ListingSource", "ListingStatus"]
