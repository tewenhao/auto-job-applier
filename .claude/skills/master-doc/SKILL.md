---
name: master-doc
description: "Use this skill to build or refine a candidate's personal 'master document' (master-doc) into the exact structured format that auto-job-applier's ingestion and voice pipeline consumes. Triggers: 'master doc', 'master document', 'refine my master doc', 'format this into the master doc format', 'start a new master doc', or handing over a raw brain-dump / resume / bio to be turned into the profile source-of-truth. The master-doc is the superset input behind every generated resume and cover letter, so its FACTS / VOICE / PRIVATE / LINKS structure is load-bearing. Do NOT use for tailoring a single resume/cover letter or for job-listing work."
---

# Master-doc authoring & refinement

The master-doc is the **superset source-of-truth** for one candidate: everything
they've done, in more depth than any resume. `auto-job-applier` ingests it and
its structure is **load-bearing** — three specific block types are parsed
literally by code:

| Block | Consumed by | Becomes | Rule |
|---|---|---|---|
| `**FACTS:**` | ingestion (`extract_profile`) | experience `detail` + `summary` + skills | Ground truth. Never invented. |
| `**VOICE:**` and `*VOICE — … (verbatim):*` + `>` quote | voice harvest (`harvest_master_doc_voice`) | `writing_samples` (voice model) | **The candidate's own words, verbatim.** |
| `**PRIVATE — …:**` | ingestion → `handling_notes` | constraints on later writing (never output) | Guidance, never facts. |
| `**LINKS:**` | reference only (excluded from voice) | contextual URLs | Primary sources. |

The extractor keys on literal cues inside PRIVATE blocks — `PRIVATE`,
`do not surface`, `don't claim`, `don't inflate`, `frame carefully`,
audience-specific framing — to route them into `handling_notes`. The harvester
keys on the `VOICE` label and `VOICE —` verbatim marker. **If you rename these
labels, the pipeline stops working.** Keep them exactly.

## The prime directive

You are an **editor and structurer, not an author.** The master-doc's value is
that every fact is true and every VOICE passage is the candidate's real voice. So:

- **Never invent a fact, metric, date, title, or outcome.** If the candidate
  didn't state it, it isn't there. Leave a gap and flag it (see *Gaps* below).
- **VOICE is verbatim or the candidate's own fresh words — never yours.** Do not
  write reflective prose *for* them. Lift their own sentences from the raw input,
  or ask them to say it and transcribe. If you must lightly tidy, keep their
  diction, rhythm, and honesty; never smooth it into generic application-speak.
- **Every claim must be sourceable.** A metric with no source is a liability, not
  an asset — move it to PRIVATE with a note to verify, or cut it.
- **Guidance is not fact.** Anything about *how to use or not use* material
  ("don't lead with X", "soften Y", "audience-dependent") goes in PRIVATE, never
  in FACTS or VOICE.

## Document structure

```
# master document on <name>

## <section>            ← top-level theme
### <Entry>             ← one role / project / award / etc.
*<optional italic context line>*
**FACTS:**
- …
**VOICE:**
- …
**PRIVATE — <qualifier>:**
- …
**LINKS:**
- …
```

**Sections** are broad life/career themes, ordered most-to-least
career-relevant. A typical set (adapt to the person):
`motivations/goals` · `experience` · `education` · `current/previous projects` ·
`want to dos` · `achievements/awards` · `volunteering` · `hobbies (that make me human)`.

**Entry headings** for dated roles use:
`Role — Org, Location. StartDate - EndDate` (e.g. `April 2025 - Present`).
Projects/awards use a descriptive name + date. Put a one-line *italic* context
note directly under the heading when it frames the whole entry (e.g.
`*Family business (my dad's).*` or `*Part of National Service.*`).

Not every entry needs all four blocks — a hobby may be just FACTS + VOICE; an
award may add PRIVATE + LINKS. Include a block only when it has real content.

## What goes in each block

**FACTS** — the verifiable substance. What was built, the role, the stack, the
scale, the outcome, the team split, the honest status (`in development`,
`demoed, adoption unclear`, `pre-trial — no metrics yet`). Use bold to mark the
load-bearing terms and numbers. State contribution precisely ("first author;
framework + write-up mine, eval code co-authors'"). Prefer honest scale anchors
("2-person team, ~15 enquiries/day") over invented efficiency metrics.

**VOICE** — the candidate's authentic reflection *in their own voice*: why it
mattered, what it taught them, the recurring threads they name themselves, the
honest caveats. Two forms:
- Reflective bullets in their voice under a `**VOICE:**` label.
- A verbatim reusable passage (a past essay, a paragraph they're proud of),
  introduced with an italic marker and quoted:
  `*VOICE — <label> (verbatim, from …; my own writing …):*` then a `>` blockquote.
  Copy it **exactly** — this feeds the voice model directly.

**PRIVATE** — handling notes for downstream writing. Common qualifiers seen in
practice: `do not surface externally`, `handle deliberately`,
`handle with care`, `framing nuance`, `note`, `gap to fill`. Each bullet is a
constraint: what not to claim, what to soften, how to frame per audience, which
number is unverified, which sensitive topic to center on growth rather than
detail. These become `handling_notes` and must never appear in a resume/letter.

**LINKS** — repos, papers (DOI), marketplace listings, primary sources for
awards (a minister's speech, an official results page). Note ownership when a
repo is a teammate's ("team repo; I was frontend dev"). Context-only links
(a standard, a third-party system) can be parenthetical.

## Workflow

1. **Read the raw input fully** — brain-dump, old resume, LinkedIn text, prior
   master-doc, or a mix. Understand the whole person before restructuring.
2. **Cluster into sections and entries.** Group everything into the section
   themes; split into one `###` entry per role/project/award/etc.
3. **For each entry, sort every sentence into a block:**
   - Verifiable substance → **FACTS**
   - Their reflection / why-it-mattered / a verbatim proud passage → **VOICE**
   - Any "how to use / not use / frame / don't claim" → **PRIVATE**
   - URLs → **LINKS**
4. **Preserve voice.** Pull VOICE passages from the candidate's own words in the
   raw input. Where a strong reflection is missing, *ask* the candidate a
   question and transcribe their answer — do not fabricate it.
5. **Interrogate every number and claim.** For each metric/title/outcome ask
   "is this sourced?" Unsourced → PRIVATE (verify) or cut. Overstated
   deployment/adoption → correct to the honest status and add a PRIVATE note.
6. **Surface tensions honestly.** Where the doc contains an apparent
   contradiction (e.g. "can't see myself in quant" *and* a quant programme),
   don't hide it — add a PRIVATE note framing it as a per-audience choice.
7. **Flag gaps, don't fill them** (see below).
8. **Validate** against the checklist, then hand back.

## Gaps

When something important is thin or missing, **do not invent it.** Either:
- Ask the candidate a specific question ("What was the team size?" "What's the
  honest status — shipped, demoed, or in development?"), or
- Leave an explicit `**PRIVATE — gap to fill:**` bullet naming what's needed.

A visible gap is correct; a plausible-sounding fabrication is a defect that will
propagate into every generated application.

## Validation checklist

Before handing back, confirm:

- [ ] Every `###` entry's substance is under `**FACTS:**`.
- [ ] Labels are exact: `**FACTS:**`, `**VOICE:**`, `**PRIVATE — …:**`,
      `**LINKS:**` (and `*VOICE — … (verbatim…):*` for quoted passages). No
      renamed or merged labels.
- [ ] No invented facts, metrics, dates, titles, or outcomes anywhere.
- [ ] Every VOICE passage is the candidate's own words (verbatim quote or their
      transcribed reflection), not editor-written prose.
- [ ] Every "how to use / don't say / frame carefully" line is in PRIVATE, not
      FACTS or VOICE.
- [ ] Every quantified claim is sourced, or flagged in PRIVATE as unverified.
- [ ] Deployment/adoption status is honest (no implied production/adoption).
- [ ] Sensitive material (health, conflict, identifiable third parties) is
      handled per a PRIVATE note centred on growth, not credentials.
- [ ] Gaps are flagged, not filled.

## References

- `TEMPLATE.md` — a copy-paste skeleton with all block types annotated.
- `EXAMPLE.md` — one fully worked (synthetic) entry showing FACTS / VOICE /
  PRIVATE / LINKS in context.
- The `master-doc-write` skill — the line-level formatting/parse-safety pass.
  This skill decides *content*; run `master-doc-write` before `ajp ingest` to
  verify every heading parses (distinct name/role, org, readable dates) so no
  entry is dropped or extracted thin.
