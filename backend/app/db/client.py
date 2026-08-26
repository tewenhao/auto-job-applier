"""Supabase client factory."""

from __future__ import annotations

from functools import lru_cache

from supabase import Client, create_client

from app.config import get_settings


@lru_cache
def get_supabase() -> Client:
    """Return a cached Supabase client built from settings.

    Raises a clear error if the project isn't configured, rather than failing
    deep inside a request.
    """
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_key:
        raise RuntimeError(
            "Supabase is not configured. Set SUPABASE_URL and SUPABASE_KEY in your .env."
        )
    return create_client(settings.supabase_url, settings.supabase_key)
