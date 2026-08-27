"""Fetch a job posting from a URL.

Strategy (option A): use the clean public JSON APIs for Greenhouse and Lever
(the two most common tech ATS); fall back to a generic HTTP GET + HTML->text for
everything else. JS-rendered pages (Workday, LinkedIn) return too little text —
we detect that and tell the user to paste the JD text instead.
"""

from __future__ import annotations

import html
import re
from datetime import date, datetime
from typing import Any
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel

USER_AGENT = "auto-job-applier/0.1 (+personal job search tool)"
# Below this many characters, a fetched page is almost certainly a JS shell.
MIN_USABLE_CHARS = 400


class FetchedJob(BaseModel):
    ats: str
    url: str | None = None
    company: str | None = None
    role_title: str | None = None
    location: str | None = None
    jd_text: str | None = None
    posted_at: date | None = None


class FetchError(RuntimeError):
    """Raised when a URL can't be fetched into usable text (e.g. a JS SPA)."""


def detect_ats(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if "greenhouse.io" in host:
        return "greenhouse"
    if "lever.co" in host:
        return "lever"
    if "myworkdayjobs.com" in host or "workday" in host:
        return "workday"
    if "linkedin.com" in host:
        return "linkedin"
    return "other"


def parse_greenhouse_url(url: str) -> tuple[str, str] | None:
    """Return (board_token, job_id) from a Greenhouse board URL."""
    m = re.search(r"greenhouse\.io/(?:embed/job_app\?for=)?([^/?#]+).*?/jobs/(\d+)", url)
    if m:
        return m.group(1), m.group(2)
    m = re.search(r"greenhouse\.io/([^/?#]+)/jobs/(\d+)", url)
    return (m.group(1), m.group(2)) if m else None


def parse_lever_url(url: str) -> tuple[str, str] | None:
    """Return (company, posting_id) from a Lever posting URL."""
    m = re.search(r"lever\.co/([^/?#]+)/([0-9a-f-]{36})", url)
    return (m.group(1), m.group(2)) if m else None


def html_to_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    text = html.unescape(raw)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n\s*\n+", "\n\n", text).strip()


def build_from_greenhouse(payload: dict[str, Any], *, url: str | None = None) -> FetchedJob:
    location = payload.get("location") or {}
    posted = _iso_date(payload.get("updated_at") or payload.get("created_at"))
    return FetchedJob(
        ats="greenhouse",
        url=url or payload.get("absolute_url"),
        company=payload.get("company_name"),
        role_title=payload.get("title"),
        location=location.get("name") if isinstance(location, dict) else None,
        jd_text=html_to_text(payload.get("content", "")),
        posted_at=posted,
    )


def build_from_lever(payload: dict[str, Any], *, url: str | None = None) -> FetchedJob:
    categories = payload.get("categories") or {}
    text = payload.get("descriptionPlain") or html_to_text(payload.get("description", ""))
    return FetchedJob(
        ats="lever",
        url=url or payload.get("hostedUrl"),
        role_title=payload.get("text"),
        location=categories.get("location") if isinstance(categories, dict) else None,
        jd_text=text,
    )


def fetch_job(url: str) -> FetchedJob:
    """Fetch and normalize a posting from a URL (network I/O)."""
    ats = detect_ats(url)

    if ats == "greenhouse" and (parsed := parse_greenhouse_url(url)):
        board, job_id = parsed
        data = _get_json(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}")
        return build_from_greenhouse(data, url=url)

    if ats == "lever" and (parsed := parse_lever_url(url)):
        company, posting_id = parsed
        data = _get_json(f"https://api.lever.co/v0/postings/{company}/{posting_id}")
        return build_from_lever(data, url=url)

    raw = _get_html(url)
    text = html_to_text(raw)
    if len(text) < MIN_USABLE_CHARS:
        raise FetchError(
            f"Fetched too little text from {url} (likely a JavaScript-rendered page). "
            "Copy the job description and pass it as text instead of a URL."
        )
    # Pull role/company from the page's <title> and Open Graph tags. These feed
    # the parser as hints and act as a fallback so a generic page doesn't land as
    # an "Untitled role".
    meta = _extract_head_meta(raw)
    return FetchedJob(
        ats=ats,
        url=url,
        company=meta.get("company"),
        role_title=meta.get("title"),
        jd_text=text,
    )


_META_TAG = re.compile(r"<meta\b[^>]*>", re.I)
_META_KEY = re.compile(r"""(?:property|name)=["']([^"']+)["']""", re.I)
_META_VAL = re.compile(r"""content=["']([^"']*)["']""", re.I)
_TITLE_TAG = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)


def _clean_title(title: str) -> str:
    """Drop a trailing site-name segment ('Role | Company', 'Role — Careers').
    Only splits on separators that are almost always site delimiters, never a
    plain hyphen (which often belongs to the role itself)."""
    for sep in (" | ", " — ", " – ", " · "):
        if sep in title:
            title = title.split(sep)[0]
    return title.strip()


def _extract_head_meta(raw: str) -> dict[str, str | None]:
    """Best-effort role/company from <title> and og: meta tags."""
    meta: dict[str, str] = {}
    for tag in _META_TAG.findall(raw):
        key = _META_KEY.search(tag)
        val = _META_VAL.search(tag)
        if key and val:
            meta[key.group(1).lower()] = html.unescape(val.group(1)).strip()

    title = meta.get("og:title")
    if not title and (m := _TITLE_TAG.search(raw)):
        title = _clean_title(html.unescape(html_to_text(m.group(1))))
    return {"title": title or None, "company": meta.get("og:site_name") or None}


def _iso_date(value: Any) -> date | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _get_json(url: str) -> dict[str, Any]:
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30.0) as client:
        resp = client.get(url, follow_redirects=True)
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]


def _get_html(url: str) -> str:
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30.0) as client:
        resp = client.get(url, follow_redirects=True)
        resp.raise_for_status()
        return resp.text
