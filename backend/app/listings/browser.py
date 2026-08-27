"""Headless-browser fallback for JS-rendered / bot-gated job pages.

Used only when the plain HTTP fetch comes up empty (a JavaScript shell like
Workday/IBM, or a 403 from an anti-bot). Renders the page with Playwright's
Chromium and returns the resulting HTML, which the normal fetch path then turns
into text + metadata.

Optional: Playwright is an extra (``uv sync --extra browser`` +
``uv run playwright install chromium``). If it isn't installed, ``render_page``
returns ``None`` and the caller falls back to its existing behaviour, so nothing
breaks without the extra.
"""

from __future__ import annotations

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def render_page(
    url: str, *, executable_path: str = "", timeout_ms: int = 30000
) -> str | None:
    """Render ``url`` in headless Chromium and return the page HTML, or ``None``
    if Playwright isn't installed or rendering fails.

    Waits for the DOM, then briefly for network to settle so SPA content that
    loads via XHR is present before we read it.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    launch: dict[str, object] = {"headless": True}
    if executable_path:
        launch["executable_path"] = executable_path

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(**launch)  # type: ignore[arg-type]
            try:
                page = browser.new_page(user_agent=USER_AGENT)
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                # Let XHR-driven content settle; ignore the timeout if the page
                # keeps a connection open (common on job sites).
                try:
                    page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass
                return page.content()
            finally:
                browser.close()
    except Exception:
        return None
