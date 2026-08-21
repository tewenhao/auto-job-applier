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

Building **Module 1 — Candidate Profile** first. See `todolist.md` for progress.

## Layout

```
backend/    Python agent brain + CLI (Module 1 lives here)  — see backend/README.md
supabase/   versioned SQL migrations (the source-of-truth schema)
frontend/   Next.js dashboard (reserved for Module 4)
```

## Quick start

```bash
cd backend
uv sync
cp .env.example .env   # fill in your keys
uv run ajp check
```

Full setup and CLI reference: [`backend/README.md`](backend/README.md).
