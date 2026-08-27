"""LLM parsing of a fetched job posting into structured listing fields."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.config import Task
from app.listings.fetch import FetchedJob
from app.llm import LLMClient


class ParsedListing(BaseModel):
    company: str | None = None
    role_title: str | None = None
    domain: str | None = None  # swe | ml | quant | product | data | hardware | other
    market: str | None = None  # uk | sg | us | cn | other
    location: str | None = None
    jd_summary: str | None = None
    requirements: list[str] = Field(default_factory=list)
    is_job_posting: bool = True  # False if this is a careers index / landing page


_SYSTEM = (
    "Extract structured fields from a job posting. Classify 'domain' into one of: "
    "swe, ml, quant, product, data, hardware, design, other. Classify 'market' as "
    "the country market of the role's location: uk, sg (Singapore), us, cn (China), "
    "or other. Write a tight 'jd_summary' (2-3 sentences) and list the key "
    "'requirements' (must-have skills/qualifications). Use the provided company/"
    "title/location hints when present.\n"
    "ROLE TITLE: always give a specific 'role_title' for a single posting. If the "
    "body doesn't state one but a title hint is given, use the hint (cleaned). Only "
    "leave role_title null if this genuinely isn't one specific role.\n"
    "PAGE TYPE: set 'is_job_posting' to false if the text is a careers landing page "
    "or a search-results / index page listing MANY different roles (e.g. one role "
    "spanning many cities, or a list of openings) rather than one specific posting. "
    "In that case do not invent a single title. Otherwise leave it true."
)


def parse_listing(llm: LLMClient, fetched: FetchedJob) -> ParsedListing:
    hints = []
    if fetched.company:
        hints.append(f"company hint: {fetched.company}")
    if fetched.role_title:
        hints.append(f"title hint: {fetched.role_title}")
    if fetched.location:
        hints.append(f"location hint: {fetched.location}")
    hint_text = ("\n".join(hints) + "\n\n") if hints else ""
    user = f"{hint_text}--- JOB POSTING ---\n{fetched.jd_text or ''}"
    return llm.parse(
        task=Task.PARSE,
        system=_SYSTEM,
        messages=[{"role": "user", "content": user}],
        output_format=ParsedListing,
    )
