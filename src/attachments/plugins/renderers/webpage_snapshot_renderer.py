from __future__ import annotations
import asyncio, base64
from attachments.plugin_api import register_plugin, requires
from attachments.core import Renderer
from attachments.testing import PluginContract

@register_plugin("renderer_image", priority=125)   # lower than inline-img(140) but above mosaic(130)
@requires("playwright")
class WebPageSnapshot(Renderer, PluginContract):
    """
    Turn a web page into a PNG (full viewport).
    Headless Chromium keeps licences permissive (Apache-2, BSD).
    """
    content_type = "image"
    _sample_obj = "https://example.com"

    def match(self, obj):
        return isinstance(obj, str) and obj.startswith(("http://", "https://"))

    async def _grab(self, url: str) -> str:
        from playwright.async_api import async_playwright # type: ignore
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page    = await browser.new_page(viewport={"width":1280, "height":720})
            await page.goto(url, wait_until="networkidle")
            await page.wait_for_timeout(200)          # let fonts/images settle
            png     = await page.screenshot(full_page=True)
            await browser.close()
        b64 = base64.b64encode(png).decode()
        return f"data:image/png;page=1;base64,{b64}"  # page=1 tag keeps schema

    def render(self, obj, meta):
        return [asyncio.run(self._grab(obj))]
