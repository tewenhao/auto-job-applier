# Design Decisions

A running log of significant decisions and their rationale. Newest at the bottom.

## Tech stack: Python backend + TypeScript frontend
- Decision: Python (`uv`, Typer, Pydantic) for the agent/parsing/orchestration
  brain; Next.js (TypeScript) for the dashboard (arrives Module 4). Monorepo.
- Alternatives: all-TypeScript monorepo; Python-only with a lightweight
  dashboard (Streamlit/HTMX).
- Rationale: user is most comfortable with Python for the LLM/data/scraping work,
  which is the bulk of the system. A dedicated TS frontend keeps the eventual
  dashboard polished. Cost is two languages, but they meet only at the Supabase
  boundary, so the seam is clean.
- Date: 2026-08-21

## Single-user, but shareable repo
- Decision: build for one user — no auth, no multi-tenant isolation — but keep
  all identity/secrets in env/config, nothing personal hardcoded, so others can
  clone and run their own instance.
- Alternatives: full multi-user product (auth, RLS, per-user OAuth storage) now;
  or a strictly personal tool with hardcoded values.
- Rationale: matches the actual goal (the user's own summer hunt) while keeping
  the door open to sharing. Multi-user later becomes a schema key + auth layer,
  not a rewrite. Implication: each user needs their own Supabase project + keys,
  so reproducible SQL migrations and a `.env.example` are part of Module 1's
  definition of done.
- Date: 2026-08-21

## CLI-first onboarding
- Decision: the onboarding interview and profile management run as a Python
  Typer CLI for now; migrate into the dashboard chat at Module 4.
- Alternatives: build a minimal standalone web chat immediately; run onboarding
  as an ad-hoc conversation inside Claude Code.
- Rationale: the dashboard is Module 4 but the interview is Module 1 — the CLI
  unblocks module 1 with zero UI work and the interview logic ports directly into
  the dashboard later. The ad-hoc option isn't a repeatable product feature.
- Date: 2026-08-21

## Supabase (Postgres) from day 1
- Decision: the profile lives in Supabase from the first module.
- Alternatives: local-first (SQLite/JSON) for Module 1, migrate later.
- Rationale: Supabase is already the chosen source of truth for the tracker;
  starting there avoids a migration and gives one DB for everything. Cost is
  cloud setup up front, accepted.
- Date: 2026-08-21

## Model split: Opus interview / Haiku parse
- Decision: Claude Opus for the conversational interview, Claude Haiku for bulk
  structured extraction. Model IDs in config, overridable per task.
- Alternatives: Sonnet for everything; fully per-task config with no defaults.
- Rationale: interview quality (good follow-ups, feels human) justifies Opus and
  runs rarely; extraction is frequent and cheap, so Haiku. Config-driven IDs keep
  it swappable without code changes.
- Date: 2026-08-21

## Profile is a superset, not the resume
- Decision: treat all inputs (resume, LinkedIn, GitHub, essays, freeform master
  doc, interview) as *sources* that merge into one rich Master Profile; generate
  by compressing *down* from it per job.
- Alternatives: treat the resume as source of truth and augment it.
- Rationale: a resume is deliberately compressed and can't fit everything; using
  it as the base propagates that loss into every generated application. The
  user explicitly wants a richer "master base" than their concise resume. The
  interview's job becomes *gap-filling* against what's already parsed, which is
  also less tedious.
- Date: 2026-08-21

## Retain all raw inputs verbatim
- Decision: store every raw input in `source_documents` (raw text + file),
  keyed to what was extracted from it.
- Alternatives: parse and discard raw inputs.
- Rationale: lets us re-parse as models improve, and trace any profile fact back
  to its evidence, without re-collecting files. Small storage cost.
- Date: 2026-08-21

## Voice = distilled style guide + retained raw samples
- Decision: keep both a Claude-distilled `voice_profile` and the raw
  `writing_samples`.
- Alternatives: distilled guide only; raw samples only.
- Rationale: the "must not read as LLM-generated" goal needs concrete examples
  for few-shot imitation, while the distilled guide gives a structured, editable
  handle on voice. Both together are strongest.
- Date: 2026-08-21

## GitHub: API metadata only (no cloning)
- Decision: pull repos, languages, topics, READMEs, and commit frequency via the
  GitHub REST API; no repo cloning or diff analysis.
- Alternatives: also shallow-clone top repos to analyze real code/commits.
- Rationale: metadata captures ~90% of the signal at a fraction of the cost and
  time. Deeper clone-based analysis can be added later if generation quality
  needs it.
- Date: 2026-08-21

## Job sourcing: manual paste + scraped, user picks the role
- Decision: listings carry `source` ∈ {`manual`, `scraped`}. Manual paste is a
  first-class path (and ships first in Module 2). Scraped listings surface in the
  dashboard for the user to choose. A **one-role-per-company** constraint groups
  sibling roles and forces the user to pick exactly one; the system never
  auto-picks a role at a one-shot company. The "Apply" click is the HITL gate
  into generation.
- Alternatives: fully automatic surfacing + auto-selection of the best-scored
  role per company.
- Rationale: the user wants to choose which role to spend a company's single
  application slot on. Captured now (though it lives in Module 2 + dashboard) so
  the data model reserves it cleanly rather than retrofitting.
- Date: 2026-08-21

## Prompt caching: cache the profile, and put it first
- Decision: mark the system prompt and the candidate-profile block as cache
  breakpoints on the three Opus routes (résumé tailoring, cover letter,
  interview), and reorder the generation prompts so the stable context comes
  *before* the per-listing content. The Haiku routes (listing parse, listing
  score, document extraction) are deliberately left uncached.
- Alternatives: cache nothing (status quo); cache everything everywhere; a
  1-hour TTL instead of the default 5 minutes.
- Rationale: caching is a *prefix* match, so order is the whole game. The
  profile renders to ~17.5k tokens and was being re-sent at full price on every
  generation — twice per application, again on every steer — and it sat *after*
  the company and role in the prompt, so no two listings shared a prefix. Moving
  it ahead of the volatile half makes the same bytes cacheable across every
  listing; a read costs ~10% of a full-price input token. The Haiku routes can't
  benefit at any price: their system prompts are 98-253 tokens against Haiku
  4.5's 4096-token minimum cacheable prefix, so a marker there would be silently
  ignored. The 5-minute TTL is right because the calls that share a prefix run
  back to back (résumé then cover letter, then the next listing) and every read
  refreshes the timer; the 1-hour TTL costs 2x to write and would only pay off
  across longer gaps.
- Consequence: `list_experiences` / `list_skills` / `list_writing_samples` now
  order by a *total* key. Rows tied on `start_date` used to come back in
  arbitrary order, which changes the rendered bytes and would have silently cost
  the cache hit it was all built for.
- Date: 2026-08-28
