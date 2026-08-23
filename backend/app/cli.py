"""Command-line entrypoint for the candidate-profile module.

This CLI is the interface for Module 1 until the dashboard (Module 4) arrives.
Phase 0 ships the skeleton plus a working ``check`` command; the ingest /
interview / voice / profile commands are stubs filled in over later phases.
"""

from __future__ import annotations

import typer

app = typer.Typer(
    help="auto-job-applier — candidate profile CLI (Module 1).",
    no_args_is_help=True,
    add_completion=False,
)

voice_app = typer.Typer(help="Voice-profile tools.", no_args_is_help=True)
profile_app = typer.Typer(help="Inspect and edit the master profile.", no_args_is_help=True)
app.add_typer(voice_app, name="voice")
app.add_typer(profile_app, name="profile")


@app.command()
def check() -> None:
    """Validate that configuration loads and report which inputs are wired up.

    Never prints secret values — only whether each is present.
    """
    from app.config import get_settings

    try:
        settings = get_settings()
    except Exception as exc:  # noqa: BLE001 - surface config errors plainly to the user
        typer.secho(f"Configuration error: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    def status(present: bool) -> str:
        return "configured" if present else "missing"

    typer.echo("Configuration loaded.")
    typer.echo(f"  Anthropic API key : {status(bool(settings.anthropic_api_key))}")
    typer.echo(f"  Interview model   : {settings.model_interview}")
    typer.echo(f"  Parse model       : {settings.model_parse}")
    typer.echo(f"  Supabase URL      : {status(bool(settings.supabase_url))}")
    typer.echo(f"  Supabase key      : {status(bool(settings.supabase_key))}")
    typer.echo(f"  GitHub token      : {status(bool(settings.github_token))}")
    typer.echo(f"  GitHub username   : {settings.github_username or 'missing'}")


@app.command()
def ingest(
    resume: str | None = typer.Option(
        None, help="Resume file, or a directory of resume versions (PDF/DOCX/TXT/MD)."
    ),
    master_doc: str | None = typer.Option(
        None, "--master-doc", help="Master document file, or a directory of them."
    ),
    essay: list[str] = typer.Option(  # noqa: B008 - typer option factory
        [], "--essay", help="Essay file or directory (repeatable)."
    ),
    cover_letter: list[str] = typer.Option(  # noqa: B008 - typer option factory
        [], "--cover-letter", help="Cover-letter file or directory (repeatable)."
    ),
    github: bool = typer.Option(
        False, "--github", help="Pull GitHub metadata (uses GITHUB_USERNAME/TOKEN)."
    ),
) -> None:
    """Parse resume / master-doc / essays / GitHub into the profile.

    Each raw input is retained verbatim in ``source_documents``. Resume and
    master-doc are structurally extracted into experiences + skills; essays and
    cover letters are kept as writing samples for voice.
    """
    from app.config import get_settings
    from app.ingestion import Ingestor
    from app.ingestion.documents import iter_documents
    from app.llm import LLMClient
    from app.profile.models import SourceType
    from app.profile.repository import ProfileRepository

    if not any([resume, master_doc, essay, cover_letter, github]):
        typer.secho(
            "Nothing to ingest — pass at least one input. See --help.",
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(code=1)

    settings = get_settings()
    repo = ProfileRepository()
    ingestor = Ingestor(repo, LLMClient(settings))
    candidate = repo.get_or_create_default_candidate()
    assert candidate.id is not None  # a persisted candidate always has an id
    candidate_id = candidate.id

    def run_doc(path: str, source_type: SourceType) -> None:
        files = iter_documents(path)
        if not files:
            typer.secho(f"  no supported documents found in {path}", fg=typer.colors.YELLOW)
            return
        for f in files:
            typer.echo(f"Ingesting {source_type.value}: {f} ...")
            summary = ingestor.ingest_document(f, source_type, candidate_id=candidate_id)
            typer.secho(f"  -> {summary}", fg=typer.colors.GREEN)

    if resume:
        run_doc(resume, SourceType.RESUME)
    if master_doc:
        run_doc(master_doc, SourceType.MASTER_DOC)
    for path in essay:
        run_doc(path, SourceType.ESSAY)
    for path in cover_letter:
        run_doc(path, SourceType.COVER_LETTER)
    if github:
        if not settings.github_username:
            typer.secho("GITHUB_USERNAME is not set in .env.", fg=typer.colors.RED)
            raise typer.Exit(code=1)
        typer.echo(f"Ingesting GitHub: @{settings.github_username} ...")
        summary = ingestor.ingest_github(
            settings.github_username, settings.github_token or None, candidate_id=candidate_id
        )
        typer.secho(f"  -> {summary}", fg=typer.colors.GREEN)

    typer.secho("Ingestion complete.", fg=typer.colors.GREEN, bold=True)


@app.command()
def interview() -> None:
    """Run the gap-aware onboarding interview."""
    typer.echo("interview: not implemented yet (Phase 3).")


@voice_app.command("build")
def voice_build() -> None:
    """Distill the voice profile from writing samples + interview transcript."""
    typer.echo("voice build: not implemented yet (Phase 4).")


@profile_app.command("show")
def profile_show() -> None:
    """Render the whole profile as readable Markdown."""
    typer.echo("profile show: not implemented yet (Phase 5).")


if __name__ == "__main__":
    app()
