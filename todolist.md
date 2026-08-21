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
- [ ] `supabase/migrations/` — SQL for `candidate`, `source_documents`,
      `experiences`, `skills`, `github_profile`, `writing_samples`,
      `voice_profile`, `preferences`, `interview_sessions`, `interview_turns`.
- [ ] `backend/app/profile/models.py` — Pydantic models mirroring the schema
      (the shared contract).
- [ ] `backend/app/db/` — Supabase client.
- [ ] `backend/app/profile/` — data-access layer (upsert/get/export) +
      merge/dedup logic.
- [ ] Verify: `supabase db push` on a fresh project stands up the schema.

## Phase 2 — Ingestion
- [ ] Resume parser (PDF/DOCX → text → Haiku → experiences/skills). **Anchor
      input — build first against a real resume.**
- [ ] Master-doc parser (freeform Markdown/text, no length limit).
- [ ] Essays / cover-letter parser → `writing_samples` (+ any experiences).
- [ ] GitHub API client → `github_profile` (metadata only).
- [ ] LinkedIn export parser (ZIP/CSV → Haiku normalize).
- [ ] Retain every raw input in `source_documents`.
- [ ] `ingest` CLI command wiring all parsers.

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

## Later phases (expanded when reached)
- [ ] **Module 2** — Listing ingestion: manual paste first, then UK Tracker
      scraper; `listings` model with `source`; preference scoring;
      one-role-per-company grouping.
- [ ] **Module 3** — Application generation: tailored resume + humanified voiced
      cover letter (JD + scraped company values + master profile).
- [ ] **Module 4** — Dashboard skeleton; migrate interview + review queues to web.
- [ ] **Module 5** — Form auto-fill (Playwright) + essay answers + field review.
- [ ] **Module 6** — Gmail monitor (API + Pub/Sub) + response classification.
- [ ] **Module 7** — Tracker (Supabase source of truth + Notion-synced view).
- [ ] **Module 8** — Wire everything through the dashboard.
