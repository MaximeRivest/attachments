"""Processor for HTML pages and files (.html, .htm).

Text: the page as Markdown — headings, lists, pipe tables, fenced code with
its language, TeX maths — with sentences kept whole across links and
emphasis (see ``_html_md``). By default only the main content is kept:
navigation, site header/footer, sidebars and cookie/share widgets are
skipped (``main: false`` keeps everything). Links are plain text unless
``links: true``.

Images: ``images: true`` extracts inline data-URI images;
``screenshot: true`` adds screen-sized captures of the page rendered in a
headless browser (``_browser``; needs ``attachments[browser]``).

When the HTML came from a URL, core passes that address as the ``url``
option: it resolves relative links and is the page a screenshot loads.

Requires ``beautifulsoup4`` + ``lxml``: ``pip install attachments[html]``
"""

from __future__ import annotations

import base64
import logging
import re
from typing import Any
from urllib.parse import urljoin

from .._options import Option, register_options
from ..deps import check_dep
from ..types import (
    ERROR_INVALID_OPTION,
    ERROR_MISSING_DEPENDENCY,
    ERROR_PARSE,
    error_artifact,
    make_artifact,
    missing_dep_artifact,
)
from . import register_processor
from ._imageout import check_image_output, limit, output_format

log = logging.getLogger("attachments.processors.html")

#: Screens captured by default (from the top). Each 1280x800 screen costs
#: roughly 1,400 tokens with Claude; 5 covers the part of most pages people
#: read first without flooding the context.
DEFAULT_MAX_SCREENS = 5

#: Shown (meta.note) when a page's HTML has almost no text but has scripts.
JS_PAGE_NOTE = (
    "Almost no text in this page's HTML: it is likely built by JavaScript, "
    "which is not run. Add [screenshot: true] to see it rendered."
)
_JS_PAGE_MAX_CHARS = 80


def _title(soup: Any) -> str | None:
    tag = soup.find("title")
    if tag:
        title = re.sub(r"\s+", " ", tag.get_text()).strip()
        return title or None
    return None


def _base_url(soup: Any, url: str | None) -> str | None:
    """Address relative links resolve against: ``<base href>``, else *url*."""
    base = soup.find("base", href=True)
    if base is not None:
        href = str(base["href"]).strip()
        if href:
            try:
                return urljoin(url or "", href)
            except ValueError:
                return url
    return url


def _data_uri_images(img_tags: list[Any], filename: str) -> list[dict[str, Any]]:
    images: list[dict[str, Any]] = []
    for img_tag in img_tags:
        src = str(img_tag.get("src") or "")
        if not src.startswith("data:"):
            continue
        try:
            header, b64 = src.split(",", 1)
            mime = header.split(";")[0].replace("data:", "") or "image/png"
            ext = mime.split("/")[-1].split("+")[0] or "png"
            images.append(
                {
                    "name": f"{filename}-img-{len(images) + 1}.{ext}",
                    "mimetype": mime,
                    "bytes": base64.b64decode(b64),
                }
            )
        except Exception as exc:
            log.debug("skipping data-URI image: %s", exc)
    return images


def html_processor(
    data: bytes,
    *,
    filename: str | None = None,
    select: str | None = None,
    main: bool = True,
    links: bool = False,
    url: str | None = None,
    render_images: bool = False,
    images: bool = False,
    screenshot: bool = False,
    max_screens: int = DEFAULT_MAX_SCREENS,
    max_dim: int | None = None,
    image_format: str | None = None,
    quality: int | None = None,
    **_: Any,
) -> dict[str, Any]:
    """Convert HTML bytes to an artifact (Markdown text, optional images).

    Options:
        select: CSS selector; only matching elements (in document order)
            are rendered, each as its own block, and ``main`` is ignored.
            The title is recorded in ``extra.title`` but NOT prefixed.
            No-match and invalid selectors are not errors: the text is
            empty and ``extra.select_note`` says why.
        main: ``True`` (default) keeps the main content only; ``False``
            renders the whole page.
        links: ``True`` writes links as ``[text](url)`` and images as
            ``![alt](url)`` (relative addresses resolved); default plain
            link text and no images in the text.
        url: The page's address (core fills it for web pages). Resolves
            relative links; ``screenshot`` loads the page from it.
        render_images: (DSL ``images``; direct callers may pass ``images``)
            extract inline data-URI images.
        screenshot: capture the rendered page as 1280x800 screens.
        max_screens: most screens to capture, from the top (0 = all).
        max_dim / image_format / quality: screenshot size and encoding,
            with the same meaning as for PDF page images.

    DSL note: the parser takes the final *balanced* bracket group, so
    attribute selectors work inline — ``page.html[select: a[href]]``.
    Comma groups work unquoted (``[select: h1, p]``): a segment without a
    colon continues the previous value (DSL rule 2a). A value with a comma
    followed by ``key:``-like text must be quoted.

    Examples:
        >>> art = html_processor(
        ...     b"<html><head><title>T</title></head>"
        ...     b"<body><h1>Top</h1><p>Body with <a href='/x'>a link</a>.</p>"
        ...     b"</body></html>",
        ... )
        >>> print(art["text"])
        # Top
        <BLANKLINE>
        Body with a link.
        >>> art = html_processor(b"<h1>Top</h1><p>Body</p>", select="h1")
        >>> art["text"], art["meta"]["extra"]["selected_count"]
        ('# Top', 1)
        >>> bad = html_processor(b"<p>x</p>", select="li:::")
        >>> bad["text"], bad["meta"]["extra"]["selected_count"]
        ('', 0)
    """
    source = filename or "page.html"

    def invalid(message: str) -> dict[str, Any]:
        artifact = error_artifact(source, ERROR_INVALID_OPTION, message)
        artifact["meta"]["kind"] = "html"
        return artifact

    problem = check_image_output(
        max_dim=max_dim, image_format=image_format, quality=quality
    )
    if problem:
        return invalid(problem)
    if (
        isinstance(max_screens, bool)
        or not isinstance(max_screens, int)
        or max_screens < 0
    ):
        return invalid(
            f"max_screens must be an integer >= 0 (0 = whole page), got {max_screens!r}"
        )
    if url is not None and not isinstance(url, str):
        return invalid(f"url must be a string, got {url!r}")

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return missing_dep_artifact(source, "html")
    from ._html_md import render, render_selection

    try:
        import lxml  # noqa: F401

        parser = "lxml"
    except ImportError:
        parser = "html.parser"

    try:
        soup = BeautifulSoup(data, parser)
    except Exception as e:
        log.warning("failed to parse HTML %s: %s", source, e)
        return error_artifact(source, ERROR_PARSE, f"Failed to parse HTML: {e}")

    title = _title(soup)
    base_url = _base_url(soup, url or None)
    extra: dict[str, Any] = {"filename": source, "title": title, "parser": parser}
    warnings: list[str] = []

    try:
        if isinstance(select, str) and select.strip():
            selector = select.strip()
            extra["selector"] = selector
            try:
                matches = soup.select(selector)
            except Exception as e:  # soupsieve SelectorSyntaxError on garbage
                matches = []
                extra["select_note"] = f"invalid selector: {e}"
            extra["selected_count"] = len(matches)
            if not matches:
                extra.setdefault("select_note", "selector matched no elements")
            rendered = render_selection(matches, links=links, base_url=base_url)
            text = rendered.text
        else:
            rendered = render(soup, main=main, links=links, base_url=base_url)
            text = rendered.text
            if title and not rendered.has_h1:
                text = f"# {title}\n\n{text}".strip()
    except RecursionError:
        # Pathologically deep markup: keep the words, lose the structure.
        warnings.append("HTML nested too deeply for Markdown; plain text kept")
        text = re.sub(r"\n{3,}", "\n\n", soup.get_text("\n")).strip()
        rendered = None

    extra["content"] = rendered.scope if rendered else "page"
    if rendered is not None and rendered.main_fallback:
        extra["main_fallback"] = True
    if links:
        extra["links"] = True
    if base_url:
        extra["url"] = base_url
    extra["chars"] = len(text)

    out_images: list[dict[str, Any]] = []
    if (render_images or images) and rendered is not None:
        out_images.extend(_data_uri_images(rendered.images, source))

    meta: dict[str, Any] = {"kind": "html", "extra": extra}

    body_chars = len(text) - (len(title) + 2 if title and text.startswith("# ") else 0)
    if (
        not extra.get("selector")
        and body_chars < _JS_PAGE_MAX_CHARS
        and soup.find("script") is not None
        and not screenshot
    ):
        meta["note"] = JS_PAGE_NOTE

    if screenshot:
        shot_result = _screenshots(
            soup=soup,
            data=data,
            source=source,
            url=url,
            max_screens=max_screens,
            max_dim=max_dim,
            image_format=image_format,
            quality=quality,
            extra=extra,
            warnings=warnings,
        )
        if isinstance(shot_result, dict):  # a typed error artifact
            return shot_result
        out_images.extend(shot_result)

    if warnings:
        meta["warnings"] = warnings
    return make_artifact(text=text, images=out_images, meta=meta)


def _screenshots(
    *,
    soup: Any,
    data: bytes,
    source: str,
    url: str | None,
    max_screens: int,
    max_dim: int | None,
    image_format: str | None,
    quality: int | None,
    extra: dict[str, Any],
    warnings: list[str],
) -> list[dict[str, Any]] | dict[str, Any]:
    """Screens of the rendered page, or a typed missing-dependency artifact.

    A missing browser is an error (it drives the service fallback, like a
    forced OCR without rapidocr); a page that fails to load in the browser
    keeps its text and gets a warning instead.
    """
    if not check_dep("browser").available:
        artifact = missing_dep_artifact(source, "browser")
        artifact["meta"]["kind"] = "html"
        return artifact
    dim = limit(max_dim)
    if dim is not None and not check_dep("image").available:
        artifact = missing_dep_artifact(source, "image")
        artifact["meta"]["kind"] = "html"
        return artifact

    from .._sources._guards import private_urls_blocked
    from ._browser import BrowserUnavailable, capture_screens, downscale

    pillow_format, mimetype, ext = output_format(image_format or "png")
    page_url = url if url and url.lower().startswith(("http://", "https://")) else None
    html = None
    if page_url is None:
        html = data.decode(soup.original_encoding or "utf-8", errors="replace")
    try:
        capture = capture_screens(
            html=html,
            url=page_url,
            max_screens=max_screens,
            image_type="jpeg" if pillow_format == "JPEG" else "png",
            quality=quality,
            block_private=private_urls_blocked(),
        )
    except BrowserUnavailable as e:
        artifact = error_artifact(source, ERROR_MISSING_DEPENDENCY, str(e))
        artifact["meta"]["kind"] = "html"
        return artifact
    except Exception as e:
        log.warning("screenshot failed for %s: %s", source, e)
        first_line = (
            str(e).strip().splitlines()[0] if str(e).strip() else type(e).__name__
        )
        warnings.append(f"screenshot failed: {first_line}")
        return []

    stem = source.rsplit("/", 1)[-1] or "page"
    shots: list[dict[str, Any]] = []
    for i, shot in enumerate(capture.shots, start=1):
        if dim is not None:
            shot = downscale(shot, dim, pillow_format, quality)
        shots.append(
            {"name": f"{stem}-screen-{i}.{ext}", "mimetype": mimetype, "bytes": shot}
        )
    extra["screenshot"] = {
        "screens": len(shots),
        "screens_total": capture.screens_total,
        "page_height": capture.page_height,
        "width": 1280,
        "loaded_from": "url" if page_url else "html",
    }
    return shots


_HTML_OPTIONS = (
    Option(
        "select",
        "str",
        aliases=("css",),
        help="CSS selector; extract only matching elements",
        example='select: "h1, .article"',
    ),
    Option(
        "main",
        "bool",
        default=True,
        help=(
            "Keep only the main content: skip navigation, site header and "
            "footer, sidebars, cookie/share widgets (false: whole page)"
        ),
        example="main: false",
    ),
    Option(
        "links",
        "bool",
        default=False,
        help=(
            "Write links as [text](url) and images as ![alt](url) (default: plain text)"
        ),
        example="links: true",
    ),
    Option(
        "url",
        "str",
        help=(
            "The page's address: resolves relative links; screenshots load it. "
            "Set automatically for web pages"
        ),
        example="url: https://example.com/docs/",
    ),
    Option(
        "images",
        "bool",
        aliases=("render",),
        param="render_images",
        default=False,
        help="Extract inline data-URI images.",
        example="images: true",
    ),
    Option(
        "screenshot",
        "bool",
        default=False,
        help=(
            "Add screenshots of the page rendered in a browser, 1280x800 "
            "screens from the top (needs attachments[browser])"
        ),
        example="screenshot: true",
    ),
    Option(
        "max_screens",
        "int",
        default=DEFAULT_MAX_SCREENS,
        help="Most screenshots to take, from the top of the page (0 = whole page)",
        example="max_screens: 2",
    ),
    Option(
        "max_dim",
        "int",
        help="Longest side of each screenshot in pixels (0 = no limit)",
        example="max_dim: 1024",
    ),
    Option(
        "image_format",
        "str",
        default="png",
        help="Screenshot format: png (sharpest text) or jpeg (smaller)",
        example="image_format: jpeg",
    ),
    Option(
        "quality",
        "int",
        help="JPEG quality, 1-95 (used with image_format: jpeg)",
        example="quality: 75",
    ),
)
register_processor(".html", html_processor)
register_processor(".htm", html_processor)
register_options(".html", _HTML_OPTIONS)
register_options(".htm", _HTML_OPTIONS)
