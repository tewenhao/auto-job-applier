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


# --- Oracle HCM enumeration ---
def test_detect_board_oracle() -> None:
    from app.listings.discover import detect_board

    board = detect_board(
        "https://eofe.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/"
        'BNY-Careers/jobs?keyword=%22engineering%22&location=United+Kingdom'
    )
    assert board is not None
    kind, token, filt = board
    assert kind == "oracle"
    assert token == "eofe.fa.us2.oraclecloud.com|BNY-Careers"
    assert filt.keywords == ["engineering"]  # quotes stripped


def test_enumerate_oracle(monkeypatch) -> None:  # noqa: ANN001
    import app.listings.discover as d

    def fake_get(url: str):  # noqa: ANN202
        if "recruitingCESites" in url:
            return {
                "items": [
                    {
                        "SiteURLName": "BNY-Careers",
                        "SiteNumber": "CX_2001",
                        "StatusCode": "ORA_ACTIVE",
                    }
                ]
            }
        if "recruitingCEJobRequisitionDetails" in url:
            return {"items": [{"ExternalDescriptionStr": "<p>Build systems</p>"}]}
        if "recruitingCEJobRequisitions" in url:
            assert "CX_2001" in url and "keyword=engineering" in url
            return {
                "items": [
                    {
                        "requisitionList": [
                            {"Id": "1", "Title": "Engineering Intern", "PrimaryLocation": "London"},
                            {"Id": "2", "Title": "Marketing Lead", "PrimaryLocation": "London"},
                        ]
                    }
                ]
            }
        raise AssertionError(url)

    monkeypatch.setattr(d, "_get", fake_get)
    from app.listings.discover import BoardFilters, enumerate_board

    filt = BoardFilters(["engineering"], None, None)
    jobs = enumerate_board("oracle", "h.oraclecloud.com|BNY-Careers", filt)
    assert [j.role_title for j in jobs] == ["Engineering Intern"]
    assert jobs[0].company == "BNY" and jobs[0].from_api is True
    assert "Build systems" in (jobs[0].jd_text or "")


# --- Phenom enumeration ---
def test_detect_phenom_refnum() -> None:
    from app.listings.discover import detect_phenom_refnum

    assert detect_phenom_refnum('window.phApp={"refNum":"SIGGLOBAL"};') == "SIGGLOBAL"
    assert detect_phenom_refnum("<html>no phenom here</html>") is None


def test_enumerate_phenom(monkeypatch) -> None:  # noqa: ANN001
    import app.listings.discover as d

    def fake_post(url: str, payload):  # noqa: ANN202
        assert url.endswith("/widgets") and payload["refNum"] == "SIGGLOBAL"
        return {
            "refineSearch": {
                "data": {
                    "jobs": [
                        {
                            "title": "Software Engineering Intern",
                            "cityStateCountry": "London, UK",
                            "descriptionTeaser": "<p>Intern role</p>",
                            "applyUrl": "https://careers.sig.com/job/1",
                        },
                        {"title": "VP Trading", "cityStateCountry": "Chicago"},
                    ]
                }
            }
        }

    monkeypatch.setattr(d, "_post", fake_post)
    from app.listings.discover import enumerate_index_page

    jobs = enumerate_index_page(
        "https://careers.example.com/jobs?keyword=intern",
        'phenom config: x = {"refNum":"SIGGLOBAL"}',
    )
    assert [j.role_title for j in jobs] == ["Software Engineering Intern"]
    assert jobs[0].location == "London, UK" and jobs[0].from_api is True


# --- Eightfold / iCIMS enumeration (index-page ATS sniffing) ---
def test_enumerate_index_page_eightfold(monkeypatch) -> None:  # noqa: ANN001
    import app.listings.discover as d

    def fake_get(url: str):  # noqa: ANN202
        if "/api/apply/v2/jobs/" in url:
            return {"job_description": "<p>Build models</p>"}
        assert "domain=mlp.com" in url
        return {
            "positions": [
                {"id": 1, "name": "2027 Quantitative Developer Intern", "location": "London, UK"},
                {"id": 2, "name": "Head of Sales", "location": "London, UK"},
            ]
        }

    monkeypatch.setattr(d, "_get", fake_get)
    jobs = d.enumerate_index_page(
        "https://campusjobs.mlp.com/careers?domain=mlp.com&keyword=intern",
        "<html>powered by eightfold</html>",
    )
    assert [j.role_title for j in jobs] == ["2027 Quantitative Developer Intern"]
    assert jobs[0].from_api is True and "Build models" in (jobs[0].jd_text or "")


def test_enumerate_index_page_icims(monkeypatch) -> None:  # noqa: ANN001
    import app.listings.discover as d

    payload = {
        "jobs": [
            {
                "data": {
                    "slug": "11362",
                    "title": "Trading Systems Engineering Internship",
                    "brand": "Susquehanna International Group, LLP",
                    "location_name": "SIG",  # a brand alias, not a place
                    "full_location": "London, United Kingdom",
                    "description": "<p>Build trading systems</p>",
                }
            },
            {"data": {"slug": "1", "title": "VP Trading", "full_location": "Dublin"}},
        ]
    }
    monkeypatch.setattr(d, "_get", lambda url: payload)
    jobs = d.enumerate_index_page(
        "https://careers.sig.com/jobs?keyword=intern", "<html>icims tracker</html>"
    )
    assert [j.role_title for j in jobs] == ["Trading Systems Engineering Internship"]
    # full_location wins over the misleading location_name
    assert jobs[0].location == "London, United Kingdom"
    assert jobs[0].company == "Susquehanna International Group, LLP"


def test_oracle_site_number_prefers_url_name_and_active(monkeypatch) -> None:  # noqa: ANN001
    import app.listings.discover as d

    sites = {
        "items": [
            {
                "SiteNumber": "CX_1001",
                "SiteName": "BNY External Career Site",
                "StatusCode": "ORA_INACTIVE",
            },
            {
                "SiteNumber": "CX_3001",
                "SiteName": "BNY",
                "SiteURLName": "BNY-Careers",
                "StatusCode": "ORA_ACTIVE",
            },
        ]
    }
    monkeypatch.setattr(d, "_get", lambda url: sites)
    assert d._oracle_site_number("h", "BNY-Careers") == "CX_3001"


def test_oracle_site_number_accepts_site_number_in_path(monkeypatch) -> None:  # noqa: ANN001
    """Some tenants put the SiteNumber itself in the URL (DTCC: .../sites/CX_1),
    and several inactive sites can share a name."""
    import app.listings.discover as d

    sites = {
        "items": [
            {"SiteNumber": "CX_6001", "SiteName": "DTCC CE Site", "StatusCode": "ORA_INACTIVE"},
            {"SiteNumber": "CX_1", "SiteName": "DTCC CE Site", "StatusCode": "ORA_ACTIVE"},
        ]
    }
    monkeypatch.setattr(d, "_get", lambda url: sites)
    assert d._oracle_site_number("h", "CX_1") == "CX_1"


def test_eightfold_domain_derivation() -> None:
    from app.listings.discover import _eightfold_domain

    assert _eightfold_domain("campusjobs.mlp.com", "") == "mlp.com"
    # tenant hosted on Eightfold itself
    assert _eightfold_domain("mlp.eightfold.ai", "") == "mlp.com"
    # multi-part country TLD
    assert _eightfold_domain("careers.acme.co.uk", "") == "acme.co.uk"
    # an explicit ?domain= always wins
    assert _eightfold_domain("anything.com", "domain=given.com") == "given.com"


def test_is_single_posting_url_distinguishes_jobs_from_boards() -> None:
    """A URL whose shape names one posting must not be vetoed by the
    careers-index heuristic (some ATS pages render 'related roles')."""
    from app.listings.fetch import is_single_posting_url as single

    assert single(
        "https://ciena.wd5.myworkdayjobs.com/en-US/Careers/job/SWE-Intern_R031332"
    )
    assert single("https://job-boards.greenhouse.io/quadraturecapital/jobs/4255974")
    assert single("https://jobs.lever.co/acme/0a1b2c3d-4e5f-6789-abcd-ef0123456789")
    assert single("https://x.oraclecloud.com/hcmUI/CandidateExperience/en/sites/S/job/81318")

    assert not single("https://ciena.wd5.myworkdayjobs.com/en-US/Careers")
    assert not single("https://job-boards.greenhouse.io/embed/job_board?for=jump&keyword=x")
    assert not single("https://jobs.lever.co/palantir?commitment=Internship")
    assert not single("https://x.oraclecloud.com/hcmUI/CandidateExperience/en/sites/S/jobs?k=e")
    assert not single("https://www.janestreet.com/join-jane-street/open-roles/")


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


# --- rescoring against changed preferences -----------------------------------


class _FakeListingsRepo:
    def __init__(self, listings: list[Listing]) -> None:
        self.rows = {lst.id: lst for lst in listings}

    def list(self, candidate_id, **_kw):  # noqa: ANN001, ANN003, ANN201
        return list(self.rows.values())

    def upsert(self, listing):  # noqa: ANN001, ANN201
        self.rows[listing.id] = listing
        return listing


class _FakeProfileRepo:
    def __init__(self, prefs: Preferences | None) -> None:
        self.prefs = prefs
        self.summary_calls = 0

    def get_preferences(self, _candidate_id):  # noqa: ANN001, ANN201
        return self.prefs

    def get_master_profile(self, _candidate_id):  # noqa: ANN001, ANN201
        self.summary_calls += 1
        from app.profile.models import Candidate, MasterProfile

        return MasterProfile(candidate=Candidate(id=CID, full_name="X"))


class _FakeScorer:
    """Stands in for the model: every listing scores the same."""

    def __init__(self, score: int) -> None:
        self.score = score
        self.calls = 0

    def __call__(self, _llm, _listing, _prefs, _summary):  # noqa: ANN001, ANN204
        from app.listings.score import ScoreResult

        self.calls += 1
        return ScoreResult(score=self.score, rationale="because", matched=[], missing=[])


def _stored(status: ListingStatus, *, market: str = "uk", score: int = 50) -> Listing:
    return Listing(
        id=uuid4(),
        candidate_id=CID,
        source=ListingSource.MANUAL,
        company="Acme",
        role_title="SWE Intern",
        market=market,
        score=score,
        status=status,
    )


def _ingestor(  # noqa: ANN201
    listings: list[Listing],
    prefs: Preferences | None,
    scorer: _FakeScorer,
    monkeypatch,  # noqa: ANN001
):
    import app.listings.ingest as ingest_mod
    from app.listings.ingest import ListingIngestor

    monkeypatch.setattr(ingest_mod, "score_listing", scorer)
    return ListingIngestor(
        _FakeListingsRepo(listings),  # type: ignore[arg-type]
        _FakeProfileRepo(prefs),  # type: ignore[arg-type]
        llm=None,  # type: ignore[arg-type]
        threshold=70,
    )


def test_rescore_updates_undecided_listings(monkeypatch) -> None:  # noqa: ANN001
    listing = _stored(ListingStatus.NEW, score=40)
    scorer = _FakeScorer(85)
    results = _ingestor([listing], Preferences(candidate_id=CID), scorer, monkeypatch).rescore(CID)

    (r,) = results
    assert r.previous_score == 40 and r.listing.score == 85
    assert r.listing.status == ListingStatus.SURFACED  # crossed the threshold
    assert r.score_changed and r.status_changed and not r.flagged


def test_rescore_flags_a_chosen_listing_instead_of_dropping_it(monkeypatch) -> None:  # noqa: ANN001
    """The point of the whole feature: a hard filter is triage, and it does not
    get to overrule a decision the user made by hand."""
    listing = _stored(ListingStatus.CHOSEN, market="us", score=88)
    prefs = Preferences(candidate_id=CID, location_markets=["uk"])  # 'us' now excluded
    scorer = _FakeScorer(10)

    (r,) = _ingestor([listing], prefs, scorer, monkeypatch).rescore(CID)

    assert r.listing.status == ListingStatus.CHOSEN  # kept, not filtered
    assert r.flagged
    assert "market" in r.listing.score_breakdown["filter_conflict"]
    assert r.listing.score == 88  # the score it was chosen on, not overwritten with 0
    assert scorer.calls == 0  # and no model call was spent on it


def test_rescore_drops_an_undecided_listing_that_now_fails_a_filter(monkeypatch) -> None:  # noqa: ANN001
    listing = _stored(ListingStatus.SURFACED, market="us")
    prefs = Preferences(candidate_id=CID, location_markets=["uk"])

    (r,) = _ingestor([listing], prefs, _FakeScorer(90), monkeypatch).rescore(CID)

    assert r.listing.status == ListingStatus.FILTERED  # no decision to protect
    assert not r.flagged


def test_rescore_clears_a_stale_flag(monkeypatch) -> None:  # noqa: ANN001
    listing = _stored(ListingStatus.CHOSEN, market="uk")
    listing.score_breakdown = {"filter_conflict": "market 'us' not in preferred markets"}
    prefs = Preferences(candidate_id=CID, location_markets=["uk"])  # now passes again

    (r,) = _ingestor([listing], prefs, _FakeScorer(75), monkeypatch).rescore(CID)

    assert "filter_conflict" not in r.listing.score_breakdown
    assert r.listing.status == ListingStatus.CHOSEN


def test_rescore_reads_the_profile_once_not_once_per_listing(monkeypatch) -> None:  # noqa: ANN001
    """Ingestion loads the profile per listing; over a whole queue that is a
    read of the entire profile per row."""
    listings = [_stored(ListingStatus.NEW) for _ in range(5)]
    ingestor = _ingestor(listings, Preferences(candidate_id=CID), _FakeScorer(80), monkeypatch)
    ingestor.rescore(CID)
    assert ingestor.profile.summary_calls == 1
