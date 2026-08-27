"""Tests for the deterministic listing pieces (no LLM/network)."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

from app.listings.fetch import (
    _clean_title,
    _extract_head_meta,
    build_from_greenhouse,
    build_from_lever,
    detect_ats,
    html_to_text,
    parse_greenhouse_url,
    parse_lever_url,
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
