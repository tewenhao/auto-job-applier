"""FastAPI dependency providers.

Each returns a repository instance. Endpoints depend on these so tests can
override them (``app.dependency_overrides``) with fakes — no Supabase needed.
"""

from __future__ import annotations

from app.generation.repository import GenerationRepository
from app.listings.repository import ListingRepository
from app.profile.repository import ProfileRepository


def get_gen_repo() -> GenerationRepository:
    return GenerationRepository()


def get_listings_repo() -> ListingRepository:
    return ListingRepository()


def get_profile_repo() -> ProfileRepository:
    return ProfileRepository()
