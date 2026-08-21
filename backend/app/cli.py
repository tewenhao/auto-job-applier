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
def ingest() -> None:
    """Parse resume / LinkedIn / GitHub / essays / master-doc into the profile."""
    typer.echo("ingest: not implemented yet (Phase 2).")


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
