"""Listing ingestion orchestration: fetch -> parse -> build -> score -> store."""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from app.config import get_settings
from app.listings.discover import detect_board, enumerate_board_url, enumerate_index_page
from app.listings.fetch import FetchedJob, FetchError, fetch_job
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

    def ingest_url(self, url: str, *, candidate_id: UUID) -> list[Listing]:
        """Ingest from a URL, expanding boards/index pages into their roles.

        - Greenhouse/Lever/Oracle *board* URLs are enumerated.
        - A single posting is ingested as one listing.
        - A page that parses as an index but is a Phenom site is enumerated too.
        Returns every listing ingested (one for a normal posting).
        """
        if detect_board(url):
            return self.ingest_board(url, candidate_id=candidate_id)

        fetched = fetch_job(url)
        parsed = parse_listing(self.llm, fetched)

        if not fetched.from_api and not parsed.is_job_posting:
            expanded = enumerate_index_page(url, fetched.raw_html or "")
            results: list[Listing] = []
            for job in expanded:
                try:
                    results.append(self._ingest_fetched(job, candidate_id=candidate_id))
                except FetchError:
                    continue
            if results:
                return results
            raise FetchError(
                f"{url} looks like a careers index / landing page listing many roles, "
                "not one posting. Open a specific job and pass that URL."
            )

        return [self._finalize(fetched, parsed, candidate_id=candidate_id, url=url)]

    def ingest_manual(
        self, *, candidate_id: UUID, url: str | None = None, text: str | None = None
    ) -> Listing:
        """Ingest one listing from a pasted URL or raw JD text (single posting)."""
        if url:
            fetched = fetch_job(url)
        elif text:
            fetched = FetchedJob(ats="manual", jd_text=text)
        else:
            raise ValueError("Provide either a URL or JD text.")
        return self._ingest_fetched(fetched, candidate_id=candidate_id, url=url)

    def ingest_board(self, url: str, *, candidate_id: UUID) -> list[Listing]:
        """Enumerate a Greenhouse/Lever/Oracle board URL and ingest each role.

        Raises FetchError if the board yields no matching postings; individual
        postings that fail to ingest are skipped, not fatal.
        """
        jobs = enumerate_board_url(url)
        if not jobs:
            raise FetchError(
                f"No matching roles found on the board {url} (check the filters in the URL)."
            )
        out: list[Listing] = []
        for fetched in jobs:
            try:
                out.append(self._ingest_fetched(fetched, candidate_id=candidate_id))
            except FetchError:
                continue
        return out

    def _ingest_fetched(
        self, fetched: FetchedJob, *, candidate_id: UUID, url: str | None = None
    ) -> Listing:
        """Parse -> gate -> build -> score -> store a fetched posting."""
        parsed = parse_listing(self.llm, fetched)

        # Only gate on the careers-index heuristic for scraped HTML — a job
        # fetched via a structured API (Greenhouse/Lever/Workday) is always a
        # single posting, so never reject it on the parser's guess.
        if not fetched.from_api and not parsed.is_job_posting:
            raise FetchError(
                f"{url or 'This text'} looks like a careers index / landing page listing "
                "many roles, not one posting. Open a specific job and pass that URL."
            )
        return self._finalize(fetched, parsed, candidate_id=candidate_id, url=url)

    def _finalize(
        self, fetched: FetchedJob, parsed: ParsedListing, *, candidate_id: UUID, url: str | None
    ) -> Listing:
        """Build -> zero-signal gate -> score -> store (no index gate)."""
        listing = build_listing(
            fetched,
            parsed,
            candidate_id=candidate_id,
            source=ListingSource.MANUAL,
            source_name="manual",
        )
        if not listing.role_title and not listing.company:
            raise FetchError(
                f"Couldn't extract a role or company from {url or 'the pasted text'} "
                "(often a JavaScript-rendered page). Paste the job description text instead."
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
