# To-Do

Ordered roughly by dependency. Module 1 is broken into concrete steps; later
modules are high-level phases, expanded when we reach them.

**Status: Modules 1–4 complete. Module 5 (Form auto-fill) next.**
The conversational interview (Phase 3) was deferred — the voice model is built
from writing samples and preferences are captured via the `ajp preferences`
commands, so it isn't a blocker; revisit if gap-filling proves needed.

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
- [x] Live Supabase project in use (ingest/generate run against it end to end).

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
- [x] LinkedIn export parser (Phase 2b) — deterministic ZIP/CSV parse
      (positions/education/projects/honors/skills/profile); exact month dates;
      consolidation prefers LinkedIn dates over year-only defaults.
- [x] Live check: `ajp consolidate` on real data — 41→~30, merges correct,
      handling_notes cleanly separated (minor residual nits noted).

## Phase 3 — Interview engine (DEFERRED)
- [x] Structured preference capture → `preferences` (via `ajp preferences
      derive/show/set`, not a conversation).
- [ ] Gap detection over the ingested profile (thin bullets, missing
      why/proud-moment/working-style/culture/things-not-on-CV). — deferred
- [ ] Opus-driven adaptive conversation loop writing elaborations into
      experience `detail`; persist transcript to `interview_turns`, resumable;
      `interview` CLI. — deferred (revisit if gap-filling is needed)

## Phase 4 — Voice model
- [x] Distill `voice_profile` from `writing_samples` (interview transcript input
      deferred) + harvest master-doc VOICE passages.
- [x] Keep raw samples for few-shot use (style-only at generation time).
- [x] `voice build` CLI command.

## Phase 5 — Editability & polish
- [x] `profile show [--notes]` → readable Markdown of the whole profile.
- [x] Editability: `profile add-note/list-notes/remove-note` handling notes;
      `preferences set-guidance`. (Full Markdown-export-and-reimport not needed.)
- [x] Tests: parser/renderer fixtures, mapping, LinkedIn, trim, DAL pieces.
- [x] Module 1 acceptance: real ingest → consolidate → voice → generate, end to end.

## Module 2 — Listing ingestion (branch: feat/listing-ingestion)
- [x] `listings` schema + `Listing` model + repository (dedup by URL).
- [x] Preferences derived from profile (`ajp preferences derive/show/set`).
- [x] Manual ingest (`ajp listings add --url|--text`): fetch (Greenhouse/Lever
      JSON fast-paths + generic HTTP) → LLM parse → hard filters + LLM relevance
      score → store. `ajp listings list/choose/dismiss`.
- [x] company_group normalization (one-role-per-company grouping; enforcement
      of "pick one" deferred to dashboard/HITL).
- [x] Batch ingest (`ajp listings add-batch`) + Trackr link-grabber snippet
      (`scripts/trackr-link-grabber.js`). UK Tracker (The Trackr) is a paid SPA;
      scraping its API is ToS/account-risky, so we grab links browser-side and
      batch-ingest the public application pages instead.
- [x] Structured ATS fast-paths beyond Greenhouse/Lever: Workday (the `wday/cxs`
      JSON twin), Greenhouse embeds on company domains (`?gh_jid=`).
- [x] Board enumeration — a *board* URL expands into every posting matching the
      filters already in that URL (keyword / location / commitment), instead of
      being rejected as an index page: Greenhouse, Lever, Oracle HCM, plus
      Eightfold and iCIMS (sniffed from the rendered HTML, since neither is
      identifiable from the URL alone). Verified across several tenants.
- [x] Headless-browser fallback (optional `browser` extra) for JS-rendered or
      bot-gated pages, used only when the HTTP fetch comes back empty.
- [x] Ingestion quality: role/company from `<title>`/OG tags; reject careers
      index pages; never index-gate a URL whose shape names one posting.
- [x] Live check: derive preferences, add real listings, review scoring
      (69 of 76 roles from a 33-URL Trackr batch ingest end-to-end).

## Module 3 — Application generation (branch: feat/application-generation)
- [x] Voice distillation (`ajp voice build`) — style guide from writing samples.
- [x] `applications` + `company_briefs` schema (migration 005).
- [x] Company research (`llm.research` web-search brief, cached per company,
      graceful fallback) grounded per company.
- [x] Cover-letter generation (JD + brief + profile + voice + handling_notes,
      humanified; style-only writing samples) → `ajp generate <listing_id>`.
      Validated across contrasting employers (quant vs sovereign fund).
- [x] Résumé tailoring + render into the user's jakegut LaTeX template → .tex/PDF.
      Grounded (no invented metrics; GitHub language bytes are not skills),
      handling_notes honoured, reverse-chronological, hobbies, math ~.
- [x] One-page guarantee: compile → measure → depth-preserving trim loop
      (`--max-pages`); fill-the-page generation.
- [x] Selection transparency: `ajp application ranking <id>` (scored, in/out,
      rationale) + `ajp generate --steer "..."` to override and regenerate.
- [x] Review loop: `ajp application list` / `show` / `approve [--submitted]`.
- [x] Live check: `voice build`, then `generate` for chosen listings; reviewed
      and iterated (Citadel, GIC, and others).

## Module 4 — Dashboard (branch: feat/dashboard)
- [x] FastAPI layer over the existing repositories + pipeline (`ajp serve`), so
      the CLI and the web UI drive identical code paths. Repos arrive via
      `Depends`, so tests swap fakes in — no Supabase needed.
- [x] Next.js (App Router) client: Listings, Add, Applications, Priorities.
- [x] Listings view — scored queue, links out to the original posting, and a
      Generate button per role.
- [x] Application review — the tailorer's ranking (score, rationale, in/out), a
      steer box that re-runs generation, approve / mark submitted.
- [x] Hand-editing: résumé (structured editor for education / experience /
      projects / skills, reorderable bullets) and cover letter (plain text).
      Saving re-renders the PDF deterministically — no model call.
- [x] Priorities editor — the standing résumé guidance, shared with
      `ajp preferences set-guidance`.
- [x] Cover letter rendered to PDF via LaTeX, matching the résumé's header/font.
- [x] Add listings from the browser — paste URLs (boards expand) or a JD;
      results stream in per URL, skips shown with their reason.
- [ ] Live check: run the full loop in the browser for a fresh batch.

## Later phases (expanded when reached)
- [ ] **Module 5** — Form auto-fill (Playwright) + essay answers + field review.
- [ ] **Module 6** — Gmail monitor (API + Pub/Sub) + response classification.
- [ ] **Module 7** — Tracker (Supabase source of truth + Notion-synced view).
- [ ] **Module 8** — Wire everything through the dashboard.
