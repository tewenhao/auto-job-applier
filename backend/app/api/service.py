"""Generation actions for the API — regenerate / generate, then render + compile.

These run the same ``generate_application`` pipeline as the CLI, then render the
tailored resume into the LaTeX template and (if a TeX toolchain is present)
compile a one-page PDF. Kept separate from the routes because they are the slow,
side-effecting operations (LLM calls + LaTeX), unlike the plain repository reads.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from app.generation.latex import compile_to_page_limit
from app.generation.models import Application
from app.generation.pipeline import generate_application
from app.generation.repository import GenerationRepository
from app.generation.resume import TailoredResume
from app.profile.repository import ProfileRepository

# The API compiles into a stable per-application directory so the dashboard can
# always find the current PDF.
API_OUT = Path("out/api")


def _compile_and_store(app: Application, *, max_pages: int) -> Application:
    """Render the stored resume, compile it (if a toolchain exists), and persist
    the possibly-trimmed result + PDF path."""
    if not app.resume_content:
        return app
    resume = TailoredResume.model_validate(app.resume_content)
    candidate = ProfileRepository().get_candidate(app.candidate_id)
    if candidate is None:
        return app

    dest = API_OUT / str(app.id)
    dest.mkdir(parents=True, exist_ok=True)
    result = compile_to_page_limit(resume, candidate, dest / "resume.tex", max_pages=max_pages)

    app.resume_tex = result.tex
    app.resume_content = result.resume.model_dump(mode="json")
    if result.pdf_path is not None:
        app.resume_pdf_path = str(result.pdf_path)
    if app.cover_letter:
        (dest / "cover_letter.txt").write_text(app.cover_letter)
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
    """Return the compiled PDF path, compiling on demand if needed."""
    if app.resume_pdf_path and Path(app.resume_pdf_path).exists():
        return Path(app.resume_pdf_path)
    app = _compile_and_store(app, max_pages=1)
    if app.resume_pdf_path and Path(app.resume_pdf_path).exists():
        return Path(app.resume_pdf_path)
    return None
