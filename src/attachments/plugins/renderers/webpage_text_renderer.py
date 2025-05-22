from __future__ import annotations
import re, textwrap, threading
from attachments.plugin_api import register_plugin, requires
from attachments.core import Renderer
from attachments.testing import PluginContract

def run_playwright_sync_in_any_loop(fn, *args, **kw):
    """
    Run a *sync* Playwright function even if the main thread already has
    an event-loop (Jupyter, FastAPI). We execute the whole block in a
    throw-away thread that has no loop.
    """
    out, err = {}, None

    def runner():
        nonlocal err
        try:
            out["value"] = fn(*args, **kw)
        except Exception as e:
            err = e

    t = threading.Thread(target=runner, daemon=True)
    t.start(); t.join()
    if err:
        raise err
    return out["value"]

# --------------------------------------------------------------------- #

@register_plugin("renderer_text", priority=124)
@requires("playwright", "bs4", pip_names={"bs4": "beautifulsoup4"})
class WebPagePlainText(Renderer, PluginContract):
    """
    Extract visible text from a web page by letting Chromium render JS and
    then pulling `page.content()` → BeautifulSoup → get_text().

    • Keeps links, CSS-hidden elements, ads, etc. out.
    • Use `meta["chars"]` to cap length (default 8000).
    """
    content_type = "text"
    _sample_obj  = "https://example.com"

    def match(self, obj):
        if not isinstance(obj, str):
            return False
        return obj.startswith(("http://", "https://"))

    # --- core work wrapped as *sync* function -------------------------
    def _extract_text(self, url: str, max_chars: int = 8000) -> str:
        from playwright.sync_api import sync_playwright
        from bs4 import BeautifulSoup

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page    = browser.new_page()
            page.goto(url, wait_until="networkidle")
            page.wait_for_timeout(100)
            html = page.content()
            browser.close()

        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "noscript"]):
            tag.extract()
        text = soup.get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text)
        text = text[:max_chars]
        return text

    # --- renderer entry ----------------------------------------------
    def render(self, obj, meta):
        max_chars = int(meta.get("chars", 8000)) if meta else 8000
        text = run_playwright_sync_in_any_loop(self._extract_text, obj, max_chars)
        return textwrap.fill(text, width=110)
