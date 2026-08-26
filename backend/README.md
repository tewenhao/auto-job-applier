# backend/

Python backend for auto-job-applier — the agent brain (ingestion, profile,
interview, voice, and later generation / scraping / Gmail). Module 1 lives
entirely here plus a CLI.

## Setup

Requires [`uv`](https://docs.astral.sh/uv/) and Python 3.11+.

```bash
cd backend
uv sync                      # create the venv and install deps
cp .env.example .env         # then fill in your keys
uv run ajp check             # validate configuration
```

## Configuration

All config is env-driven (see `.env.example`). Nothing personal is hardcoded, so
the repo is shareable — each user supplies their own:

- `ANTHROPIC_API_KEY` — LLM access (interview + parsing).
- `SUPABASE_URL` / `SUPABASE_KEY` — the profile database (source of truth).
- `GITHUB_TOKEN` / `GITHUB_USERNAME` — GitHub profile ingestion.

Model choice is per-task and overridable: `MODEL_INTERVIEW` (default
`claude-opus-5`) and `MODEL_PARSE` (default `claude-haiku-4-5`).

## CLI

```bash
uv run ajp check       # validate config (Phase 0)
uv run ajp ingest      # parse inputs into the profile (Phase 2)
uv run ajp interview   # gap-aware onboarding interview (Phase 3)
uv run ajp voice build # distill the voice profile (Phase 4)
uv run ajp profile show# render the profile as Markdown (Phase 5)
```

### Discovering roles from The Trackr

The Trackr is a subscription SPA — we don't scrape its API (ToS/account risk).
Instead, browse it yourself and grab the outbound application links with the
`scripts/trackr-link-grabber.js` snippet (run it in your browser console on a
Trackr tab; it copies the links), then feed them to `ajp listings add-batch`.
The individual application pages (Greenhouse/Lever/company sites) are public and
fetched normally.

## Layout

```
app/
  config.py     env-driven settings + per-task model selection
  llm/          thin Anthropic wrapper (per-task models, .raw for advanced use)
  ingestion/    input parsers                        (Phase 2)
  profile/      Pydantic models + Supabase DAL        (Phase 1)
  interview/    gap-aware conversation engine         (Phase 3)
  voice/        voice-profile distiller               (Phase 4)
  db/           Supabase client                       (Phase 1)
  cli.py        Typer entrypoint (the `ajp` command)
tests/
```

## Dev

```bash
uv run pytest        # tests
uv run ruff check .  # lint
uv run mypy app      # types
```
