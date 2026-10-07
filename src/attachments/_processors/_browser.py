"""Page screenshots in a headless browser (Chromium via Playwright).

Used by the html processor's ``screenshot`` option. A web page is loaded
from its address (so scripts, fonts and same-origin requests work exactly
as in a browser); a local HTML file is loaded from its bytes, with any
``<base href>`` resolving its images and stylesheets.

The page is captured as consecutive screen-sized images (1280x800 CSS
pixels) from the top, not as one tall image: a vision model shrinks a
1280x20000 picture until its text is unreadable, while a 1280x800 screen
fits Claude's and OpenAI's image limits at (almost) full resolution.

Safety: when private addresses are blocked (``ATT_BLOCK_PRIVATE_URLS``,
or the self-hosted server — see ``_sources._guards.private_urls_blocked``),
every request the page makes, redirects and sub-resources included, must
pass the same SSRF check as plain downloads; others are aborted.

Playwright's synchronous API refuses to run inside a running asyncio loop
(Jupyter, async apps), so the browser always runs on a worker thread.
"""

from __future__ import annotations

import concurrent.futures
import io
import math
import os
from dataclasses import dataclass
from typing import Any

#: Viewport of every capture, in CSS pixels (device scale factor 1).
VIEWPORT_WIDTH = 1280
VIEWPORT_HEIGHT = 800

#: Navigation / load timeout, and the extra time allowed for the network to
#: go quiet (late images, web fonts) before capturing.
LOAD_TIMEOUT_MS = 30_000
SETTLE_TIMEOUT_MS = 3_000

#: Path to a Chromium/Chrome executable to use instead of Playwright's own
#: download (e.g. a system Chrome, or a Nix-provided Chromium).
CHROMIUM_ENV = "ATTACHMENTS_CHROMIUM"

INSTALL_HINT = (
    "pip install 'attachments[browser]' && playwright install chromium "
    f"(or point {CHROMIUM_ENV} at a Chromium/Chrome executable)"
)


class BrowserUnavailable(RuntimeError):
    """Playwright is installed but no browser executable can be launched."""


@dataclass
class Capture:
    shots: list[bytes]  # encoded images, top to bottom
    page_height: int  # CSS pixels
    screens_total: int  # screens needed to cover the whole page


def _guard_route(route: Any) -> None:
    from .._sources._guards import _assert_public_http_url

    url = route.request.url
    if url.startswith(("data:", "blob:", "about:")):
        route.continue_()
        return
    try:
        _assert_public_http_url(url)
    except ValueError:
        route.abort("blockedbyclient")
        return
    route.continue_()


def _capture(
    *,
    html: str | None,
    url: str | None,
    max_screens: int,
    image_type: str,
    quality: int | None,
    block_private: bool,
) -> Capture:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        launch: dict[str, Any] = {}
        executable = os.environ.get(CHROMIUM_ENV, "").strip()
        if executable:
            launch["executable_path"] = executable
        try:
            browser = p.chromium.launch(**launch)
        except PlaywrightError as e:
            message = str(e)
            if "Executable doesn't exist" in message or "playwright install" in message:
                raise BrowserUnavailable(
                    f"No Chromium for screenshots. Install with: {INSTALL_HINT}"
                ) from None
            raise
        try:
            context = browser.new_context(
                viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
                device_scale_factor=1,
                reduced_motion="reduce",
                service_workers="block",
            )
            page = context.new_page()
            if block_private:
                page.route("**/*", _guard_route)
            if url:
                page.goto(url, wait_until="load", timeout=LOAD_TIMEOUT_MS)
            else:
                page.set_content(html or "", wait_until="load", timeout=LOAD_TIMEOUT_MS)

            def settle(ms: int) -> None:
                try:
                    page.wait_for_load_state("networkidle", timeout=ms)
                except PlaywrightTimeout:
                    pass

            def height() -> int:
                return int(
                    page.evaluate(
                        "Math.max(document.documentElement.scrollHeight,"
                        " document.body ? document.body.scrollHeight : 0, 1)"
                    )
                )

            settle(SETTLE_TIMEOUT_MS)
            # Scroll through the part we capture so lazy-loaded images load.
            screens = math.ceil(height() / VIEWPORT_HEIGHT)
            wanted = screens if max_screens == 0 else min(screens, max_screens)
            for i in range(1, wanted):
                page.evaluate(f"window.scrollTo(0, {i * VIEWPORT_HEIGHT})")
                page.wait_for_timeout(120)
            page.evaluate("window.scrollTo(0, 0)")
            settle(1_500)

            total_height = height()
            screens_total = max(1, math.ceil(total_height / VIEWPORT_HEIGHT))
            wanted = (
                screens_total if max_screens == 0 else min(screens_total, max_screens)
            )
            shot_kwargs: dict[str, Any] = {
                "type": image_type,
                "full_page": True,
                "animations": "disabled",
                "caret": "hide",
            }
            if image_type == "jpeg":
                shot_kwargs["quality"] = quality or 85
            shots = []
            for i in range(wanted):
                top = i * VIEWPORT_HEIGHT
                clip = {
                    "x": 0,
                    "y": top,
                    "width": VIEWPORT_WIDTH,
                    "height": min(VIEWPORT_HEIGHT, total_height - top),
                }
                shots.append(page.screenshot(clip=clip, **shot_kwargs))
            return Capture(shots, total_height, screens_total)
        finally:
            browser.close()


def capture_screens(
    *,
    html: str | None = None,
    url: str | None = None,
    max_screens: int = 5,
    image_type: str = "png",
    quality: int | None = None,
    block_private: bool = False,
) -> Capture:
    """Load a page (``url``) or a document (``html``) and capture screens.

    Raises:
        BrowserUnavailable: no browser executable could be launched.
        Exception: navigation/capture failures (Playwright errors).
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            _capture,
            html=html,
            url=url,
            max_screens=max_screens,
            image_type=image_type,
            quality=quality,
            block_private=block_private,
        )
        return future.result()


def downscale(
    data: bytes, max_dim: int, pillow_format: str, quality: int | None
) -> bytes:
    """Shrink an encoded screenshot so its longest side is at most *max_dim*."""
    from PIL import Image

    from ._imageout import pil_encode

    with Image.open(io.BytesIO(data)) as img:
        if max(img.size) <= max_dim:
            return data
        img = img.copy()
        img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
        return pil_encode(img, pillow_format, quality)
