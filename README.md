# auto-job-applier

My attempt at making an automatic job applier because year 2 summer plans are making me stressed out.

An AI-powered, human-in-the-loop pipeline that automates summer internship mass
applications: it builds a rich picture of the candidate, ingests job listings,
generates tailored applications in the candidate's authentic voice, auto-fills
ATS forms, and tracks responses — with the user signing off at every meaningful
gate.

## Design docs

- [`architecture.md`](architecture.md) — whole-system shape and principles
- [`modules.md`](modules.md) — per-module responsibilities and interfaces
- [`decisions.md`](decisions.md) — design decisions and rationale
- [`todolist.md`](todolist.md) — phased build checklist

## Status

**Modules 1–4 complete**: candidate profile, listing ingestion, application
generation, and the web dashboard. The whole loop — add listings, review the
scored queue, generate, inspect the model's ranking, steer and regenerate, edit
the résumé/cover letter by hand, approve — runs in the browser, with the `ajp`
CLI still exposing every step. **Module 5 — Form Auto-fill** is next.
See `todolist.md` for the detailed checklist.

## Layout

```
backend/    Python agent brain, `ajp` CLI, and the dashboard API — see backend/README.md
supabase/   versioned SQL migrations (the source-of-truth schema)
frontend/   Next.js dashboard (Module 4) — see frontend/README.md
```

## Quick start

```bash
cd backend
uv sync
cp .env.example .env   # fill in your keys
uv run ajp check
```

Then run the dashboard (two terminals):

```bash
cd backend  && uv run ajp serve   # API on :8000 (docs at /docs)
cd frontend && npm install && npm run dev   # UI on :3000
```

Optional, but recommended for ingestion — a headless browser lets the fetcher
read JavaScript-rendered postings (Workday, IBM, and similar):

```bash
cd backend
uv sync --extra browser
uv run playwright install chromium
```

Full setup and CLI reference: [`backend/README.md`](backend/README.md).
