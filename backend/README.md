# backend/

Python backend for auto-job-applier — the agent brain. Modules 1–3 (candidate
profile, listing ingestion, application generation) live here behind the `ajp`
CLI; scraping / Gmail / the dashboard backend arrive in later modules.

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

- `ANTHROPIC_API_KEY` — LLM access (parsing, consolidation, generation).
- `SUPABASE_URL` / `SUPABASE_KEY` — the profile database (source of truth).
- `GITHUB_TOKEN` / `GITHUB_USERNAME` — GitHub profile ingestion.

Model choice is per-task and overridable, e.g. `MODEL_INTERVIEW` /
`MODEL_CONSOLIDATE` / `MODEL_GENERATE` (default `claude-opus-5`) and
`MODEL_PARSE` (default `claude-haiku-4-5`).

Résumé generation renders LaTeX; if `latexmk` or `pdflatex` is installed it also
compiles a PDF and enforces the one-page limit. Without a TeX toolchain you still
get the `.tex` (compile it elsewhere); page count is then unverified.

## CLI

### Module 1 — candidate profile

```bash
uv run ajp check                       # validate config
uv run ajp ingest --resume … --master-doc … --essay … --cover-letter … \
        --linkedin export.zip --github [--fresh]   # populate the profile
uv run ajp consolidate                 # semantic dedup/merge of experiences + skills
uv run ajp profile show [--notes]      # render the profile as Markdown
uv run ajp profile add-note "<rule>"   # add a "do not surface" handling note
uv run ajp profile list-notes | remove-note <i>
uv run ajp voice build [--no-harvest]  # distill the voice profile (harvests master-doc VOICE)
uv run ajp preferences derive | show | set …   # job-search preferences
uv run ajp preferences set-guidance "<text>"   # standing résumé-generation priorities
```

Authoring the master-doc is supported by two skills in `.claude/skills/`:
`master-doc` (content: FACTS/VOICE/PRIVATE/LINKS) and `master-doc-write`
(formatting/parse-safety so every entry ingests cleanly).

### Module 2 — listings

```bash
uv run ajp listings add --url <job-url>          # ingest + score one listing
uv run ajp listings add-batch --file links.txt   # ingest + score many at once
uv run ajp listings list | show <id> | choose <id> | dismiss <id>
```

The Trackr is a subscription SPA — we don't scrape its API (ToS/account risk).
Browse it yourself and grab outbound application links with the
[`scripts/trackr-link-grabber.js`](../scripts/trackr-link-grabber.js) snippet
(run it in your browser console; it copies the links), then feed them to
`listings add-batch`. The individual application pages (Greenhouse/Lever/company
sites) are public and fetched normally.

### Module 3 — application generation

```bash
uv run ajp generate <listing_id> [--steer "…"] [--max-pages 1] [--refresh-company]
                                        # tailored resume (.tex/.pdf) + voiced cover letter,
                                        # written to out/<company>-<timestamp>/
uv run ajp application list                      # all applications: company, role, status
uv run ajp application ranking <id>              # why each experience/project was chosen
uv run ajp application show <id>                 # the cover letter + resume status
uv run ajp application approve <id> [--submitted]
```

`--steer` overrides selection/ranking for one application (e.g. "prioritise my
RSAF and IMDA roles over side projects"); `preferences set-guidance` makes such a
priority the standing default for every resume.

## Layout

```
app/
  config.py     env-driven settings + per-task model selection
  llm/          thin Anthropic wrapper (per-task models; complete/parse/research)
  ingestion/    input parsers: documents, GitHub, LinkedIn export, consolidation
  profile/      Pydantic models + Supabase DAL + Markdown render
  voice/        voice-profile distiller + master-doc VOICE harvest
  listings/     fetch (ATS fast-paths) + parse + score against preferences  (Module 2)
  generation/   company research, cover letter, résumé tailoring + LaTeX,
                one-page trim loop, ranking/steer                            (Module 3)
  db/           Supabase client
  cli.py        Typer entrypoint (the `ajp` command)
tests/
```

## Dev

```bash
uv run pytest        # tests
uv run ruff check .  # lint
uv run mypy app      # types
```
