# frontend/ — dashboard (Module 4)

Next.js (App Router, TypeScript) dashboard for reviewing generated
applications. It is a thin client over the `ajp serve` API
(`backend/app/api/`): every read and action hits that one backend, so the web
UI and the CLI behave identically.

## What it does

- **`/`** — **Listings**: the scored queue. Each role links out to the original
  posting, and a Generate button drafts an application for it.
- **`/add`** — **Add listings**: paste job URLs (one per line) or a job
  description. Board and search links expand into every matching role; results
  stream in per URL, and a skipped URL shows why.
- **`/priorities`** — the standing résumé guidance (what to prioritise on every
  résumé); the same value as `ajp preferences set-guidance`.
- **`/applications`** — every generated draft, with company / role / status.
- **`/applications/[id]`** — the review center for one application:
  - the tailorer's **ranking** of every experience/project it considered
    (score, rationale, included/dropped), so you can see _why_ it chose what
    it chose;
  - a **steer** box — free-text guidance that re-runs the pipeline and visibly
    changes the affected scores;
  - **approve / mark submitted**;
  - **hand-editing** — a structured editor for the résumé (education /
    experience / projects / skills, with reorderable bullets) and a text editor
    for the cover letter. Saving re-renders the PDF from exactly what you wrote,
    with no model call;
  - links to the compiled **résumé and cover-letter PDFs**, downloaded as
    `<candidate>-<company>-<kind>.pdf` so a folder of them stays legible.

Ingesting a batch and generating an application are long server-side jobs, so
their progress is held outside the page: switch tabs mid-run and come back, and
you are still watching the same run. A full browser reload does end a run — its
unfinished rows say so rather than pretending otherwise, and re-ingesting is
safe (listings de-duplicate by URL).

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
