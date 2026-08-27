"""Board enumeration: turn a careers *board* URL into its individual postings.

A Trackr link is often a filtered board page (e.g.
``jobs.lever.co/palantir?commitment=Internship&location=London`` or
``job-boards.greenhouse.io/embed/job_board?for=jumptrading&keyword=engineer+intern``)
rather than one job. Instead of failing on those, list every posting on the
board via the public Greenhouse/Lever APIs and keep the ones matching the
filters already encoded in the URL. One paste -> all the relevant roles.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

from app.listings.fetch import (
    USER_AGENT,
    FetchedJob,
    build_from_greenhouse,
    build_from_lever,
)

# Don't ingest an unbounded number of roles from a single board.
MAX_BOARD_RESULTS = 40


class BoardFilters:
    def __init__(
        self, keywords: list[str], location: str | None, commitment: str | None
    ) -> None:
        # If the URL carried no filters at all, default to intern-ish roles.
        if not keywords and not location and not commitment:
            keywords = ["intern"]
        self.keywords = [k.lower() for k in keywords]
        self.location = location.lower() if location else None
        self.commitment = commitment.lower() if commitment else None

    def matches(self, job: FetchedJob, *, commitment: str | None = None) -> bool:
        title = (job.role_title or "").lower()
        if any(kw not in title for kw in self.keywords):
            return False
        if self.location:
            where = f"{job.location or ''} {title}".lower()
            if self.location not in where:
                return False
        if self.commitment and self.commitment not in (commitment or "").lower():
            return False
        return True


def _filters_from_query(query: str) -> BoardFilters:
    q = parse_qs(query)
    keywords: list[str] = []
    for kw in q.get("keyword", []):
        keywords.extend(kw.split())

    def _first(key: str) -> str | None:
        values = q.get(key)
        return values[0] if values else None

    return BoardFilters(
        keywords=keywords, location=_first("location"), commitment=_first("commitment")
    )


def detect_board(url: str) -> tuple[str, str, BoardFilters] | None:
    """Return (kind, token, filters) if ``url`` is a Greenhouse/Lever *board*
    (not a single posting), else None."""
    parts = urlparse(url)
    host = (parts.hostname or "").lower()
    query = parts.query

    if "greenhouse.io" in host:
        # A single job (…/jobs/123 or ?gh_jid=) is not a board.
        if re.search(r"/jobs/\d+", url) or "gh_jid=" in url:
            return None
        q = parse_qs(query)
        token = q["for"][0] if "for" in q else None
        if not token:
            m = re.search(r"greenhouse\.io/([^/?#]+)", url)
            if m and m.group(1) not in {"embed", "job-boards"}:
                token = m.group(1)
        return ("greenhouse", token, _filters_from_query(query)) if token else None

    if "lever.co" in host:
        if re.search(r"/[0-9a-f-]{36}", url):  # a specific posting id
            return None
        m = re.search(r"lever\.co/([^/?#]+)", url)
        return ("lever", m.group(1), _filters_from_query(query)) if m else None

    return None


def _title(token: str) -> str:
    return token.replace("-", " ").replace("_", " ").title()


def _get(url: str) -> Any:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    with httpx.Client(headers=headers, timeout=30.0) as client:
        resp = client.get(url, follow_redirects=True)
        resp.raise_for_status()
        return resp.json()


def enumerate_board(kind: str, token: str, filters: BoardFilters) -> list[FetchedJob]:
    """List a board's postings and return the ones matching ``filters``."""
    out: list[FetchedJob] = []
    if kind == "greenhouse":
        data = _get(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true")
        for job in data.get("jobs", []):
            job.setdefault("company_name", _title(token))
            fetched = build_from_greenhouse(job, url=job.get("absolute_url"))
            if filters.matches(fetched):
                out.append(fetched)
    elif kind == "lever":
        for posting in _get(f"https://api.lever.co/v0/postings/{token}?mode=json"):
            fetched = build_from_lever(posting, url=posting.get("hostedUrl"))
            if not fetched.company:
                fetched.company = _title(token)
            commitment = (posting.get("categories") or {}).get("commitment")
            if filters.matches(fetched, commitment=commitment):
                out.append(fetched)
    return out[:MAX_BOARD_RESULTS]


def enumerate_board_url(url: str) -> list[FetchedJob] | None:
    """If ``url`` is a board, enumerate its matching postings; else None."""
    board = detect_board(url)
    if board is None:
        return None
    return enumerate_board(*board)
