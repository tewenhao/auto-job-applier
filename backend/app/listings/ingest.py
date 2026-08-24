"""Listing ingestion orchestration: fetch -> parse -> build -> score -> store."""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from app.config import get_settings
from app.listings.fetch import FetchedJob, fetch_job
from app.listings.models import Listing, ListingSource, ListingStatus, normalize_company
from app.listings.parse import ParsedListing, parse_listing
from app.listings.repository import ListingRepository
from app.listings.score import apply_hard_filters, score_listing
from app.llm import LLMClient
from app.profile.repository import ProfileRepository


def parse_url_lines(text: str) -> list[str]:
    """Extract URLs from a block of text: one per line, skipping blanks and
    ``#`` comments."""
    out = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            out.append(stripped)
    return out


def dedupe_preserving_order(urls: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def build_listing(
    fetched: FetchedJob,
    parsed: ParsedListing,
    *,
    candidate_id: UUID,
    source: ListingSource,
    source_name: str,
) -> Listing:
    """Merge a fetched posting and its parsed fields into a Listing (pure)."""
    company = parsed.company or fetched.company
    return Listing(
        candidate_id=candidate_id,
        source=source,
        source_name=source_name,
        url=fetched.url,
        ats=fetched.ats,
        company=company,
        company_group=normalize_company(company),
        role_title=parsed.role_title or fetched.role_title,
        domain=parsed.domain,
        market=parsed.market,
        location=parsed.location or fetched.location,
        jd_text=fetched.jd_text,
        jd_summary=parsed.jd_summary,
        requirements=parsed.requirements,
        posted_at=fetched.posted_at,
    )


class ListingIngestor:
    def __init__(
        self,
        listings: ListingRepository,
        profile: ProfileRepository,
        llm: LLMClient,
        threshold: int | None = None,
    ) -> None:
        self.listings = listings
        self.profile = profile
        self.llm = llm
        self.threshold = (
            threshold if threshold is not None else get_settings().listing_score_threshold
        )

    def ingest_manual(
        self, *, candidate_id: UUID, url: str | None = None, text: str | None = None
    ) -> Listing:
        """Ingest a listing from a pasted URL or raw JD text."""
        if url:
            fetched = fetch_job(url)
        elif text:
            fetched = FetchedJob(ats="manual", jd_text=text)
        else:
            raise ValueError("Provide either a URL or JD text.")

        parsed = parse_listing(self.llm, fetched)
        listing = build_listing(
            fetched,
            parsed,
            candidate_id=candidate_id,
            source=ListingSource.MANUAL,
            source_name="manual",
        )
        return self.score_and_store(listing, candidate_id=candidate_id)

    def score_and_store(self, listing: Listing, *, candidate_id: UUID) -> Listing:
        prefs = self.profile.get_preferences(candidate_id)
        reason = apply_hard_filters(listing, prefs)
        if reason:
            listing.score = 0
            listing.status = ListingStatus.FILTERED
            listing.score_rationale = reason
            listing.score_breakdown = {"filtered": reason}
        else:
            result = score_listing(self.llm, listing, prefs, self._profile_summary(candidate_id))
            listing.score = result.score
            listing.score_rationale = result.rationale
            listing.score_breakdown = {"matched": result.matched, "missing": result.missing}
            listing.status = (
                ListingStatus.SURFACED if result.score >= self.threshold else ListingStatus.NEW
            )
        return self.listings.upsert(listing)

    def _profile_summary(self, candidate_id: UUID) -> str:
        profile = self.profile.get_master_profile(candidate_id)
        exps = [
            f"- {e.title} @ {e.org} ({e.kind})"
            for e in profile.experiences[:20]
            if e.title
        ]
        skills = ", ".join(s.name for s in profile.skills[:30])
        return "Experiences:\n" + "\n".join(exps) + "\n\nSkills: " + skills
