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
from urllib.parse import parse_qs, quote, urlparse

import httpx

from app.listings.fetch import (
    USER_AGENT,
    FetchedJob,
    build_from_greenhouse,
    build_from_lever,
    html_to_text,
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
        keywords.extend(w.strip('"') for w in kw.split())

    def _first(key: str) -> str | None:
        values = q.get(key)
        return values[0].strip('"') if values else None

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

    # Oracle HCM Cloud CandidateExperience search page.
    m = re.search(r"/hcmUI/CandidateExperience/[^/]+/sites/([^/?#]+)", url)
    if m and "oraclecloud" in host:
        return ("oracle", f"{host}|{m.group(1)}", _filters_from_query(query))

    return None


def _title(token: str) -> str:
    return token.replace("-", " ").replace("_", " ").title()


def _get(url: str) -> Any:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    with httpx.Client(headers=headers, timeout=30.0) as client:
        resp = client.get(url, follow_redirects=True)
        resp.raise_for_status()
        return resp.json()


def _post(url: str, payload: dict[str, Any]) -> Any:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    with httpx.Client(headers=headers, timeout=30.0) as client:
        resp = client.post(url, json=payload, follow_redirects=True)
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
    elif kind == "oracle":
        host, site = token.split("|", 1)
        out = _enumerate_oracle(host, site, filters)
    return out[:MAX_BOARD_RESULTS]


# --- Oracle HCM Cloud (CandidateExperience) ---
def _oracle_api(host: str) -> str:
    return f"https://{host}/hcmRestApi/resources/latest"


def _oracle_site_number(host: str, site: str) -> str | None:
    """Map a CE site name (e.g. 'BNY-Careers') to its numeric siteNumber."""
    data = _get(f"{_oracle_api(host)}/recruitingCESites?onlyData=true&expand=all")
    for item in data.get("items", []):
        names = {item.get("Name"), item.get("SiteName"), item.get("ExternalPathName")}
        if site in names:
            number = item.get("SiteNumber") or item.get("Number")
            if number:
                return str(number)
    return None


def _enumerate_oracle(host: str, site: str, filters: BoardFilters) -> list[FetchedJob]:
    site_number = _oracle_site_number(host, site)
    if not site_number:
        return []
    facets = "LOCATIONS;WORK_LOCATIONS;WORKPLACE_TYPES;TITLES;CATEGORIES;POSTING_DATES"
    finder = (
        f"findReqs;siteNumber={site_number},facetsList={facets},"
        f"limit=200,sortBy=POSTING_DATES_DESC"
    )
    if filters.keywords:
        finder += f',keyword={" ".join(filters.keywords)}'
    search = (
        f"{_oracle_api(host)}/recruitingCEJobRequisitions?onlyData=true"
        f"&expand=requisitionList.secondaryLocations,flexFieldsFacet.values"
        f"&finder={quote(finder, safe=';,=')}"
    )
    data = _get(search)
    items = data.get("items") or [{}]
    reqs = items[0].get("requisitionList", [])

    out: list[FetchedJob] = []
    for req in reqs:
        job = FetchedJob(
            ats="oracle",
            from_api=True,
            url=f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{req.get('Id')}",
            company=site.replace("-Careers", "").replace("Careers", "").strip("-") or site,
            role_title=req.get("Title"),
            location=req.get("PrimaryLocation"),
        )
        if not filters.matches(job):
            continue
        job.jd_text = _oracle_job_text(host, site_number, req.get("Id"))
        out.append(job)
    return out


def _oracle_job_text(host: str, site_number: str, req_id: str | None) -> str:
    if not req_id:
        return ""
    finder = f'ById;Id="{req_id}",siteNumber={site_number}'
    safe_chars = ';,="'
    encoded = quote(finder, safe=safe_chars)
    url = (
        f"{_oracle_api(host)}/recruitingCEJobRequisitionDetails?onlyData=true"
        f"&expand=all&finder={encoded}"
    )
    try:
        data = _get(url)
    except httpx.HTTPError:
        return ""
    items = data.get("items") or [{}]
    detail = items[0]
    parts = [detail.get("ExternalDescriptionStr", ""), detail.get("ExternalQualificationsStr", "")]
    return html_to_text(" ".join(p for p in parts if p))


# --- Phenom People (POST /widgets, ddoKey=refineSearch) ---
_PHENOM_REFNUM = re.compile(r"""["']refNum["']\s*[:=]\s*["']([A-Za-z0-9]+)["']""")


def detect_phenom_refnum(html: str) -> str | None:
    """A Phenom career page embeds its site's refNum in the page config."""
    m = _PHENOM_REFNUM.search(html or "")
    return m.group(1) if m else None


def enumerate_phenom_url(url: str, html: str) -> list[FetchedJob]:
    """Enumerate a Phenom site using filters read from the page URL."""
    return enumerate_phenom(url, html, _filters_from_query(urlparse(url).query))


def enumerate_phenom(url: str, html: str, filters: BoardFilters) -> list[FetchedJob]:
    """Enumerate a Phenom career site's postings via its /widgets search API."""
    refnum = detect_phenom_refnum(html)
    host = urlparse(url).hostname
    if not refnum or not host:
        return []
    payload = {
        "lang": "en",
        "deviceType": "desktop",
        "country": "us",
        "pageName": "search-results",
        "ddoKey": "refineSearch",
        "stringify": False,
        "pageType": "external",
        "jobs": True,
        "counts": False,
        "all_fields": ["category", "state", "city", "country", "department"],
        "from": 0,
        "size": 100,
        "clientName": host.split(".")[0],
        "excludeJd": False,
        "facetType": 0,
        "refNum": refnum,
        "keywords": " ".join(filters.keywords) if filters.keywords else "",
        "location": filters.location or "",
    }
    data = _post(f"https://{host}/widgets", payload)
    jobs = (((data or {}).get("refineSearch") or {}).get("data") or {}).get("jobs") or []

    out: list[FetchedJob] = []
    for j in jobs:
        location = j.get("cityStateCountry") or j.get("location") or j.get("city")
        body = j.get("descriptionTeaser") or j.get("description") or j.get("jd") or ""
        job = FetchedJob(
            ats="phenom",
            from_api=True,
            url=j.get("applyUrl") or j.get("jobUrl") or j.get("url"),
            company=_title(host.split(".")[0]) if host else None,
            role_title=j.get("title"),
            location=location,
            jd_text=html_to_text(body),
        )
        if filters.matches(job):
            out.append(job)
    return out[:MAX_BOARD_RESULTS]


def enumerate_board_url(url: str) -> list[FetchedJob] | None:
    """If ``url`` is a board, enumerate its matching postings; else None."""
    board = detect_board(url)
    if board is None:
        return None
    return enumerate_board(*board)
