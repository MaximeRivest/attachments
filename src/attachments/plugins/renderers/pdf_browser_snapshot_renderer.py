"""
renderer_image: screenshot each page of a PDF with Playwright/Chromium.
MIT/BSD-only stack (Playwright + Chromium).

Usage
-----
pip install attachments[browser]          # see optional-deps section
"""
from __future__ import annotations

import asyncio, base64, io, math
from attachments.plugin_api import register_plugin, requires
from attachments.core import Renderer
from attachments.testing import PluginContract

@register_plugin("renderer_image", priority=135)  # between inline-img(140) & mosaic(130)
@requires("pypdf", "playwright")
class BrowserPDFSnapshot(Renderer, PluginContract):
    """
    Returns one PNG per page (cap via `meta["max_pages"]`, default 10).
    Uses Playwright headless Chromium; keeps everything MIT/BSD.
    """
    content_type = "image"

    try:
        from pypdf import PdfReader # type: ignore
        _sample_obj = PdfReader.__new__(PdfReader)
    except Exception:
        _sample_obj = None

    # ---------- match -------------------------------------------------
    def match(self, obj):
        from pypdf import PdfReader # type: ignore
        return isinstance(obj, PdfReader)

    # ---------- render ------------------------------------------------
    async def _render_async(self, pdf_bytes: bytes, pages: int, max_pages: int):
        from playwright.async_api import async_playwright # type: ignore
        out = []

        async with async_playwright() as p:
            browser = await p.chromium.launch()  # use .launch(headless=True) by default
            context = await browser.new_context()
            for idx in range(min(pages, max_pages)):
                # data: URL with #page=x so Chromium opens at the right page
                data_url = f"data:application/pdf;base64,{base64.b64encode(pdf_bytes).decode()}#page={idx+1}"
                page = await context.new_page()
                await page.goto(data_url, wait_until="networkidle")
                # give Chromium's PDF viewer a moment to render
                await page.wait_for_timeout(100)

                png = await page.screenshot(full_page=True)
                b64 = base64.b64encode(png).decode()
                out.append(f"data:image/png;page={idx+1};base64,{b64}")
                await page.close()
            await browser.close()
        return out

    def render(self, reader, meta):
        max_pages = int(meta.get("max_pages", 10)) if meta else 10
        pdf_bytes = reader.stream.read()
        pages     = len(reader.pages)
        return asyncio.run(self._render_async(pdf_bytes, pages, max_pages))
