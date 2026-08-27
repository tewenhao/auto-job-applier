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
from urllib.parse import parse_qs, urlparse

import httpx
from pydantic import BaseModel

from app.config import get_settings

# A browser UA: some ATS hosts (notably Workday) reject non-browser agents.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
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
    from_api: bool = False  # fetched via a structured single-job API (not scraped HTML)


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


def parse_workday_url(url: str) -> tuple[str, str, str, str] | None:
    """Return (host, tenant, site, job_path) for a Workday careers URL.

    Workday careers pages are JS shells, but each has a JSON twin under
    ``/wday/cxs/{tenant}/{site}/job/{job_path}``. E.g.
    ``https://osv-cci.wd1.myworkdayjobs.com/en-US/CCICareers/job/Foo_R1347``
    -> host ``osv-cci.wd1.myworkdayjobs.com``, tenant ``osv-cci``,
    site ``CCICareers``, job_path ``Foo_R1347``.
    """
    m = re.search(
        r"https?://([\w-]+\.[\w.-]*myworkdayjobs\.com)"
        r"/(?:[a-z]{2}-[A-Z]{2}/)?([^/]+)/job/([^?#]+)",  # job path may span '/'
        url,
    )
    if not m:
        return None
    host, site = m.group(1), m.group(2)
    job_path = m.group(3).rstrip("/")  # may be 'Location/Slug_R123'
    tenant = host.split(".")[0]
    return host, tenant, site, job_path


def _greenhouse_embed(url: str) -> tuple[str, str] | None:
    """A Greenhouse job embedded on a company domain carries ?gh_jid=NNN. Guess
    the board token from the domain's main label (e.g. quantbot.com -> quantbot)."""
    parts = urlparse(url)
    jid_values = parse_qs(parts.query).get("gh_jid")
    jid = jid_values[0] if jid_values else None
    if not jid or not jid.isdigit():
        return None
    host = (parts.hostname or "").lower().removeprefix("www.")
    token = host.split(".")[0] if host else ""
    return (token, jid) if token else None


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
        from_api=True,
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
        from_api=True,
        url=url or payload.get("hostedUrl"),
        role_title=payload.get("text"),
        location=categories.get("location") if isinstance(categories, dict) else None,
        jd_text=text,
    )


def build_from_workday(payload: dict[str, Any], *, url: str | None = None) -> FetchedJob:
    info = payload.get("jobPostingInfo") or {}
    org = payload.get("hiringOrganization") or {}
    return FetchedJob(
        ats="workday",
        from_api=True,
        url=url or info.get("externalUrl"),
        company=org.get("name") if isinstance(org, dict) else None,
        role_title=info.get("title"),
        location=info.get("location"),
        jd_text=html_to_text(info.get("jobDescription", "")),
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

    if ats == "workday" and (wd := parse_workday_url(url)):
        host, tenant, site, job_path = wd
        cxs = f"https://{host}/wday/cxs/{tenant}/{site}/job/{job_path}"
        try:
            job = build_from_workday(_get_json(cxs), url=url)
        except (httpx.HTTPError, ValueError):
            job = None  # fall through to the generic HTML path below
        if job and job.jd_text and len(job.jd_text) >= MIN_USABLE_CHARS:
            return job

    # Greenhouse boards embedded on a company's own domain (?gh_jid=NNN) are
    # detected as "other" but are served by the Greenhouse API.
    if ats == "other" and (gh := _greenhouse_embed(url)):
        board, job_id = gh
        try:
            data = _get_json(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}")
            return build_from_greenhouse(data, url=url)
        except (httpx.HTTPError, ValueError):
            pass  # fall through to the generic HTML path below

    raw: str | None = None
    try:
        raw = _get_html(url)
    except httpx.HTTPStatusError as exc:
        # Anti-bot blocks (403/401/429) — let the browser fallback try instead.
        if exc.response.status_code not in (401, 403, 429):
            raise
    text = html_to_text(raw) if raw else ""

    # Headless-browser fallback for JS shells and blocked pages (Workday whose
    # JSON path failed, IBM, arcticlake, Cloudflare 403s, ...).
    if len(text) < MIN_USABLE_CHARS:
        rendered = _render_with_browser(url)
        if rendered and len(html_to_text(rendered)) >= MIN_USABLE_CHARS:
            raw = rendered
            text = html_to_text(rendered)

    if not raw or len(text) < MIN_USABLE_CHARS:
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
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    with httpx.Client(headers=headers, timeout=30.0) as client:
        resp = client.get(url, follow_redirects=True)
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]


def _render_with_browser(url: str) -> str | None:
    """Render ``url`` in a headless browser if enabled + available, else None."""
    try:
        settings = get_settings()
    except Exception:
        return None
    if not settings.browser_fallback:
        return None
    from app.listings.browser import render_page

    return render_page(url, executable_path=settings.browser_executable_path)


def _get_html(url: str) -> str:
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30.0) as client:
        resp = client.get(url, follow_redirects=True)
        resp.raise_for_status()
        return resp.text
