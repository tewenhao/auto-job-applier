---
name: master-doc-write
description: "Use this skill to format or lint the RAW MARKDOWN of a master-doc so the ingestion parser reads every entry correctly — every experience/project/award/education heading carries a distinct name/role, its org/context, and parseable dates, and the FACTS/VOICE/PRIVATE/LINKS labels are spelled exactly. Triggers: 'lint my master doc', 'check my master doc formatting', 'will my master doc ingest correctly', 'fix the master doc headings', 'my experiences disappeared after ingest', or before running `ajp ingest`. This is the line-level formatting/parse-safety companion to the `master-doc` skill (which decides CONTENT — FACTS vs VOICE vs PRIVATE). Do NOT use to author content, tailor a resume, or for job-listing work."
---

# Master-doc formatting & lint (parse-safety)

The `master-doc` skill decides **what** goes in the doc (FACTS / VOICE / PRIVATE /
LINKS). This skill guarantees the doc **parses**: that ingestion extracts every
entry with a distinct, populated identity, so nothing is dropped or silently
merged. It is a formatting pass and a linter, not a content pass.

## Why this matters (the failure it prevents)

Ingestion extracts each experience/project/award into a row keyed by
`(kind, org, title)`. Two problems follow from a sloppy heading:

- **A heading that omits the org or the role** → extraction yields `org=null`
  and/or `title=null`. Several such entries become **indistinguishable**.
- **Two entries that resolve to the same `(kind, org, title)`** are treated as
  the same experience.

On a `--fresh` ingest the pipeline now plain-inserts (so entries no longer
silently collapse), but a null/duplicate identity still produces **thin,
low-quality rows** — a role with no org, an award with no event. The fix is
always the same: give every heading a distinct name/role, its org/context, and
dates. Get the heading right and the entry extracts richly.

## What ingestion reads, and from where

| Field on the row | Comes from |
|---|---|
| `title` / role, `org`, `location`, dates | the entry's `###` **heading** |
| `detail` / `summary` | the `**FACTS:**` and `**VOICE:**` prose |
| `handling_notes` | the `**PRIVATE — …:**` bullets |
| (context only) | `**LINKS:**` |

So the **heading is load-bearing for identity**. If the org/role/dates aren't in
the heading (or clearly in the FACTS), the row comes out thin.

## Heading grammar (per section)

The parser is tolerant of punctuation (em-dash `—` or commas), but every heading
must make the **role/name**, the **org/context**, and the **dates** all
recoverable. Recommended shapes:

```markdown
## experience
### <Role> — <Org>, <Location>. <StartDate> - <EndDate | Present>
### <Role>, <Org>, <Location>. <StartDate> - <EndDate>        ← commas also fine

## education
### <Degree> — <Institution> (<College>)                      ← dates go in FACTS

## current/previous projects
### <Project name> — <one-line descriptor>. <Date>
### <Project name>. <Date>

## achievements/awards
### <Placement/Award> — <Event / Body>[, <Category>]
### <Placement>, <Event>, <Year>

## volunteering
### <Role/Programme> — <Org>[, <Location>]. <Date | Since Date>

## hobbies (that make me human)
### <Hobby> (<duration>)
```

The non-negotiables for every experience/project/award/volunteering entry:

- a **distinct name/role** (no two entries share the same one under the same org);
- the **org / event / body** it belongs to (never omit it — it's half the identity);
- **dates** the parser can read (see below). Education may carry dates in FACTS
  instead of the heading.

## Dates the parser accepts

`normalize_date` reads exactly these forms (case-sensitive month names):

- `2025-06-01`, `2025-06`, `2025`
- `Jun 2025`, `June 2025`

Ranges use ` - ` or ` – ` between two such dates (`Sep 2024 - Feb 2025`),
`Present` for ongoing (`April 2025 - Present`), or `Since <date>`. Avoid forms
the parser can't split into a start/end (e.g. "Summer 2025", "AY24/25") — spell
the month or year instead.

## Block labels — spell them exactly

The extractor keys on these literally; a renamed label breaks routing:

- `**FACTS:**`
- `**VOICE:**`  (and the verbatim marker `*VOICE — <label> (verbatim…):*` above a `>` blockquote)
- `**PRIVATE — <qualifier>:**`  (e.g. `do not surface externally`, `handle deliberately`, `note`)
- `**LINKS:**`

Bold, colon inside the `**…**`, exact words. `**FACTS**` (no colon) or
`**Facts:**` (wrong case) will not route reliably.

## Lint checklist (run before `ajp ingest`)

Read the whole doc and verify:

- [ ] Every `###` under experience/projects/awards/volunteering names its **org
      / event / body** — none is just a bare title.
- [ ] No two entries resolve to the same **name + org** (they'd merge). Give each
      a distinct role/name.
- [ ] Every such entry has **dates** in a parseable form (or, for education, in
      FACTS). No "Summer 2025"-style unparseable dates.
- [ ] Section headers are the expected `##` themes; every entry is a `###`.
- [ ] Block labels are spelled exactly: `**FACTS:**`, `**VOICE:**`,
      `**PRIVATE — …:**`, `**LINKS:**` (+ the `*VOICE — … (verbatim…):*` marker).
- [ ] No entry's identity (role/org) lives ONLY inside a PRIVATE note — PRIVATE
      is stripped from the row, so the heading/FACTS must carry it.

Report each problem with its line and a corrected heading; fix in place when
asked. See `HEADINGS.md` for worked before/after examples.

## After fixing, re-ingest

```bash
cd backend
uv run ajp ingest --fresh --resume <…> --master-doc <…> --linkedin <…> --github
uv run ajp consolidate
uv run ajp profile show          # confirm the expected count of experiences
```

Compare each document's printed `-> {'experiences': N}` against what
`profile show` lists: if they match, nothing was lost.
