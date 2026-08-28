"""Failures, told to the person who has to fix them.

The dashboard is where most failures will be met, and a red `500: Internal
Server Error` tells you nothing you can act on. So every failure that reaches
the UI arrives as a :class:`Problem`: what went wrong in plain words, and an
ordered list of things to try — Nielsen's ninth heuristic, which asks that
errors be expressed in plain language, say precisely what happened, and suggest
a way out.

The fixes are specific to *this* project on purpose. "Check your credentials" is
not help; "the settings are cached, so restart `ajp serve` after editing .env"
is, because that is the thing that actually catches people out here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Editing .env has no effect until the process restarts (settings are cached
# with lru_cache), which is not obvious and wastes a lot of time.
_RESTART = "Restart `ajp serve` — it reads .env once at startup, so edits need a restart."
_LOGS = "Check the terminal running `ajp serve` for the full traceback."


@dataclass(frozen=True)
class Problem:
    """One failure, in a form the UI can render and a person can act on."""

    code: str  # stable identifier, for the UI to branch on if it wants to
    title: str  # short, plain language: what went wrong
    message: str  # the detail, still in plain language
    fixes: list[str] = field(default_factory=list)  # ordered things to try
    status: int = 500

    def as_detail(self) -> dict[str, Any]:
        """The body the API returns under ``detail``."""
        return {
            "code": self.code,
            "title": self.title,
            "message": self.message,
            "fixes": list(self.fixes),
        }


def as_http(problem: Problem) -> Any:
    """The HTTPException to raise for ``problem`` (kept out of the type checker's
    way — importing FastAPI here would make this module about the framework)."""
    from fastapi import HTTPException

    return HTTPException(status_code=problem.status, detail=problem.as_detail())


def _text(exc: BaseException) -> str:
    return str(exc).lower()


def diagnose(exc: BaseException) -> Problem:  # noqa: PLR0911 - a lookup table, one branch per cause
    """Turn an exception into something the user can act on.

    Unrecognised failures still get a Problem — a generic one that at least says
    where to look — rather than falling through to a bare 500.
    """
    import anthropic

    text = _text(exc)

    # --- the model API ---
    if isinstance(exc, anthropic.AuthenticationError) or "invalid x-api-key" in text:
        return Problem(
            code="llm_auth",
            title="Anthropic rejected the API key",
            message="The key in your .env was refused, so nothing could be generated.",
            fixes=[
                "Check ANTHROPIC_API_KEY in backend/.env — a stray quote or space is enough.",
                "Run `uv run ajp check` in backend/ to validate the configuration.",
                _RESTART,
            ],
            status=502,
        )
    if "credit balance is too low" in text:
        return Problem(
            code="llm_no_credit",
            title="The Anthropic account is out of credit",
            message=(
                "The API refused the request because the account has no credit left. "
                "Nothing was lost — whatever you had is still saved."
            ),
            fixes=[
                "Add credit at console.anthropic.com/settings/billing.",
                "Then press the button again — this is safe to retry.",
                "If you have more than one key, check that .env has the funded one.",
            ],
            status=402,
        )
    if isinstance(exc, anthropic.RateLimitError):
        return Problem(
            code="llm_rate_limit",
            title="Anthropic is rate-limiting the account",
            message="Too many requests went out too quickly, so this one was refused.",
            fixes=[
                "Wait a minute and try again.",
                "Generate one application at a time rather than several at once.",
            ],
            status=429,
        )
    if isinstance(exc, anthropic.APIConnectionError | anthropic.APITimeoutError):
        return Problem(
            code="llm_unreachable",
            title="Couldn't reach the Anthropic API",
            message="The request never got a reply — usually the network, not your setup.",
            fixes=[
                "Check your internet connection, and any VPN or proxy.",
                "Try again — generation is safe to retry.",
            ],
            status=504,
        )
    if isinstance(exc, anthropic.APIStatusError) and exc.status_code >= 500:
        return Problem(
            code="llm_server_error",
            title="The Anthropic API is having trouble",
            message="The API returned a server error. This is on their side, not yours.",
            fixes=["Wait a moment and try again.", "Check status.anthropic.com."],
            status=502,
        )
    if "cut off before it was valid json" in text:
        # Raised by LLMClient.parse when the model hits max_tokens mid-output.
        return Problem(
            code="llm_truncated",
            title="The model's answer was cut off",
            message=(
                "The response hit its length ceiling before it finished, so it "
                "couldn't be read. Usually a one-off."
            ),
            fixes=[
                "Try again — it usually succeeds on the second attempt.",
                "If it keeps happening, use the steer box to ask for fewer entries.",
            ],
            status=502,
        )

    # --- the candidate's own files ---
    if isinstance(exc, FileNotFoundError) or "no master document at" in text:
        return Problem(
            code="master_doc_missing",
            title="The master document couldn't be found",
            message=str(exc),
            fixes=[
                "Set MASTER_DOC_PATH in backend/.env to the file's path.",
                "A relative path is resolved from the repository root, not from backend/.",
                _RESTART,
            ],
            status=400,
        )

    # --- the database ---
    if any(k in text for k in ("supabase", "postgrest", "getaddrinfo", "connection refused")):
        return Problem(
            code="database_unreachable",
            title="Couldn't reach the profile database",
            message="Supabase didn't answer, so nothing could be read or saved.",
            fixes=[
                "Check SUPABASE_URL and SUPABASE_KEY in backend/.env.",
                "A free Supabase project pauses when idle — open the dashboard to wake it.",
                "Run `uv run ajp check` in backend/ to test the connection.",
                _RESTART,
            ],
            status=502,
        )

    # --- anything else ---
    return Problem(
        code="unexpected",
        title="Something went wrong",
        message=f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__,
        fixes=[
            "Try again — some failures are transient.",
            _LOGS,
            "If it repeats, the traceback in that terminal is what to report.",
        ],
        status=500,
    )


def page_fit_notice(
    *, pages: int | None, stop_reason: str, max_pages: int, trims: int
) -> Problem | None:
    """A résumé that came out over the page limit, if it did.

    The CLI has always said this; the dashboard said nothing at all, so a
    two-page résumé looked like a success. The two ways of failing to fit call
    for opposite actions, so they are reported separately.
    """
    if pages is None:
        return Problem(
            code="pdf_not_compiled",
            title="The PDF couldn't be built",
            message=(
                "The résumé's .tex was written, but no PDF was produced, so its "
                "length is unverified — it may not be one page."
            ),
            fixes=[
                "Install a LaTeX toolchain (MacTeX on macOS, TeX Live elsewhere), "
                "then regenerate.",
                "Download the .tex and compile it anywhere, including Overleaf.",
                _LOGS,
            ],
        )
    if stop_reason == "content_floor":
        return Problem(
            code="over_page_limit_at_floor",
            title=f"This résumé is {pages} pages, not {max_pages}",
            message=(
                "Every entry has been cut back as far as it can go and it still "
                "doesn't fit. Something has to come out."
            ),
            fixes=[
                "Use the steer box to drop an experience or project explicitly.",
                "Shorten the longest bullets in the editor below.",
                "Or accept the length — the ranking shows what the model kept and why.",
            ],
        )
    if stop_reason == "iterations":
        return Problem(
            code="over_page_limit_gave_up",
            title=f"This résumé is {pages} pages, not {max_pages}",
            message=(
                f"Trimming stopped after {trims} rounds with content still left to "
                "cut — it ran out of rounds, not out of things to trim."
            ),
            fixes=[
                "Press Regenerate: trimming picks up from here and usually finishes.",
                "Or cut an entry yourself with the steer box, which gets there faster.",
            ],
        )
    return None


def generic(status: int, message: str) -> Problem:
    """Wrap a plain message (an ordinary HTTPException) as a Problem.

    Endpoints that raise a one-line 400/404 still get the same shape, so the UI
    has exactly one thing to render.
    """
    if status == 404:
        return Problem(
            code="not_found",
            title="Not found",
            message=message,
            fixes=[
                "Go back to the list and open the item again — it may have been "
                "regenerated or removed.",
                "Reload the page.",
            ],
            status=status,
        )
    if status in (401, 403):
        return Problem(
            code="forbidden",
            title="Not allowed",
            message=message,
            fixes=["Check the credentials in backend/.env.", _RESTART],
            status=status,
        )
    return Problem(
        code="bad_request",
        title="That request couldn't be completed",
        message=message,
        fixes=["Read the message above — it says what needs to change.", "Then try again."],
        status=status,
    )
