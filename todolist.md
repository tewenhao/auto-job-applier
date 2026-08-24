# To-Do

Ordered roughly by dependency. Module 1 is broken into concrete steps; later
modules are high-level phases, expanded when we reach them.

## Phase 0 — Project scaffolding
- [x] Monorepo layout: `backend/`, `supabase/`, `frontend/` (reserved).
- [x] Python project: `pyproject.toml` (`uv`), Typer, Pydantic, Anthropic SDK,
      Supabase client, `pypdf`/`python-docx`, `httpx`.
- [x] `backend/app/config.py` — env-driven settings (API keys, model IDs,
      Supabase URL/keys, GitHub PAT).
- [x] `.env.example` + README setup steps (clone → env → schema → run).
- [x] `backend/app/llm/` — Anthropic client wrapper + per-task model config
      (Opus interview / Haiku parse, overridable).
- [x] `ajp check` command + config/llm tests; ruff + mypy clean.

## Phase 1 — Database & models
- [x] `supabase/migrations/` — SQL for `candidate`, `source_documents`,
      `experiences`, `skills`, `github_profile`, `writing_samples`,
      `voice_profile`, `preferences`, `interview_sessions`, `interview_turns`.
- [x] `backend/app/profile/models.py` — Pydantic models mirroring the schema
      (the shared contract) + `MasterProfile` aggregate + Markdown export.
- [x] `backend/app/db/` — Supabase client.
- [x] `backend/app/profile/` — data-access layer (upsert/get + natural-key
      dedup for experiences). LLM-based merge deferred to Phase 2 ingestion.
- [x] Verified locally: migration applies on real Postgres 16; models match all
      10 tables 1:1; `to_row` → Postgres → `from_row` round-trips.
- [ ] Verify `supabase db push` against a live Supabase project (needs creds).

## Phase 2 — Ingestion
- [x] Document text extraction (PDF/DOCX/TXT/MD).
- [x] LLM structured extraction (`messages.parse` + Pydantic schema, Haiku).
- [x] Resume parser (→ experiences/skills, contact backfill).
- [x] Master-doc parser (freeform; detail-preserving guidance).
- [x] Essays / cover-letter parser → `writing_samples`.
- [x] GitHub API client → `github_profile` (metadata only; pure transform tested).
- [x] Retain every raw input in `source_documents`.
- [x] `ingest` CLI command wiring all parsers.
- [x] Tests for deterministic pieces (extraction schema, mapping, github, docs).
- [x] Live run against real resume + master doc (41 exp / 42 skills extracted).
- [x] Refinement: semantic consolidation (`ajp consolidate`) — LLM cluster+merge
      of duplicate experiences; skills de-dup/re-categorize.
- [x] Refinement: `handling_notes` field (schema + extraction) so "do not surface"
      guidance is separated from `detail` and never output.
- [x] `ajp profile show [--notes]` wired up (Markdown render).
- [ ] LinkedIn export parser (ZIP/CSV → Haiku normalize) — deferred to Phase 2b.
- [ ] Live check: run `ajp consolidate` on real data; review, tune prompts.

## Phase 3 — Interview engine
- [ ] Gap detection over the ingested profile (thin bullets, missing
      why/proud-moment/working-style/culture/things-not-on-CV).
- [ ] Opus-driven adaptive conversation loop; write elaborations into
      experience `detail`.
- [ ] Quick structured preference capture (domains, markets, company size,
      avoid-list) → `preferences`; refine fuzzy prefs conversationally.
- [ ] Persist transcript to `interview_turns`; make it resumable.
- [ ] `interview` CLI command.

## Phase 4 — Voice model
- [ ] Distill `voice_profile` from `writing_samples` + interview transcript.
- [ ] Keep raw samples for few-shot use.
- [ ] `voice build` CLI command.

## Phase 5 — Editability & polish
- [ ] `profile show / export` → readable Markdown of the whole profile.
- [ ] `profile edit` (edit exported Markdown + re-import, or direct Supabase).
- [ ] Tests: parser fixtures, gap detection, DAL round-trips.
- [ ] Module 1 acceptance walk-through end to end.

## Module 2 — Listing ingestion (branch: feat/listing-ingestion)
- [x] `listings` schema + `Listing` model + repository (dedup by URL).
- [x] Preferences derived from profile (`ajp preferences derive/show/set`).
- [x] Manual ingest (`ajp listings add --url|--text`): fetch (Greenhouse/Lever
      JSON fast-paths + generic HTTP) → LLM parse → hard filters + LLM relevance
      score → store. `ajp listings list/choose/dismiss`.
- [x] company_group normalization (one-role-per-company grouping; enforcement
      of "pick one" deferred to dashboard/HITL).
- [ ] **UK Tracker scraper** — blocked on the tracker's source URL/format.
- [ ] Greenhouse/Lever/Workday board scrapers (beyond single-URL fast-paths).
- [ ] Live check: derive preferences, add a real listing, review scoring.

## Later phases (expanded when reached)
- [ ] **Module 3** — Application generation: tailored resume + humanified voiced
      cover letter (JD + scraped company values + master profile).
- [ ] **Module 4** — Dashboard skeleton; migrate interview + review queues to web.
- [ ] **Module 5** — Form auto-fill (Playwright) + essay answers + field review.
- [ ] **Module 6** — Gmail monitor (API + Pub/Sub) + response classification.
- [ ] **Module 7** — Tracker (Supabase source of truth + Notion-synced view).
- [ ] **Module 8** — Wire everything through the dashboard.
