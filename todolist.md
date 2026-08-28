# To-Do

Ordered roughly by dependency. Module 1 is broken into concrete steps; later
modules are high-level phases, expanded when we reach them.

**Status: Modules 1–4 complete. Module 5 (Form auto-fill) next.**
Phase 3's interview was eventually built, scoped down: it captures **one new
entry into the master-doc at a time** (`ajp interview`, or the dashboard's
Profile page) rather than sweeping the whole profile for gaps. Preferences stay
structured, via the `ajp preferences` commands.

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

## Phase 3 — Interview engine
- [x] Structured preference capture → `preferences` (via `ajp preferences
      derive/show/set`, not a conversation).
- [x] Entry-capture interview (`app/profile/interview.py`): one question at a
      time, drawing out what a résumé needs and people leave out — their
      contribution as distinct from the team's, the stack, honest status, real
      figures — then drafting the entry in the master-doc's canonical format
      for review. `ajp interview [--fresh] [--section]` and the dashboard's
      Profile page drive the same functions.
- [x] Resumable: the transcript persists to `interview_sessions` /
      `interview_turns`, so a session survives a reload or a Ctrl-C and can be
      continued in either surface.
- [x] The reviewed draft is written into the **master-doc**, never straight
      into the database — ingest rebuilds the database from the doc, so a
      row-level write would be undone by the next ingest and lost on `--fresh`.
- [x] Reliability, all found live: a transcript ending on the assistant's
      unanswered question is nudged rather than sent (was a 500); `LLMClient`
      retries the API's transient generic 400 (the SDK never retries 4xx);
      consecutive same-role turns are merged so a failed call can't wedge a
      session permanently.
- [x] Effort tuning: `next_step` runs at `effort="low"` (choosing a question is
      routing, not reasoning) and `draft_entry` at `"medium"`. At the default,
      adaptive thinking consumed the whole 16k budget and truncated the model's
      own JSON — ~40s a turn and flaky; now ~7s round trip, 6/6 live runs.
- [ ] Gap detection over the ingested profile (thin bullets, missing
      why/proud-moment/working-style/culture/things-not-on-CV). — still not
      built. The entry interview covers "add the thing that's missing"; sweeping
      the whole profile for thin spots hasn't been needed yet.

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
- [x] Next.js (App Router) client: Listings, Add, Applications, Priorities,
      Profile.
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
- [x] Profile page — self-service for the profile itself: upload a résumé /
      cover letter / essay / master-doc and run the same ingestion `ajp ingest`
      does (dedup on, so re-uploading updates rather than duplicates), pull
      GitHub metadata, and add a new experience by interview. LinkedIn's zip is
      left to the CLI.
- [x] Master-doc entry list with edit / remove. Edits are applied to the
      document itself (keeping a `.bak`) and re-ingested, so they survive the
      next ingest; the UI points at handling notes for "true, but keep it off
      the résumé".
- [x] Live check: the full loop in the browser — add listings, generate, steer,
      edit, approve. It surfaced four things unit tests could not: run progress
      died on navigation, every document downloaded as `resume.pdf`, steering
      moved the ranking but not what trimming cut, and trimming deleted whole
      entries before touching a bullet. All fixed.
- [x] Live check: a full interview in the browser, including resuming a session
      left unfinished the day before — the transcript came back intact, the
      doubled-up user turn from the old wedging bug included.

## Later phases (expanded when reached)
- [ ] **Module 5** — Form auto-fill (Playwright) + essay answers + field review.
- [ ] **Module 6** — Gmail monitor (API + Pub/Sub) + response classification.
- [ ] **Module 7** — Tracker (Supabase source of truth + Notion-synced view).
- [ ] **Module 8** — Wire everything through the dashboard.
