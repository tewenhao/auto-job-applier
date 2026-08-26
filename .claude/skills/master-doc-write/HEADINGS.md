# Heading fixes — before / after

Worked examples of the parse-safety problems this skill catches. Each "before"
extracts badly (thin or colliding rows); each "after" gives the parser a
distinct name/role, an org/context, and readable dates.

## Missing org — the classic disappearing-entry cause

```markdown
❌  ### Digitalisation Lead. April 2025 - Present
```
No org → `org=null`. If another entry is also org-less, they collide.

```markdown
✅  ### Digitalisation Lead — Yong Huat Hardware Pte Ltd, Singapore. April 2025 - Present
```

## Two entries that collide on name + org

```markdown
❌  ### Intern — Home Team Academy, Singapore. May 2025 - Jul 2025
❌  ### Intern — Home Team Academy, Singapore. May 2025 - Jul 2025
```
Same `(kind, org, title)` → merge into one row.

```markdown
✅  ### Intern (xCloud, RPA) — Home Team Academy, Singapore. May 2025 - Jul 2025
✅  ### Intern (xDigital, LangChain) — Home Team Academy, Singapore. May 2025 - Jul 2025
```
Distinct roles → two rows. (Or fold genuinely-one role into a single entry.)

## Bare project name, no date

```markdown
❌  ### scoundrel
```

```markdown
✅  ### scoundrel — Java roguelike card game. July 2026
```

## Award with no event/body

```markdown
❌  ### 2nd place (Advanced)
```

```markdown
✅  ### 2nd place ("First Runner-Up"), TIL-AI (Advanced), 2025 DSTA BrainHack
```

## Unparseable dates

```markdown
❌  ### Research Intern — Acme Labs. Summer 2025
❌  ### Analyst — Acme. AY24/25
```
`normalize_date` can't read "Summer 2025" or "AY24/25".

```markdown
✅  ### Research Intern — Acme Labs. Jun 2025 - Aug 2025
✅  ### Analyst — Acme. Oct 2024 - Jun 2025
```

## Identity hidden in a PRIVATE note

```markdown
❌  ### The family-business project. April 2025 - Present
    **PRIVATE — note:** this is Yong Huat Hardware, my dad's company.
```
PRIVATE is stripped before the row is written, so the org never lands.

```markdown
✅  ### Digitalisation Lead — Yong Huat Hardware Pte Ltd, Singapore. April 2025 - Present
    **PRIVATE — note:** it's my dad's company — soften the family framing externally.
```
The org is in the heading (identity); the PRIVATE note carries only the guidance.

## Education — dates belong in FACTS, org in the heading

```markdown
✅  ### BA (Hons) Computer Science — University of Cambridge (Hughes Hall)
    **FACTS:**
    - Reading Computer Science, Oct 2025 - Jun 2028; funded by the SG Digital Scholarship.
```
