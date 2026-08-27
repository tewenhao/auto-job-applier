"""Tests for the deterministic listing pieces (no LLM/network)."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest

from app.listings.fetch import (
    _clean_title,
    _extract_head_meta,
    build_from_greenhouse,
    build_from_lever,
    build_from_workday,
    detect_ats,
    html_to_text,
    parse_greenhouse_url,
    parse_lever_url,
    parse_workday_url,
)
from app.listings.ingest import build_listing, dedupe_preserving_order, parse_url_lines
from app.listings.models import Listing, ListingSource, ListingStatus, normalize_company
from app.listings.parse import ParsedListing
from app.listings.score import apply_hard_filters
from app.profile.models import Preferences

CID = uuid4()


# --- HTML metadata extraction (title/company fallback) ---
def test_extract_head_meta_prefers_og_tags() -> None:
    html = (
        "<head><title>SWE Intern - Backend | Acme Careers</title>"
        '<meta property="og:title" content="SWE Intern - Backend">'
        '<meta property="og:site_name" content="Acme Corp"></head>'
    )
    meta = _extract_head_meta(html)
    assert meta == {"title": "SWE Intern - Backend", "company": "Acme Corp"}


def test_extract_head_meta_falls_back_to_title_tag() -> None:
    meta = _extract_head_meta("<head><title>Quant Researcher — Jane Street</title></head>")
    assert meta["title"] == "Quant Researcher"  # site suffix stripped
    assert meta["company"] is None


def test_clean_title_keeps_hyphenated_roles() -> None:
    assert _clean_title("Backend Engineer - Payments") == "Backend Engineer - Payments"
    assert _clean_title("Data Analyst | Careers") == "Data Analyst"


# --- headless-browser fallback wiring ---
_JS_SHELL = "<html><body><div id=app></div></body></html>"  # too little text
_RENDERED = (
    "<html><head><title>SWE Intern | Acme</title></head><body>"
    "<h1>Software Engineer Intern</h1><p>" + "Build systems in C++ and Python. " * 20
    + "</p></body></html>"
)


def test_fetch_job_browser_fallback_on_js_shell(monkeypatch) -> None:  # noqa: ANN001
    import app.listings.fetch as f

    monkeypatch.setattr(f, "_get_html", lambda url: _JS_SHELL)
    monkeypatch.setattr(f, "_render_with_browser", lambda url: _RENDERED)
    job = f.fetch_job("https://careers.example.com/job/1")
    assert job.role_title == "SWE Intern"
    assert "Build systems in C++" in (job.jd_text or "")


def test_fetch_job_browser_fallback_on_403(monkeypatch) -> None:  # noqa: ANN001
    import httpx

    import app.listings.fetch as f

    def _raise_403(url):  # noqa: ANN001, ANN202
        resp = httpx.Response(403, request=httpx.Request("GET", url))
        raise httpx.HTTPStatusError("403", request=resp.request, response=resp)

    monkeypatch.setattr(f, "_get_html", _raise_403)
    monkeypatch.setattr(f, "_render_with_browser", lambda url: _RENDERED)
    job = f.fetch_job("https://www.citadel.com/careers/details/x")
    assert "Build systems in C++" in (job.jd_text or "")


def test_fetch_job_raises_when_browser_unavailable(monkeypatch) -> None:  # noqa: ANN001
    import app.listings.fetch as f
    from app.listings.fetch import FetchError

    monkeypatch.setattr(f, "_get_html", lambda url: _JS_SHELL)
    monkeypatch.setattr(f, "_render_with_browser", lambda url: None)
    with pytest.raises(FetchError):
        f.fetch_job("https://careers.example.com/job/1")


# --- board enumeration (discovery) ---
def test_detect_board_lever_and_greenhouse() -> None:
    from app.listings.discover import detect_board

    kind, token, filt = detect_board(
        "https://jobs.lever.co/palantir?location=London&commitment=Internship"
    )
    assert (kind, token) == ("lever", "palantir")
    assert filt.location == "london" and filt.commitment == "internship"

    kind, token, filt = detect_board(
        "https://job-boards.greenhouse.io/embed/job_board?for=jumptrading&keyword=engineer+intern"
    )
    assert (kind, token) == ("greenhouse", "jumptrading")
    assert filt.keywords == ["engineer", "intern"]

    # single postings are not boards
    assert detect_board("https://job-boards.greenhouse.io/quadraturecapital/jobs/4255974") is None
    assert (
        detect_board("https://jobs.lever.co/acme/0a1b2c3d-4e5f-6789-abcd-ef0123456789") is None
    )
    assert detect_board("https://www.quantbot.com/careers/?gh_jid=4299858009") is None


def test_board_filters_matching() -> None:
    from app.listings.discover import BoardFilters
    from app.listings.fetch import FetchedJob

    swe = FetchedJob(ats="lever", role_title="Software Engineer Intern", location="London, UK")
    grad = FetchedJob(ats="lever", role_title="Graduate Analyst", location="New York")

    # keyword AND-match on title
    assert BoardFilters(["engineer", "intern"], None, None).matches(swe)
    assert not BoardFilters(["engineer", "intern"], None, None).matches(grad)
    # location substring
    assert BoardFilters(["intern"], "london", None).matches(swe)
    assert not BoardFilters(["intern"], "london", None).matches(grad)
    # commitment (lever)
    assert BoardFilters([], None, "internship").matches(swe, commitment="Internship")
    # empty filters -> default intern keyword
    assert BoardFilters([], None, None).keywords == ["intern"]


def test_enumerate_board_greenhouse(monkeypatch) -> None:  # noqa: ANN001
    import app.listings.discover as d

    payload = {
        "jobs": [
            {"title": "Software Engineer Intern", "content": "<p>Build stuff</p>", "location": {}},
            {"title": "Senior Staff Engineer", "content": "<p>Lead</p>", "location": {}},
        ]
    }
    monkeypatch.setattr(d, "_get", lambda url: payload)
    from app.listings.discover import BoardFilters, enumerate_board

    jobs = enumerate_board("greenhouse", "jumptrading", BoardFilters(["intern"], None, None))
    assert [j.role_title for j in jobs] == ["Software Engineer Intern"]
    assert jobs[0].company == "Jumptrading" and jobs[0].from_api is True


# --- ATS detection + URL parsing ---
def test_detect_ats() -> None:
    assert detect_ats("https://boards.greenhouse.io/acme/jobs/123") == "greenhouse"
    assert detect_ats("https://jobs.lever.co/acme/abc") == "lever"
    assert detect_ats("https://acme.wd1.myworkdayjobs.com/x") == "workday"
    assert detect_ats("https://www.linkedin.com/jobs/view/123") == "linkedin"
    assert detect_ats("https://careers.acme.com/job/1") == "other"


def test_parse_greenhouse_and_lever_urls() -> None:
    assert parse_greenhouse_url("https://boards.greenhouse.io/acme/jobs/4567") == ("acme", "4567")
    lever_id = "0a1b2c3d-4e5f-6789-abcd-ef0123456789"
    assert parse_lever_url(f"https://jobs.lever.co/acme/{lever_id}") == ("acme", lever_id)
    assert parse_lever_url("https://jobs.lever.co/acme/not-a-uuid") is None


def test_parse_workday_url() -> None:
    host, tenant, site, path = parse_workday_url(
        "https://osv-cci.wd1.myworkdayjobs.com/en-US/CCICareers/job/"
        "Front-Office-SWE-Internship_R1347?source=Trackr"
    )
    assert host == "osv-cci.wd1.myworkdayjobs.com"
    assert tenant == "osv-cci"
    assert site == "CCICareers"
    assert path == "Front-Office-SWE-Internship_R1347"
    # without the language segment
    assert parse_workday_url("https://acme.wd5.myworkdayjobs.com/External/job/DS_R99") == (
        "acme.wd5.myworkdayjobs.com",
        "acme",
        "External",
        "DS_R99",
    )
    assert parse_workday_url("https://greenhouse.io/acme/jobs/1") is None


def test_parse_workday_url_multi_segment_path() -> None:
    # Workday sometimes prefixes the job slug with a location segment.
    _, _, _, path = parse_workday_url(
        "https://tencent.wd1.myworkdayjobs.com/en-US/Tencent_Careers/job/"
        "UK-London/Software-Engineering-Intern_R107162-1?source=Trackr"
    )
    assert path == "UK-London/Software-Engineering-Intern_R107162-1"


def test_greenhouse_embed_detection() -> None:
    from app.listings.fetch import _greenhouse_embed

    assert _greenhouse_embed("https://www.quantbot.com/careers/?gh_jid=4299858009") == (
        "quantbot",
        "4299858009",
    )
    assert _greenhouse_embed("https://acme.com/jobs?x=1") is None


def test_api_result_has_from_api_flag() -> None:
    # build_* set from_api so ingestion never index-gates a structured single job
    assert build_from_greenhouse({"title": "X"}).from_api is True
    assert build_from_workday({"jobPostingInfo": {"title": "X"}}).from_api is True


def test_build_from_workday() -> None:
    payload = {
        "jobPostingInfo": {
            "title": "Front Office SWE Intern",
            "jobDescription": "<p>Build <b>trading</b> systems in C++.</p>",
            "location": "London",
        },
        "hiringOrganization": {"name": "CCI"},
    }
    job = build_from_workday(payload, url="https://x.myworkdayjobs.com/en-US/S/job/Foo_R1")
    assert job.ats == "workday"
    assert job.role_title == "Front Office SWE Intern"
    assert job.company == "CCI"
    assert job.location == "London"
    assert "trading systems in C++" in (job.jd_text or "")


def test_html_to_text_strips_tags_and_scripts() -> None:
    html = "<div>Hello <script>bad()</script><b>world</b>&amp; more</div>"
    assert html_to_text(html) == "Hello world & more"


def test_build_from_greenhouse() -> None:
    payload = {
        "title": "SWE Intern",
        "company_name": "Acme",
        "location": {"name": "London, UK"},
        "content": "<p>Build things &amp; learn</p>",
        "updated_at": "2026-03-01T10:00:00Z",
        "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
    }
    job = build_from_greenhouse(payload)
    assert job.role_title == "SWE Intern" and job.company == "Acme"
    assert job.location == "London, UK"
    assert job.jd_text == "Build things & learn"
    assert job.posted_at == date(2026, 3, 1)


def test_build_from_lever_prefers_plain_description() -> None:
    payload = {
        "text": "ML Intern",
        "categories": {"location": "Singapore"},
        "descriptionPlain": "Do ML.",
        "description": "<p>ignored</p>",
        "hostedUrl": "https://jobs.lever.co/acme/x",
    }
    job = build_from_lever(payload)
    assert job.role_title == "ML Intern" and job.location == "Singapore"
    assert job.jd_text == "Do ML."


# --- model + normalization ---
def test_normalize_company() -> None:
    assert normalize_company("Acme Inc.") == "acme"
    assert normalize_company("Foo Bar Ltd") == "foo bar"
    assert normalize_company(None) is None


def test_listing_to_row_round_trip() -> None:
    lst = Listing(
        candidate_id=CID, source=ListingSource.MANUAL, company="Acme",
        requirements=["Python"], status=ListingStatus.SURFACED, score=72,
    )
    row = lst.to_row()
    assert row["candidate_id"] == str(CID)
    assert row["source"] == "manual" and row["status"] == "surfaced"
    back = Listing.from_row({**row, "id": str(uuid4())})
    assert back.score == 72 and back.requirements == ["Python"]


# --- build_listing merge ---
def test_build_listing_merges_fetched_and_parsed() -> None:
    from app.listings.fetch import FetchedJob

    fetched = FetchedJob(ats="greenhouse", url="u", company="Acme", role_title="SWE", location="UK")
    parsed = ParsedListing(domain="swe", market="uk", jd_summary="Nice role", requirements=["Go"])
    lst = build_listing(
        fetched, parsed, candidate_id=CID, source=ListingSource.MANUAL, source_name="manual"
    )
    assert lst.company == "Acme" and lst.company_group == "acme"
    assert lst.domain == "swe" and lst.market == "uk"
    assert lst.requirements == ["Go"]


# --- hard filters ---
def _listing(**kw) -> Listing:
    base = dict(candidate_id=CID, source=ListingSource.MANUAL)
    base.update(kw)
    return Listing(**base)


def test_hard_filter_market_mismatch() -> None:
    prefs = Preferences(candidate_id=CID, location_markets=["uk", "sg"])
    assert apply_hard_filters(_listing(market="us"), prefs) is not None
    assert apply_hard_filters(_listing(market="uk"), prefs) is None
    # unknown market is not hard-dropped
    assert apply_hard_filters(_listing(market=None), prefs) is None


def test_hard_filter_avoid_list() -> None:
    prefs = Preferences(candidate_id=CID, avoid=["gambling"])
    hit = _listing(company="Gambling Co", role_title="SWE")
    assert apply_hard_filters(hit, prefs) is not None
    assert apply_hard_filters(_listing(company="Acme"), prefs) is None


def test_hard_filter_no_prefs() -> None:
    assert apply_hard_filters(_listing(market="us"), None) is None


# --- batch URL helpers ---
def test_parse_url_lines_skips_blanks_and_comments() -> None:
    text = "https://a.com/1\n\n  # a comment\nhttps://b.com/2  \n"
    assert parse_url_lines(text) == ["https://a.com/1", "https://b.com/2"]


def test_dedupe_preserving_order() -> None:
    assert dedupe_preserving_order(["a", "b", "a", "c", "b"]) == ["a", "b", "c"]
