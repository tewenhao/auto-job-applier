"""Tests for the dashboard API (FastAPI).

Repositories are swapped out via ``app.dependency_overrides`` with in-memory
fakes, so these exercise the routing/serialization without Supabase or an LLM.
The slow generate/regenerate paths are covered only for their fast failure
branches (missing listing/application); the LLM+LaTeX pipeline itself is tested
elsewhere.
"""

from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.deps import get_gen_repo, get_listings_repo, get_profile_repo
from app.api.main import app
from app.generation.models import Application, ApplicationStatus
from app.listings.models import Listing, ListingSource
from app.profile.models import Candidate, Preferences

CID = uuid4()


class FakeGenRepo:
    def __init__(self, apps: list[Application]) -> None:
        self._apps = {a.id: a for a in apps}

    def list_applications(self, candidate_id):  # noqa: ANN001
        return list(self._apps.values())

    def get_application(self, application_id):  # noqa: ANN001
        return self._apps.get(application_id)

    def upsert_application(self, application):  # noqa: ANN001
        self._apps[application.id] = application
        return application


class FakeListingsRepo:
    def __init__(self, listings: list[Listing]) -> None:
        self._listings = {item.id: item for item in listings}

    def get(self, listing_id):  # noqa: ANN001
        return self._listings.get(listing_id)

    def list(self, candidate_id, **kw):  # noqa: ANN001
        return list(self._listings.values())


class FakeProfileRepo:
    def __init__(self) -> None:
        self._prefs: Preferences | None = None

    def get_or_create_default_candidate(self) -> Candidate:
        return Candidate(id=CID, full_name="Tester")

    def get_preferences(self, candidate_id):  # noqa: ANN001
        return self._prefs

    def set_preferences(self, prefs):  # noqa: ANN001
        self._prefs = prefs
        return prefs


def _listing() -> Listing:
    return Listing(
        id=uuid4(),
        candidate_id=CID,
        source=ListingSource.MANUAL,
        company="Acme",
        role_title="SWE Intern",
    )


def _application(listing_id, *, status=ApplicationStatus.DRAFT) -> Application:
    return Application(
        id=uuid4(),
        candidate_id=CID,
        listing_id=listing_id,
        status=status,
        cover_letter="Dear Acme,",
        resume_content=None,
    )


def _client(*, apps, listings) -> TestClient:
    gen = FakeGenRepo(apps)
    lst = FakeListingsRepo(listings)
    prof = FakeProfileRepo()
    app.dependency_overrides[get_gen_repo] = lambda: gen
    app.dependency_overrides[get_listings_repo] = lambda: lst
    app.dependency_overrides[get_profile_repo] = lambda: prof
    return TestClient(app)


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_health() -> None:
    client = TestClient(app)
    assert client.get("/api/health").json() == {"status": "ok"}


def test_list_applications_joins_listing() -> None:
    listing = _listing()
    a = _application(listing.id)
    client = _client(apps=[a], listings=[listing])

    rows = client.get("/api/applications").json()
    assert len(rows) == 1
    assert rows[0]["company"] == "Acme"
    assert rows[0]["role_title"] == "SWE Intern"
    assert rows[0]["status"] == "draft"


def test_get_application_detail() -> None:
    listing = _listing()
    a = _application(listing.id)
    client = _client(apps=[a], listings=[listing])

    detail = client.get(f"/api/applications/{a.id}").json()
    assert detail["company"] == "Acme"
    assert detail["cover_letter"] == "Dear Acme,"
    assert detail["resume"] is None
    assert detail["resume_pdf_available"] is False


def test_get_application_404() -> None:
    client = _client(apps=[], listings=[])
    resp = client.get(f"/api/applications/{uuid4()}")
    assert resp.status_code == 404


def test_approve_sets_status() -> None:
    listing = _listing()
    a = _application(listing.id)
    client = _client(apps=[a], listings=[listing])

    resp = client.post(f"/api/applications/{a.id}/approve", json={"submitted": False})
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"

    resp = client.post(f"/api/applications/{a.id}/approve", json={"submitted": True})
    assert resp.json()["status"] == "submitted"


def test_list_listings_flags_existing_drafts() -> None:
    with_draft = _listing()
    without_draft = _listing()
    a = _application(with_draft.id)
    client = _client(apps=[a], listings=[with_draft, without_draft])

    rows = {r["id"]: r for r in client.get("/api/listings").json()}
    assert rows[str(with_draft.id)]["application_id"] == str(a.id)
    assert rows[str(without_draft.id)]["application_id"] is None
    assert rows[str(with_draft.id)]["company"] == "Acme"


def test_save_resume_persists_edit(monkeypatch) -> None:  # noqa: ANN001
    from app.api import service
    from app.generation.resume import ExperienceEntry, TailoredResume

    listing = _listing()
    a = _application(listing.id)
    edited = TailoredResume(
        experience=[ExperienceEntry(title="Edited role", bullets=["Hand-written bullet"])],
        skills=[],
    )

    def fake_save(app_id, resume, *, max_pages):  # noqa: ANN001, ANN202
        assert app_id == a.id
        a.resume_content = resume.model_dump(mode="json")
        return a

    monkeypatch.setattr(service, "save_resume", fake_save)
    client = _client(apps=[a], listings=[listing])

    resp = client.put(
        f"/api/applications/{a.id}/resume",
        json={"resume": edited.model_dump(mode="json"), "max_pages": 1},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["resume"]["experience"][0]["title"] == "Edited role"
    assert body["resume"]["experience"][0]["bullets"] == ["Hand-written bullet"]


def test_save_resume_404(monkeypatch) -> None:  # noqa: ANN001
    from app.api import service
    from app.generation.resume import TailoredResume

    def fake_save(app_id, resume, *, max_pages):  # noqa: ANN001, ANN202
        raise KeyError(app_id)

    monkeypatch.setattr(service, "save_resume", fake_save)
    client = _client(apps=[], listings=[])
    resp = client.put(
        f"/api/applications/{uuid4()}/resume",
        json={"resume": TailoredResume().model_dump(mode="json")},
    )
    assert resp.status_code == 404


def test_cover_letter_pdf_served(monkeypatch, tmp_path) -> None:  # noqa: ANN001
    from app.api import service

    listing = _listing()
    a = _application(listing.id)
    pdf = tmp_path / "cl.pdf"
    pdf.write_bytes(b"%PDF-1.5\n...")

    monkeypatch.setattr(service, "ensure_cover_letter_pdf", lambda app: pdf)
    client = _client(apps=[a], listings=[listing])

    resp = client.get(f"/api/applications/{a.id}/cover_letter.pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"


def test_cover_letter_pdf_404_when_none(monkeypatch) -> None:  # noqa: ANN001
    from app.api import service

    listing = _listing()
    a = _application(listing.id)
    monkeypatch.setattr(service, "ensure_cover_letter_pdf", lambda app: None)
    client = _client(apps=[a], listings=[listing])

    resp = client.get(f"/api/applications/{a.id}/cover_letter.pdf")
    assert resp.status_code == 404


def test_preferences_round_trip() -> None:
    client = _client(apps=[], listings=[])

    assert client.get("/api/preferences").json()["resume_guidance"] is None

    put = client.put("/api/preferences", json={"resume_guidance": "  Prioritise paid roles.  "})
    assert put.json()["resume_guidance"] == "Prioritise paid roles."  # trimmed
    assert client.get("/api/preferences").json()["resume_guidance"] == "Prioritise paid roles."

    # empty clears
    cleared = client.put("/api/preferences", json={"resume_guidance": ""})
    assert cleared.json()["resume_guidance"] is None


def test_generate_missing_listing_404() -> None:
    client = _client(apps=[], listings=[])
    resp = client.post("/api/generate", json={"listing_id": str(uuid4())})
    assert resp.status_code == 404
