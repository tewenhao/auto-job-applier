"""Generation actions for the API — regenerate / generate, then render + compile.

These run the same ``generate_application`` pipeline as the CLI, then render the
tailored resume into the LaTeX template and (if a TeX toolchain is present)
compile a one-page PDF. Kept separate from the routes because they are the slow,
side-effecting operations (LLM calls + LaTeX), unlike the plain repository reads.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from app.generation.cover_letter_latex import compile_cover_letter
from app.generation.latex import compile_to_page_limit
from app.generation.models import Application
from app.generation.naming import COVER_LETTER, RESUME, document_filename
from app.generation.pipeline import generate_application
from app.generation.repository import GenerationRepository
from app.generation.resume import TailoredResume
from app.listings.repository import ListingRepository
from app.profile.repository import ProfileRepository

# The API compiles into a stable per-application directory so the dashboard can
# always find the current PDF.
API_OUT = Path("out/api")

# meta key holding the compiled cover-letter PDF path (Application has dedicated
# columns for the resume, but not the cover letter — reuse the meta jsonb).
COVER_LETTER_PDF_KEY = "cover_letter_pdf_path"


def _compile_and_store(app: Application, *, max_pages: int) -> Application:
    """Render + compile the stored resume and cover letter (if a toolchain
    exists) and persist the results — the possibly-trimmed resume + its PDF path,
    and the cover-letter PDF path (in meta)."""
    candidate = ProfileRepository().get_candidate(app.candidate_id)
    if candidate is None:
        return app

    dest = API_OUT / str(app.id)
    dest.mkdir(parents=True, exist_ok=True)
    listing = ListingRepository().get(app.listing_id)
    company = listing.company if listing else None

    def _name(kind: str, ext: str) -> str:
        return document_filename(
            candidate_name=candidate.full_name, company=company, kind=kind, ext=ext
        )

    if app.resume_content:
        resume = TailoredResume.model_validate(app.resume_content)
        result = compile_to_page_limit(
            resume, candidate, dest / _name(RESUME, "tex"), max_pages=max_pages
        )
        app.resume_tex = result.tex
        app.resume_content = result.resume.model_dump(mode="json")
        if result.pdf_path is not None:
            app.resume_pdf_path = str(result.pdf_path)

    if app.cover_letter:
        (dest / _name(COVER_LETTER, "txt")).write_text(app.cover_letter)
        _, cl_pdf = compile_cover_letter(
            app.cover_letter, candidate, listing, dest / _name(COVER_LETTER, "tex")
        )
        if cl_pdf is not None:
            app.meta = {**app.meta, COVER_LETTER_PDF_KEY: str(cl_pdf)}

    return GenerationRepository().upsert_application(app)


def save_resume(application_id: UUID, resume: TailoredResume, *, max_pages: int) -> Application:
    """Persist a hand-edited resume and re-render it — no LLM involved.

    This is the manual-edit counterpart to ``regenerate``: the user is the final
    editor, and we deterministically render + compile exactly what they saved
    (still trimming only if it overflows ``max_pages``)."""
    existing = GenerationRepository().get_application(application_id)
    if existing is None:
        raise KeyError(application_id)
    existing.resume_content = resume.model_dump(mode="json")
    return _compile_and_store(existing, max_pages=max_pages)


def save_cover_letter(application_id: UUID, text: str) -> Application:
    """Persist a hand-edited cover letter and re-render its PDF — no LLM, and
    only the cover letter (the resume is left untouched)."""
    gen = GenerationRepository()
    existing = gen.get_application(application_id)
    if existing is None:
        raise KeyError(application_id)

    cleaned = text.strip()
    existing.cover_letter = cleaned or None
    candidate = ProfileRepository().get_candidate(existing.candidate_id)
    meta = {k: v for k, v in existing.meta.items() if k != COVER_LETTER_PDF_KEY}
    if cleaned and candidate is not None:
        dest = API_OUT / str(existing.id)
        dest.mkdir(parents=True, exist_ok=True)
        listing = ListingRepository().get(existing.listing_id)
        company = listing.company if listing else None

        def _name(ext: str) -> str:
            return document_filename(
                candidate_name=candidate.full_name,
                company=company,
                kind=COVER_LETTER,
                ext=ext,
            )

        (dest / _name("txt")).write_text(cleaned)
        _, cl_pdf = compile_cover_letter(cleaned, candidate, listing, dest / _name("tex"))
        if cl_pdf is not None:
            meta[COVER_LETTER_PDF_KEY] = str(cl_pdf)
    existing.meta = meta
    return gen.upsert_application(existing)


def regenerate(
    application_id: UUID, *, steer: str | None, refresh_company: bool, max_pages: int
) -> Application:
    """Re-run generation for an existing application (optionally steered)."""
    existing = GenerationRepository().get_application(application_id)
    if existing is None:
        raise KeyError(application_id)
    updated = generate_application(
        existing.listing_id, refresh_company=refresh_company, steer=steer
    )
    return _compile_and_store(updated, max_pages=max_pages)


def generate_new(listing_id: UUID, *, steer: str | None, max_pages: int) -> Application:
    """Generate an application for a listing that has none yet (or refresh it)."""
    app = generate_application(listing_id, steer=steer)
    return _compile_and_store(app, max_pages=max_pages)


def ensure_pdf(app: Application) -> Path | None:
    """Return the compiled resume PDF path, compiling on demand if needed."""
    if app.resume_pdf_path and Path(app.resume_pdf_path).exists():
        return Path(app.resume_pdf_path)
    app = _compile_and_store(app, max_pages=1)
    if app.resume_pdf_path and Path(app.resume_pdf_path).exists():
        return Path(app.resume_pdf_path)
    return None


def cover_letter_pdf_path(app: Application) -> Path | None:
    """The stored cover-letter PDF path if it exists on disk, else None."""
    stored = app.meta.get(COVER_LETTER_PDF_KEY)
    return Path(stored) if stored and Path(stored).exists() else None


def ensure_cover_letter_pdf(app: Application) -> Path | None:
    """Return the compiled cover-letter PDF path, compiling on demand if needed."""
    existing = cover_letter_pdf_path(app)
    if existing is not None:
        return existing
    if not app.cover_letter:
        return None
    return cover_letter_pdf_path(_compile_and_store(app, max_pages=1))


def commit_master_doc_entry(section: str, markdown: str, *, candidate_id: UUID) -> tuple[str, str]:
    """Append a reviewed entry to the master-doc, then re-ingest the doc.

    Re-ingesting the whole document (rather than inserting the entry straight
    into the database) keeps the doc canonical: `ajp ingest --fresh` rebuilds
    from it, so anything written only to the database would be lost.
    Deduplication means re-reading the unchanged entries is harmless.
    """
    from app.config import get_settings
    from app.ingestion import Ingestor
    from app.llm import LLMClient
    from app.profile.master_doc import append_entry_to_file
    from app.profile.models import SourceType
    from app.profile.repository import ProfileRepository

    path = Path(get_settings().master_doc_path)
    if not path.exists():
        raise FileNotFoundError(
            f"No master document at {path}. Set MASTER_DOC_PATH to point at it."
        )

    append_entry_to_file(path, section, markdown)

    repo = ProfileRepository()
    ingestor = Ingestor(repo, LLMClient())
    summary = ingestor.ingest_document(
        path, SourceType.MASTER_DOC, candidate_id=candidate_id, dedup=True
    )
    return str(path), str(summary)
