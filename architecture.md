# Architecture — Auto Job Applier

An AI-powered, human-in-the-loop pipeline that automates summer internship mass
applications: it builds a rich picture of the candidate, ingests job listings,
generates tailored applications in the candidate's authentic voice, auto-fills
ATS forms, and tracks responses — with the user signing off at every meaningful
gate.

This document describes the **whole system** so the shape is clear, then goes
deep on **Module 1 (Candidate Profile)**, which is what we build first. Modules
2–8 are sketched as forward context; each gets its own detailed pass when we
reach it.

---

## Core principles

1. **The profile is a superset, not the resume.** A resume is a lossy,
   space-constrained *projection* of what someone has done. If the resume were
   the source of truth, every generated application would inherit that same
   compression. Instead, all inputs (resume, LinkedIn, GitHub, essays, a
   freeform "master doc", and the onboarding interview) merge into one **Master
   Profile** that is the richest possible superset. Downstream generation
   selects and compresses *from* it, per job — never the other way around.

2. **Nothing acts without the human.** Every outward or hard-to-reverse step —
   surfacing a listing, choosing which role to apply for, sending a generated
   resume/cover letter, submitting a form — is gated behind explicit user
   sign-off via the dashboard. The system prepares; the user decides.

3. **Single-user today, shareable tomorrow.** Built for one user with no auth or
   multi-tenant isolation, but *nothing personal is hardcoded*. All secrets and
   identity come from env/config. Someone can clone the repo, drop in their own
   keys + Supabase project + their own resume, and run it. Multi-user later is a
   schema key + an auth layer away, not a rewrite.

4. **Supabase (Postgres) is the source of truth.** One database for profile,
   listings, applications, and tracker state. Typed models (Pydantic) mirror the
   schema and are the contract every module imports.

---

## System shape

```
                            ┌─────────────────────────────────────────┐
                            │            SUPABASE (Postgres)           │
                            │  source of truth: profile · listings ·   │
                            │        applications · tracker state      │
                            └───────────────▲───────────────▲─────────┘
                                            │               │
   INPUTS                                   │               │
   resume · linkedin · github ──┐   ┌───────┴────────┐  ┌───┴───────────┐
   essays · master doc ─────────┼──►│  1. CANDIDATE  │  │ 7. GMAIL       │
   onboarding interview ────────┘   │     PROFILE    │  │    MONITOR     │◄── Gmail API
                                    │ (master superset)│  │ (Pub/Sub push) │    + Pub/Sub
                                    └───────┬────────┘  └───┬───────────┘
                                            │ context base   │ status updates
                            ┌───────────────▼────────────────▼─────────┐
   JOB SOURCES              │                                          │
   UK Tracker (scrape) ──┐  │   2. LISTING      3. APPLICATION         │
   Greenhouse/Lever/ ────┼─►│      INGESTION ──►   GENERATION ──►  5. FORM
   Workday/LinkedIn      │  │   (scraped +        (tailored resume    AUTO-FILL
   manual paste link ────┘  │    manual, scored)   + voiced letter)   (Playwright)
                            │        │                                    │
                            └────────┼────────────────────────────────────┘
                                     │            ▲            ▲
                                     ▼            │            │
                            ┌──────────────────────────────────────────┐
                            │            8. DASHBOARD (web)             │
                            │  HITL review queues · "Apply" choices ·   │
                            │  form-fill approvals · flagged emails ·   │
                            │  6. TRACKER view (all applications)       │
                            └──────────────────────────────────────────┘
```

Control flows through the dashboard; data flows through Supabase.

---

## The application lifecycle (how a job becomes a submission)

1. **Listing enters** — either the user pastes a link (`manual`) or a scraper
   finds it (`scraped`). Both parse into the same listing model.
2. **Scored** against the profile's preferences; listings above threshold
   surface in the dashboard.
3. **User chooses the role.** Listings group by company. Where a company caps
   applications at one role, sibling roles are surfaced *together* and the user
   must pick exactly one before anything is generated. **The system never
   auto-picks a role at a one-shot company.** This "Apply" click is the HITL gate
   that promotes a listing into the pipeline.
4. **Generation fires** for that specific role — tailored resume + cover letter,
   grounded in the JD, freshly scraped company mission/values, and the master
   profile, written in the user's authentic voice.
5. **User reviews** the generated resume + letter (HITL checkpoint).
6. **Form auto-fill** stages the ATS submission via Playwright; **user reviews
   every filled field** (HITL checkpoint) before submit.
7. **Submitted** — logged to the tracker.
8. **Email monitor** watches for responses from that company's domain,
   classifies them, and updates the tracker + notifies the user.

---

## Module map

| # | Module | Responsibility | Status |
|---|--------|----------------|--------|
| 1 | **Candidate Profile** | Ingest all inputs (resume, master-doc, essays, LinkedIn export, GitHub) into the master-superset profile; voice model; preferences. | **Done** |
| 2 | Listing Ingestion | Manual paste + batch; structured ATS fast-paths and board enumeration (Greenhouse, Lever, Workday, Oracle HCM, Eightfold, iCIMS) with a headless-browser fallback; parse to listing model; score vs preferences. | **Done** |
| 3 | Application Generation | Tailored one-page resume (LaTeX → PDF) + humanified, voiced cover letter grounded in JD + company values; inspectable ranking + steering. | **Done** |
| 4 | **Dashboard** | Next.js UI over a FastAPI layer (`ajp serve`): add listings, browse the scored queue, generate, inspect the ranking, steer/regenerate, edit résumé + cover letter, approve. | **Done** |
| 5 | Form Auto-fill | Playwright ATS form-fill + essay answers; field-level review before submit. | **Next** |
| 6 | Gmail Monitor | Gmail API + Pub/Sub; classify responses; update tracker. | Later |
| 7 | Tracker | Supabase as source of truth + Notion-synced human-readable view. | Later |
| 8 | Wire-up | Dashboard as the central HITL + notifications + tracker surface. | Last |

---

## Tech stack

- **Backend** — Python (`uv`, Typer CLI, Pydantic models). Houses the agent
  brain: ingestion, parsing, interview, voice, generation, orchestration,
  scraping, Playwright, Gmail worker. It also serves the dashboard API
  (FastAPI, `ajp serve`), so the CLI and the web UI drive identical code paths.
- **Frontend** — Next.js (TypeScript, App Router). The dashboard (module 4): a
  thin client over the same API, holding no business logic of its own.
- **Database** — Supabase (Postgres) from day 1, via SQL migrations (not manual
  table creation) so a fresh clone can stand up the schema reproducibly.
- **LLM** — Anthropic Claude. **Opus** for the conversational interview (quality
  of follow-ups matters), **Haiku** for bulk structured extraction (resume→JSON,
  cheap and frequent). Model IDs live in config and are overridable per task.
- **External** — GitHub REST API (metadata only), Gmail API + Google Pub/Sub,
  Notion API, Playwright/Chromium.

---

## Repo layout (target shape; module 1 fills in `backend/`)

```
auto-job-applier/
├── backend/
│   ├── app/
│   │   ├── ingestion/     # resume, linkedin, github, essays, master-doc parsers
│   │   ├── profile/       # Pydantic models + Supabase data-access layer
│   │   ├── interview/     # gap-aware conversational engine
│   │   ├── voice/         # voice-profile distiller
│   │   ├── llm/           # Anthropic client wrapper + model config
│   │   ├── db/            # Supabase client
│   │   ├── config.py      # env-driven settings
│   │   ├── api/           # FastAPI dashboard API (`ajp serve`)
│   │   └── cli.py         # Typer entrypoints (ingest / voice / listings / generate / serve)
│   ├── tests/
│   ├── pyproject.toml
│   └── .env.example
├── supabase/
│   └── migrations/        # versioned SQL schema
├── frontend/              # Next.js dashboard (module 4)
├── architecture.md
├── modules.md
├── decisions.md
└── todolist.md
```

---

## What "done" looks like for Module 1

- Fresh clone + `.env` + `supabase db push` stands up the schema.
- `ingest` parses a real resume, LinkedIn export, GitHub profile, essays, and a
  freeform master doc into the experience bank, retaining every raw input.
- `interview` runs an Opus-driven, gap-aware conversation that elaborates thin
  experiences and captures preferences, working style, and things-not-on-CV,
  and is resumable.
- `voice build` produces a distilled voice profile plus retained raw samples.
- `profile show/export` renders the whole profile as readable Markdown; the user
  can correct it (edit + re-import, or direct Supabase) — the profile is fully
  editable.
- Typed Pydantic models expose the profile as the context base every later
  module imports.
