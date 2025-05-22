from __future__ import annotations
import asyncio, base64, threading, contextlib
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
        except Exception as e:        # capture & re-raise in caller thread
            err = e

    t = threading.Thread(target=runner, daemon=True)
    t.start(); t.join()
    if err:
        raise err
    return out["value"]

# --------------------------------------------------------------------- #

@register_plugin("renderer_image", priority=125)
@requires("playwright")
class WebPageSnapshot(Renderer, PluginContract):
    content_type = "image"
    _sample_obj  = "https://example.com"

    def match(self, obj):
        return isinstance(obj, str) and obj.startswith(("http://", "https://"))

    # --- core work wrapped as *sync* function -------------------------
    def _snap(self, url: str, w: int = 1280, h: int = 720) -> bytes:
        from playwright.sync_api import sync_playwright          # sync API
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page    = browser.new_page(viewport={"width": w, "height": h})
            page.goto(url, wait_until="networkidle")
            page.wait_for_timeout(200)
            png = page.screenshot(full_page=True)
            browser.close()
        return png

    # --- renderer entry ----------------------------------------------
    def render(self, obj, meta):
        png = run_playwright_sync_in_any_loop(self._snap, obj)
        b64 = base64.b64encode(png).decode()
        return [f"data:image/png;page=1;base64,{b64}"]
