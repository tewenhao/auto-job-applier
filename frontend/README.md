# frontend/ — dashboard (Module 4)

Next.js (App Router, TypeScript) dashboard for reviewing generated
applications. It is a thin client over the `ajp serve` API
(`backend/app/api/`): every read and action hits that one backend, so the web
UI and the CLI behave identically.

## What it does

- **`/`** — every generated application, with company / role / status.
- **`/applications/[id]`** — the review center for one application:
  - the tailorer's **ranking** of every experience/project it considered
    (score, rationale, included/dropped), so you can see _why_ it chose what
    it chose;
  - a **steer** box — free-text guidance that re-runs the pipeline and visibly
    changes the affected scores;
  - **approve / mark submitted**;
  - a link to the **compiled PDF** and the tailored cover letter.

## Running it

1. Start the API from `backend/`:

   ```bash
   uv run ajp serve            # http://127.0.0.1:8000  (docs at /docs)
   ```

2. Start the dashboard from `frontend/`:

   ```bash
   npm install
   npm run dev                 # http://localhost:3000
   ```

The API base URL defaults to `http://127.0.0.1:8000`; override it by copying
`.env.local.example` to `.env.local` and editing `NEXT_PUBLIC_API_BASE`.
