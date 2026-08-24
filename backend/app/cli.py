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
prefs_app = typer.Typer(help="Job-search preferences.", no_args_is_help=True)
listings_app = typer.Typer(help="Ingest, score, and review job listings.", no_args_is_help=True)
app.add_typer(voice_app, name="voice")
app.add_typer(profile_app, name="profile")
app.add_typer(prefs_app, name="preferences")
app.add_typer(listings_app, name="listings")


def _split(value: str | None) -> list[str] | None:
    """Parse a comma-separated CLI option into a list (None if not provided)."""
    if value is None:
        return None
    return [v.strip() for v in value.split(",") if v.strip()]


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
    fresh: bool = typer.Option(
        False,
        "--fresh",
        help="Clear this candidate's source docs, experiences, skills, and writing "
        "samples first, for a clean rebuild. (GitHub + contact are left in place.)",
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

    if not any([resume, master_doc, essay, cover_letter, github, fresh]):
        typer.secho(
            "Nothing to ingest — pass at least one input (or --fresh). See --help.",
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(code=1)

    settings = get_settings()
    repo = ProfileRepository()
    ingestor = Ingestor(repo, LLMClient(settings))
    candidate = repo.get_or_create_default_candidate()
    assert candidate.id is not None  # a persisted candidate always has an id
    candidate_id = candidate.id

    if fresh:
        typer.secho(
            "--fresh: clearing source docs, experiences, skills, writing samples ...",
            fg=typer.colors.YELLOW,
        )
        repo.clear_experiences(candidate_id)
        repo.clear_skills(candidate_id)
        repo.clear_writing_samples(candidate_id)
        repo.clear_source_documents(candidate_id)

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
def consolidate(
    experiences: bool = typer.Option(True, help="Cluster + merge duplicate experiences."),
    skills: bool = typer.Option(True, help="De-duplicate and re-categorize skills."),
) -> None:
    """Semantically merge duplicate experiences and clean up skills.

    Operates on data already in the profile (does not re-read source documents).
    """
    from app.ingestion.consolidate import consolidate_experiences, consolidate_skills
    from app.llm import LLMClient
    from app.profile.repository import ProfileRepository

    repo = ProfileRepository()
    llm = LLMClient()
    candidate = repo.get_or_create_default_candidate()
    assert candidate.id is not None
    candidate_id = candidate.id

    if experiences:
        typer.echo("Consolidating experiences (this calls the model a few times) ...")
        result = consolidate_experiences(repo, llm, candidate_id)
        typer.secho(
            f"  experiences: {result['before']} -> {result['after']}", fg=typer.colors.GREEN
        )
    if skills:
        typer.echo("Consolidating skills ...")
        result = consolidate_skills(repo, llm, candidate_id)
        typer.secho(f"  skills: {result['before']} -> {result['after']}", fg=typer.colors.GREEN)

    typer.secho("Consolidation complete.", fg=typer.colors.GREEN, bold=True)


@app.command()
def interview() -> None:
    """Run the gap-aware onboarding interview."""
    typer.echo("interview: not implemented yet (Phase 3).")


@voice_app.command("build")
def voice_build() -> None:
    """Distill the voice profile from writing samples + interview transcript."""
    typer.echo("voice build: not implemented yet (Phase 4).")


@profile_app.command("show")
def profile_show(
    notes: bool = typer.Option(
        False, "--notes", help="Include internal handling notes (never surfaced downstream)."
    ),
) -> None:
    """Render the whole profile as readable Markdown."""
    from app.profile.markdown import profile_to_markdown
    from app.profile.repository import ProfileRepository

    repo = ProfileRepository()
    candidate = repo.get_or_create_default_candidate()
    assert candidate.id is not None
    profile = repo.get_master_profile(candidate.id)
    typer.echo(profile_to_markdown(profile, include_handling_notes=notes))


# --- preferences ---
@prefs_app.command("derive")
def preferences_derive() -> None:
    """Draft preferences from the master profile (LLM), then save them."""
    from app.llm import LLMClient
    from app.profile.preferences import derive_preferences, draft_to_preferences
    from app.profile.repository import ProfileRepository

    repo = ProfileRepository()
    candidate = repo.get_or_create_default_candidate()
    assert candidate.id is not None
    profile = repo.get_master_profile(candidate.id)

    typer.echo("Deriving preferences from your profile ...")
    draft = derive_preferences(LLMClient(), profile)
    saved = repo.set_preferences(draft_to_preferences(draft, candidate_id=candidate.id))
    _print_preferences(saved)
    typer.secho("Saved. Edit with `ajp preferences set` or in Supabase.", fg=typer.colors.GREEN)


@prefs_app.command("show")
def preferences_show() -> None:
    """Show current preferences."""
    from app.profile.repository import ProfileRepository

    repo = ProfileRepository()
    candidate = repo.get_or_create_default_candidate()
    assert candidate.id is not None
    prefs = repo.get_preferences(candidate.id)
    if prefs is None:
        typer.secho("No preferences set. Run `ajp preferences derive`.", fg=typer.colors.YELLOW)
        raise typer.Exit(code=1)
    _print_preferences(prefs)


@prefs_app.command("set")
def preferences_set(
    role_types: str | None = typer.Option(None, help="Comma-separated; replaces the field."),
    domains: str | None = typer.Option(None, help="Comma-separated (swe,ml,quant,...)."),
    industries: str | None = typer.Option(None, help="Comma-separated."),
    company_sizes: str | None = typer.Option(None, help="Comma-separated (startup,midsize,large)."),
    markets: str | None = typer.Option(None, help="Comma-separated (uk,sg,us,cn)."),
    avoid: str | None = typer.Option(None, help="Comma-separated things to avoid."),
) -> None:
    """Overwrite specific preference fields (only the ones you pass)."""
    from app.profile.models import Preferences
    from app.profile.repository import ProfileRepository

    repo = ProfileRepository()
    candidate = repo.get_or_create_default_candidate()
    assert candidate.id is not None
    prefs = repo.get_preferences(candidate.id) or Preferences(candidate_id=candidate.id)

    for field, value in (
        ("role_types", _split(role_types)),
        ("domains", _split(domains)),
        ("industries", _split(industries)),
        ("company_sizes", _split(company_sizes)),
        ("location_markets", _split(markets)),
        ("avoid", _split(avoid)),
    ):
        if value is not None:
            setattr(prefs, field, value)

    _print_preferences(repo.set_preferences(prefs))
    typer.secho("Saved.", fg=typer.colors.GREEN)


def _print_preferences(prefs) -> None:  # type: ignore[no-untyped-def]
    typer.echo("Preferences:")
    for label, values in (
        ("Role types", prefs.role_types),
        ("Domains", prefs.domains),
        ("Industries", prefs.industries),
        ("Company sizes", prefs.company_sizes),
        ("Markets", prefs.location_markets),
        ("Avoid", prefs.avoid),
    ):
        typer.echo(f"  {label}: {', '.join(values) if values else '-'}")


# --- listings ---
@listings_app.command("add")
def listings_add(
    url: str | None = typer.Option(None, help="Job posting URL."),
    text: str | None = typer.Option(None, help="Raw JD text (for pages that won't fetch)."),
) -> None:
    """Ingest one listing from a URL or pasted JD text; parse and score it."""
    from app.listings.ingest import ListingIngestor
    from app.listings.repository import ListingRepository
    from app.llm import LLMClient
    from app.profile.repository import ProfileRepository

    if not url and not text:
        typer.secho("Pass --url or --text.", fg=typer.colors.YELLOW)
        raise typer.Exit(code=1)

    profile_repo = ProfileRepository()
    candidate = profile_repo.get_or_create_default_candidate()
    assert candidate.id is not None
    ingestor = ListingIngestor(ListingRepository(), profile_repo, LLMClient())

    typer.echo("Fetching, parsing, and scoring ...")
    listing = ingestor.ingest_manual(candidate_id=candidate.id, url=url, text=text)
    typer.secho(
        f"[{listing.score}] {listing.role_title} @ {listing.company} "
        f"({listing.status}) — {listing.score_rationale}",
        fg=typer.colors.GREEN,
    )


@listings_app.command("add-batch")
def listings_add_batch(
    urls: list[str] | None = typer.Argument(  # noqa: B008 - typer argument factory
        None, help="Job URLs (space-separated)."
    ),
    file: str | None = typer.Option(
        None, "--file", help="Path to a file of URLs (one per line; # comments ok)."
    ),
) -> None:
    """Ingest many listings at once from URLs and/or a file (fetch, parse, score each).

    Pairs with the Trackr link-grabber snippet: grab links in your browser, paste
    them here (or into a file) and this fetches/scores them all. Failures on one
    URL don't stop the rest.
    """
    from pathlib import Path

    from app.listings.ingest import (
        ListingIngestor,
        dedupe_preserving_order,
        parse_url_lines,
    )
    from app.listings.repository import ListingRepository
    from app.llm import LLMClient
    from app.profile.repository import ProfileRepository

    collected = list(urls or [])
    if file:
        collected += parse_url_lines(Path(file).read_text(encoding="utf-8"))
    targets = dedupe_preserving_order(collected)
    if not targets:
        typer.secho("No URLs given. Pass URLs or --file.", fg=typer.colors.YELLOW)
        raise typer.Exit(code=1)

    profile_repo = ProfileRepository()
    candidate = profile_repo.get_or_create_default_candidate()
    assert candidate.id is not None
    ingestor = ListingIngestor(ListingRepository(), profile_repo, LLMClient())

    ok = 0
    failed = 0
    typer.echo(f"Ingesting {len(targets)} URLs ...")
    for url in targets:
        try:
            listing = ingestor.ingest_manual(candidate_id=candidate.id, url=url)
            ok += 1
            typer.secho(
                f"  [{listing.score}] {listing.status:9} "
                f"{listing.role_title} @ {listing.company}",
                fg=typer.colors.GREEN,
            )
        except Exception as exc:  # noqa: BLE001 - one bad URL shouldn't abort the batch
            failed += 1
            typer.secho(f"  [skip] {url}: {exc}", fg=typer.colors.RED)

    typer.secho(
        f"Done: {ok} ingested, {failed} skipped. See `ajp listings list`.",
        fg=typer.colors.GREEN,
        bold=True,
    )


@listings_app.command("list")
def listings_list(
    all_: bool = typer.Option(False, "--all", help="Show all, not just surfaced."),
) -> None:
    """List scored listings, highest score first."""
    from app.listings.models import ListingStatus
    from app.listings.repository import ListingRepository
    from app.profile.repository import ProfileRepository

    candidate = ProfileRepository().get_or_create_default_candidate()
    assert candidate.id is not None
    repo = ListingRepository()
    listings = repo.list(
        candidate.id, status=None if all_ else ListingStatus.SURFACED
    )
    if not listings:
        typer.echo("No listings." if all_ else "No surfaced listings. Try --all.")
        return
    typer.secho(f"{'SCORE':>5}  {'STATUS':9}  ROLE @ COMPANY  (market/domain)", bold=True)
    for lst in listings:
        score = str(lst.score) if lst.score is not None else "--"
        typer.echo(
            f"{score:>5}  {lst.status:9}  {lst.role_title} @ {lst.company}  "
            f"({lst.market}/{lst.domain})"
        )
        typer.secho(f"        {lst.id}", dim=True)
    typer.echo("\nUse `ajp listings show <id>` for the JD summary and scoring rationale.")


@listings_app.command("show")
def listings_show(listing_id: str) -> None:
    """Show one listing in full, including the scoring rationale."""
    from uuid import UUID

    from app.listings.repository import ListingRepository

    lst = ListingRepository().get(UUID(listing_id))
    if lst is None:
        typer.secho("No listing with that id.", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    typer.secho(f"{lst.role_title}  @  {lst.company}", bold=True)
    typer.echo(
        f"  score {lst.score}  |  status {lst.status}  |  {lst.market}/{lst.domain}"
        f"  |  ats {lst.ats}"
    )
    for label, value in (("location", lst.location), ("deadline", lst.deadline), ("url", lst.url)):
        if value:
            typer.echo(f"  {label}: {value}")

    if lst.jd_summary:
        typer.echo(f"\nSummary:\n  {lst.jd_summary}")
    if lst.requirements:
        typer.echo("\nRequirements:")
        for r in lst.requirements:
            typer.echo(f"  - {r}")

    typer.secho("\nWhy this score:", bold=True)
    if lst.score_rationale:
        typer.echo(f"  {lst.score_rationale}")
    breakdown = lst.score_breakdown or {}
    if breakdown.get("filtered"):
        typer.secho(f"  filtered: {breakdown['filtered']}", fg=typer.colors.YELLOW)
    for label, key in (("matched", "matched"), ("missing", "missing")):
        items = breakdown.get(key) or []
        if items:
            typer.echo(f"  {label}:")
            for item in items:
                typer.echo(f"    - {item}")


@listings_app.command("choose")
def listings_choose(listing_id: str) -> None:
    """Mark a listing as chosen (the HITL gate into generation)."""
    _set_listing_status(listing_id, "chosen")


@listings_app.command("dismiss")
def listings_dismiss(listing_id: str) -> None:
    """Dismiss a listing."""
    _set_listing_status(listing_id, "dismissed")


def _set_listing_status(listing_id: str, status: str) -> None:
    from uuid import UUID

    from app.listings.models import ListingStatus
    from app.listings.repository import ListingRepository

    ListingRepository().set_status(UUID(listing_id), ListingStatus(status))
    typer.secho(f"Listing {listing_id} -> {status}.", fg=typer.colors.GREEN)


if __name__ == "__main__":
    app()
