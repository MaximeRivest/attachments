"""
renderer_image: screenshot each page of a PDF with Playwright/Chromium.
MIT/BSD-only stack (Playwright + Chromium).

Usage
-----
pip install attachments[browser]          # see optional-deps section
"""
from __future__ import annotations

import asyncio, base64, io, math, threading, tempfile, os, pathlib
from attachments.plugin_api import register_plugin, requires
from attachments.core import Renderer
from attachments.testing import PluginContract

@register_plugin("renderer_image", priority=141)  # HIGHER than PyPDFInlineImages (140)
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

    # --- helper to run sync Playwright in a thread (like webpage renderers) ---
    def run_playwright_sync_in_any_loop(self, fn, *args, **kw):
        # verbose = kw.pop('verbose', False) # Get verbose from kwargs if passed this way
        # For simplicity, let's assume verbose is a direct parameter or retrieved from meta earlier
        # This helper is called from render, which has access to meta.
        # We'll need to pass verbose to this helper if we want its prints to be conditional.
        # For now, let's assume the calling context (render) handles meta and verbose.
        # The prints inside this helper are more about its own operation.
        # Let's make them conditional on a verbose kwarg to this function directly.
        verbose_helper = kw.pop('verbose_helper', False)

        if verbose_helper:
            print(f"[BrowserPDFSnapshotHelper] run_playwright_sync_in_any_loop: About to run {fn.__name__} in a new thread.")
        out, err = {}, None
        def runner():
            nonlocal err
            if verbose_helper:
                print(f"[BrowserPDFSnapshotHelper] run_playwright_sync_in_any_loop: Thread started for {fn.__name__}.")
            try:
                out["value"] = fn(*args, **kw)
                if verbose_helper:
                    print(f"[BrowserPDFSnapshotHelper] run_playwright_sync_in_any_loop: {fn.__name__} completed. Output keys: {out.keys()}")
            except Exception as e:
                if verbose_helper:
                    print(f"[BrowserPDFSnapshotHelper] run_playwright_sync_in_any_loop: Exception in {fn.__name__} thread: {e}")
                err = e
        t = threading.Thread(target=runner, daemon=True)
        t.start(); t.join()
        if err:
            if verbose_helper:
                print(f"[BrowserPDFSnapshotHelper] run_playwright_sync_in_any_loop: Re-raising error from {fn.__name__} thread.")
            raise err
        if verbose_helper:
            print(f"[BrowserPDFSnapshotHelper] run_playwright_sync_in_any_loop: Returning value from {fn.__name__}.")
        return out["value"]

    # ---------- render ------------------------------------------------
    def _render_sync(self, pdf_bytes: bytes, pages: int, max_pages: int, verbose: bool):
        from playwright.sync_api import sync_playwright, ViewportSize
        if verbose:
            print(f"[BrowserPDFSnapshot] _render_sync: PDF has {pages} pages, max_pages={max_pages}")
        out = []
        temp_pdf_file = None
        user_data_dir = os.path.join(tempfile.gettempdir(), "playwright_pdf_user_data")
        # pathlib.Path(user_data_dir).mkdir(parents=True, exist_ok=True) # This might be too aggressive if not needed by simpler launch
        # if verbose:
        #     print(f"[BrowserPDFSnapshot] Using user_data_dir: {user_data_dir}")

        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file_obj:
                tmp_file_obj.write(pdf_bytes)
                temp_pdf_file = tmp_file_obj.name
            if verbose:
                print(f"[BrowserPDFSnapshot] PDF bytes written to temporary file: {temp_pdf_file}")

            if not os.path.isabs(temp_pdf_file):
                temp_pdf_file_abs = os.path.abspath(temp_pdf_file)
            else:
                temp_pdf_file_abs = temp_pdf_file
            file_url = f"file://{temp_pdf_file_abs}"

            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=False, 
                    args=["--disable-gpu"]
                )
                context = browser.new_context(
                    accept_downloads=False,
                )
                
                for idx in range(min(pages, max_pages)):
                    if verbose:
                        print(f"[BrowserPDFSnapshot] Processing page {idx+1}")
                    page_specific_url = f"{file_url}#page={idx+1}"
                    if verbose:
                        print(f"[BrowserPDFSnapshot] Navigating to: {page_specific_url}")
                    page = context.new_page()
                    try:
                        page.set_viewport_size(ViewportSize(width=1280, height=1024))
                        page.emulate_media(media='screen')
                        page.goto(page_specific_url, wait_until="networkidle", timeout=10000)
                        page.wait_for_timeout(500) # Small explicit wait
                        
                        if verbose:
                            print(f"[BrowserPDFSnapshot] Taking screenshot for page {idx+1}...")
                        png = page.screenshot()
                        b64 = base64.b64encode(png).decode()
                        out.append(f"data:image/png;page={idx+1};base64,{b64}")
                    except Exception as page_e:
                        if verbose:
                            print(f"[BrowserPDFSnapshot] Error processing page {idx+1} URL {page_specific_url}: {page_e}")
                    finally:
                        page.close()
                browser.close()
        except Exception as e:
            if verbose:
                print(f"[BrowserPDFSnapshot] Exception during _render_sync: {e}")
            raise 
        finally:
            if temp_pdf_file and os.path.exists(temp_pdf_file):
                if verbose:
                    print(f"[BrowserPDFSnapshot] Deleting temporary file: {temp_pdf_file}")
                os.remove(temp_pdf_file)
            
        if verbose:
            print(f"[BrowserPDFSnapshot] Output images: {len(out)}")
        return out

    def render(self, reader, meta):
        verbose = meta.get("verbose", False) if meta else False
        if verbose:
            print(f"[BrowserPDFSnapshot] render: Called with reader={type(reader)}, meta={meta}")
        
        max_pages = int(meta.get("max_pages", 10)) if meta else 10
        pdf_bytes = b''
        try:
            # current_pos = reader.stream.tell()
            reader.stream.seek(0)
            # if verbose:
            #     print(f"[BrowserPDFSnapshot] render: Seeked reader.stream to 0. Previous position was {current_pos}.")
            pdf_bytes = reader.stream.read()
            # reader.stream.seek(current_pos) # Don't necessarily need to restore
        except Exception as e_seek:
            if verbose:
                print(f"[BrowserPDFSnapshot] render: Warning - could not seek/read reader.stream: {e_seek}.")
            return None

        pages = len(reader.pages)
        if verbose:
            print(f"[BrowserPDFSnapshot] render: pdf_bytes length={len(pdf_bytes)}, pages={pages}, max_pages_from_meta={max_pages}")
        
        if not pdf_bytes:
            if verbose:
                print("[BrowserPDFSnapshot] render: pdf_bytes is empty. Aborting.")
            return []
        if pages == 0:
            if verbose:
                print("[BrowserPDFSnapshot] render: No pages found in PDF. Aborting.")
            return []
        
        if verbose:
            print(f"[BrowserPDFSnapshot] render: Calling run_playwright_sync_in_any_loop with _render_sync.")
        # Pass verbose to the helper, and also to _render_sync
        result = self.run_playwright_sync_in_any_loop(self._render_sync, pdf_bytes, pages, max_pages, verbose=verbose, verbose_helper=verbose)
        if verbose:
            print(f"[BrowserPDFSnapshot] render: Result from _render_sync: {type(result)}, length: {len(result) if isinstance(result, list) else 'N/A'}")
        return result
