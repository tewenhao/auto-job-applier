# Modules

This document decomposes the system. **Module 1 (Candidate Profile)** is broken
into its sub-components in full, since it's what we build first. Modules 2–8 are
stubs that capture responsibility, interface, and dependencies for forward
context — each gets a detailed pass when we reach it.

The unifying contract across everything is the set of **Pydantic models** in
`backend/app/profile/models.py`, which mirror the Supabase schema. Every module
that needs candidate context imports these; they are the "context base for all
downstream generation."

---

# Module 1 — Candidate Profile

**Goal:** merge every input into one rich Master Profile (a *superset* of what
the candidate has done), fully editable, serving as the context base for all
generation.

## Data model (Supabase / Postgres)

The heart is an **experience bank** where each thing the candidate has done
carries both a concise summary and long-form detail, plus links to evidence.

- **`candidate`** — one row (single-user). Identity, contact, links
  (github/linkedin/portfolio). Keyed so multi-user is a later addition, not a
  rewrite.
- **`source_documents`** — every raw input kept verbatim: resume, linkedin
  export, essays, cover letters, master doc, portfolio HTML. Fields: `type`,
  `filename`, `raw_text`, `storage_path`, `parsed_at`, `meta`. Retained so we
  can re-parse as models improve without re-collecting files.
- **`experiences`** — the core. `kind` (work / project / education / leadership /
  award / open_source / other), `org`, `title`, dates, **`summary`** (concise),
  **`detail`** (rich elaboration), `skills[]`, `tech[]`, `highlights[]`,
  `evidence` (points to a GitHub repo or a `source_documents` span), `source`
  (which input, or `interview`), `confidence`.
- **`skills`** — normalized: `name`, `category`, `proficiency`, `evidence[]`.
  Derived from experiences, editable.
- **`github_profile`** — cached API metadata: `repos`, `languages`, activity
  stats, `pulled_at`. (Metadata only — no cloning.)
- **`writing_samples`** — raw excerpts from essays/cover letters/interview, kept
  for few-shot grounding at generation time. `text`, `source`, `tags`.
- **`voice_profile`** — Claude-distilled style guide: tone, rhythm, vocabulary,
  quirks, do/don't. Points at the `writing_samples` it was built from.
- **`preferences`** — role types, domains (SWE/ML/quant/product/…), industries,
  company sizes, location markets (UK/SG/US/CN), and an **avoid list**. Shaped to
  be *scoreable* by Module 2. Optional weights per dimension.
- **`interview_sessions`** / **`interview_turns`** — transcript log so the
  interview is resumable and auditable; extracted facts flow into experiences /
  skills / preferences / voice.

## Sub-components

### 1a. Ingestion (`backend/app/ingestion/`)
- **Responsibility:** turn raw inputs into experience-bank rows.
- **Interface:**
  - In: file paths (resume PDF/DOCX, LinkedIn export ZIP, essays, master-doc
    Markdown/text), GitHub username + PAT.
  - Out: `source_documents`, `experiences`, `skills`, `writing_samples`,
    `github_profile` rows.
- **How:** each input has a parser. Documents → text → **Haiku** structured
  extraction into typed models. GitHub → REST API metadata. LinkedIn export →
  CSV parse + Haiku normalization. The master doc is parsed like any other
  source (freeform, no length limit).
- **Depends on:** `llm/`, `profile/` (DAL), `db/`.

### 1b. Profile store (`backend/app/profile/`)
- **Responsibility:** the typed models + the data-access layer over Supabase;
  merge/dedup logic when multiple inputs describe the same experience.
- **Interface:** Pydantic models (the shared contract) + repository methods
  (`upsert_experience`, `get_profile`, `export_markdown`, …).
- **Depends on:** `db/`.

### 1c. Interview engine (`backend/app/profile/interview.py`)
- **Responsibility:** capturing ONE new entry the profile doesn't have yet, by
  conversation rather than by form.
- **Interface:**
  - In: the already-ingested profile (as context, so it doesn't re-ask), plus
    the stored transcript.
  - Out: a drafted master-doc entry for review; `interview_sessions` /
    `interview_turns`; and, once the user accepts, a new block in the
    master-doc, re-ingested into experiences / skills / writing samples.
- **How:** **Opus** asks one short, specific question at a time, drawing out
  what a résumé needs and people leave out — their contribution as distinct
  from the team's, the stack, honest status, real figures — then drafts the
  entry in the doc's canonical FACTS / VOICE / PRIVATE format. Never writes
  silently: the draft is always reviewed first. Resumable across sessions and
  across surfaces (start in the dashboard, finish in `ajp interview`).
- **Scoped down from the original plan:** it captures one entry rather than
  sweeping the profile for gaps, and preference capture stayed structured
  (`ajp preferences`). Writes land in the master-doc, never straight into the
  database, because ingest rebuilds the database from the doc.
- **Depends on:** `llm/`, `profile/`.

### 1d. Voice model (`backend/app/voice/`)
- **Responsibility:** represent authentic voice for downstream generation.
- **Interface:** In: `writing_samples` + interview transcript. Out:
  `voice_profile` (distilled) — raw samples remain for few-shot use.
- **How:** Claude distills a style guide; both the guide and the raw excerpts are
  kept (the "must not read as LLM-generated" goal needs concrete examples, not
  just a description).
- **Depends on:** `llm/`, `profile/`.

### 1e. CLI (`backend/app/cli.py`)
- **Responsibility:** the module's interface until the dashboard (Module 4).
- **Commands:**
  - `ingest <files…>` — run 1a across inputs.
  - `interview` — run 1c (resumable).
  - `voice build` — run 1d.
  - `profile show / export` — render the whole profile as readable Markdown.
  - `profile edit` — correct fields (edit exported Markdown + re-import, or edit
    Supabase directly). Satisfies "fully editable and correctable."
- **Depends on:** all of the above.

### Module 1 dependencies
- Anthropic API key, Supabase project + keys, GitHub PAT — all via `.env`.
- No dependency on any other module. Everything downstream depends on it.

---

# Modules 2–8 (stubs — forward context)

## Module 2 — Listing Ingestion
- **Responsibility:** get job listings into the system and score them.
- **Interface:** In: a pasted link, a batch of links (the Trackr link-grabber),
  or pasted JD text. A link may name one posting *or* a board/filtered search,
  which is enumerated into every matching role. Out: `listings` rows with
  `source` ∈ {`manual`, `scraped`}, parsed JD, company, role, market, and a
  preference-match score.
- **Key concepts:** manual paste is a first-class path and the easiest to ship
  first. Fetching is layered: a structured ATS API where one exists
  (Greenhouse, Lever, Workday, Oracle HCM, Eightfold, iCIMS), then plain HTTP,
  then an optional headless browser for JS-rendered or bot-gated pages. A URL
  whose shape names a single posting is never rejected by the careers-index
  heuristic. Listings group by company; a **one-role-per-company** constraint means
  sibling roles surface together and the user picks exactly one — the system
  never auto-picks at a one-shot company.
- **Depends on:** Module 1 (`preferences` for scoring).

## Module 3 — Application Generation
- **Responsibility:** tailored resume + humanified, voiced cover letter.
- **Interface:** In: chosen `listing` + JD + freshly scraped company
  mission/values + master profile + `voice_profile`. Out: resume + cover letter
  drafts for HITL review.
- **Depends on:** Modules 1, 2.

## Module 4 — Dashboard
- **Responsibility:** the browser surface for the whole loop — add listings,
  review the scored queue, generate, inspect the ranking, steer and regenerate,
  hand-edit the résumé and cover letter, approve. Also the profile itself
  (ingest a document, interview in an entry, edit the master-doc) and the
  preferences that decide which listings reach the queue, with re-scoring when
  they change.
- **Interface:** a FastAPI layer (`ajp serve`) over the existing repositories
  and generation pipeline, and a Next.js client over that API. The API holds no
  logic the CLI doesn't, so the two cannot drift.
- **Key concepts:** every mutation is still HITL — the dashboard prepares and
  the user decides. Hand-edits re-render deterministically (no model call),
  which keeps "the model drafts" and "I am the final author" separate. A
  decision the user has made by hand is never overruled by a rule: re-scoring
  flags a chosen listing its filters would now exclude, rather than dropping it.
  Failures are reported as a cause plus what to try, never a bare 500 — and so
  are the quiet ones, like a résumé that came out two pages.
- **Depends on:** Modules 1–3, reads Supabase.

## Module 5 — Form Auto-fill
- **Responsibility:** Playwright ATS form-fill + essay answers grounded in the
  profile; field-level review before submit.
- **Depends on:** Modules 1, 3.

## Module 6 — Gmail Monitor
- **Responsibility:** Gmail API + Pub/Sub; classify company responses (OA /
  interview / rejection / info request / noise); update tracker.
- **Depends on:** Module 7 (tracker cross-reference).

## Module 7 — Tracker
- **Responsibility:** Supabase as source of truth + Notion-synced human view;
  logs company, role, JD, date, ATS, status, email responses.
- **Depends on:** Modules 2, 3, 5.

## Module 8 — Wire-up
- **Responsibility:** dashboard as the central HITL + notifications + tracker
  surface tying everything together.
- **Depends on:** all.
