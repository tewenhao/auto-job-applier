"""Render a MasterProfile as human-readable Markdown.

Pure function (no DB): used by ``profile show/export`` and as the round-trip
surface for hand editing. Kept deterministic and dependency-free so it's easy to
test and diff.
"""

from __future__ import annotations

from app.profile.models import Experience, MasterProfile


def _fmt_dates(exp: Experience) -> str:
    start = exp.start_date.isoformat() if exp.start_date else "?"
    if exp.is_current:
        return f"{start} – present"
    end = exp.end_date.isoformat() if exp.end_date else "?"
    return f"{start} – {end}"


def _experience_block(exp: Experience, *, include_handling_notes: bool) -> list[str]:
    header = " · ".join(p for p in (exp.title, exp.org) if p)
    lines = [f"### {header or '(untitled)'}", f"*{exp.kind}* — {_fmt_dates(exp)}"]
    if exp.summary:
        lines += ["", exp.summary]
    if exp.detail:
        lines += ["", exp.detail]
    if exp.highlights:
        lines += [""] + [f"- {h}" for h in exp.highlights]
    tags = list(exp.skills) + list(exp.tech)
    if tags:
        lines += ["", f"`{'` `'.join(tags)}`"]
    if include_handling_notes and exp.handling_notes:
        lines += ["", "> **handling notes (internal, never surfaced):**"]
        lines += [f"> - {n}" for n in exp.handling_notes]
    return lines


def profile_to_markdown(profile: MasterProfile, *, include_handling_notes: bool = False) -> str:
    """Render the whole profile to a Markdown document.

    ``handling_notes`` are internal constraints and are excluded by default (this
    render approximates what downstream generation sees). Pass
    ``include_handling_notes=True`` for the user's own review.
    """
    c = profile.candidate
    out: list[str] = [f"# {c.full_name or 'Candidate profile'}"]

    contact = [v for v in (c.email, c.phone, c.location) if v]
    if contact:
        out.append(" · ".join(contact))
    links = [v for v in (c.github_url, c.linkedin_url, c.portfolio_url) if v]
    if links:
        out.append(" · ".join(links))

    if profile.experiences:
        out += ["", "## Experience"]
        for exp in profile.experiences:
            out += [""] + _experience_block(exp, include_handling_notes=include_handling_notes)

    if profile.skills:
        out += ["", "## Skills"]
        by_category: dict[str, list[str]] = {}
        for s in profile.skills:
            by_category.setdefault(s.category or "Other", []).append(s.name)
        for category, names in sorted(by_category.items()):
            out.append(f"- **{category}**: {', '.join(sorted(names))}")

    if profile.github and profile.github.username:
        gh = profile.github
        out += ["", "## GitHub", f"[@{gh.username}](https://github.com/{gh.username})"]
        if gh.languages:
            langs = ", ".join(sorted(gh.languages, key=lambda k: -_as_num(gh.languages[k])))
            out.append(
                "Repo language bytes (NOISY — GitHub counts generated/vendored/dependency "
                f"code; NOT a verified skills list): {langs}"
            )
        out.append(f"{len(gh.repos)} repositories.")

    if profile.preferences:
        p = profile.preferences
        out += ["", "## Preferences"]
        for label, values in (
            ("Roles", p.role_types),
            ("Domains", p.domains),
            ("Industries", p.industries),
            ("Company sizes", p.company_sizes),
            ("Markets", p.location_markets),
            ("Avoid", p.avoid),
        ):
            if values:
                out.append(f"- **{label}**: {', '.join(values)}")

    if profile.voice:
        out += ["", "## Voice"]
        if profile.voice.tone:
            out.append(f"- **Tone**: {profile.voice.tone}")
        if profile.voice.summary:
            out.append(profile.voice.summary)

    if include_handling_notes and c.handling_notes:
        out += ["", "## Handling notes (global, internal — never surfaced)"]
        out += [f"- {n}" for n in c.handling_notes]

    return "\n".join(out) + "\n"


def _as_num(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
