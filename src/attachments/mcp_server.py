"""attachments MCP server (`attachments-mcp`) — agents get `att()` as a tool.

The Model Context Protocol server exposes the one-function universal
ingestion of this library to any MCP-capable agent (Claude Code, Claude
Desktop, ...). Two tools, mirroring the Python API:

* ``att`` — turn any source (file, directory, glob, zip/tar, URL,
  ``github://`` repo) into prompt-ready text plus page/slide images.
* ``att_options`` — discover the per-format DSL option tables.

Configuration (Claude Code)::

    claude mcp add attachments -- uvx --from "attachments[mcp]" attachments-mcp

Configuration (Claude Desktop ``claude_desktop_config.json``)::

    {
        "mcpServers": {
            "attachments": {
                "command": "uvx",
                "args": ["--from", "attachments[mcp]", "attachments-mcp"],
            }
        }
    }

Service passthrough works by construction: the server reads the same
configuration as the library (``attachments.configure(...)`` and the
``ATTACHMENTS_API_KEY`` / ``ATTACHMENTS_SERVICE_URL`` environment
variables), so pointing ``ATTACHMENTS_SERVICE_URL`` at a hosted tier gives
agents OCR/audio/etc. without local optional dependencies.

Security note: this server reads local files and fetches URLs with the
user's permissions — only attach it to agents you trust.

This module imports cleanly without the ``mcp`` SDK installed; only
running the server requires it (``pip install attachments[mcp]``).
"""

from __future__ import annotations

import sys
from typing import Any

from .deps import DEPENDENCY_MAP

__all__ = ["create_server", "main"]

#: Maximum number of image content blocks returned per ``att`` call.
MAX_IMAGES = 6

#: Per-image payload cap (decoded bytes); larger images are skipped with
#: a one-line text note so payloads stay agent-friendly.
MAX_IMAGE_BYTES = 1_500_000

#: Characters of text returned per ``att`` call (``max_chars``). Clients cut
#: longer results without saying what was lost (Pi removes the middle of
#: anything over 20 KB; Claude Code warns past 10,000 tokens), so a long
#: document comes back in parts, each ending with how to get the next.
MAX_CHARS = 16_000

#: Environment variable that changes :data:`MAX_CHARS` for this server
#: (``0`` = no limit), for clients known to take longer results. The tool's
#: own ``max_chars`` can only lower it: an agent cannot know where its
#: client cuts (in the benchmark, agents raised it and lost pages).
MAX_CHARS_ENV = "ATTACHMENTS_MCP_MAX_CHARS"


def server_max_chars() -> int:
    """The most characters one ``att`` call returns here (``0`` = no limit).

    Examples:
        >>> import os
        >>> os.environ.pop(MAX_CHARS_ENV, None) and None
        >>> server_max_chars()
        16000
    """
    import os

    raw = os.environ.get(MAX_CHARS_ENV, "").strip()
    try:
        value = int(raw) if raw else MAX_CHARS
    except ValueError:
        return MAX_CHARS
    return max(0, value)


def effective_max_chars(asked: int | None) -> tuple[int, bool]:
    """``(limit, capped)``: the agent's *asked* limit, never above the server's.

    Examples:
        >>> effective_max_chars(None)
        (16000, False)
        >>> (
        ...     effective_max_chars(4000),
        ...     effective_max_chars(30000),
        ...     effective_max_chars(0),
        ... )
        ((4000, False), (16000, True), (16000, True))
    """
    ceiling = server_max_chars()
    if asked is None or (ceiling and asked == ceiling):
        return ceiling, False
    if ceiling == 0:
        return max(0, asked), False
    if asked <= 0 or asked > ceiling:
        return ceiling, True
    return asked, False


#: The teaching message shown when the mcp SDK is missing.
_MISSING_MCP_MESSAGE = (
    f"attachments-mcp requires the mcp extra. Install with: {DEPENDENCY_MAP['mcp'][1]}"
)

_HELP = """attachments-mcp — MCP server exposing att() to agents.

Usage:
    attachments-mcp            Run the server on stdio (what MCP clients do)
    attachments-mcp --help     Show this message

Tools exposed:
    att(source, options)       Universal ingestion: files, directories,
                               globs, zip/tar, https://, github://
    att_options(extension)     Per-format DSL option tables

Claude Code:
    claude mcp add attachments -- uvx --from "attachments[mcp]" attachments-mcp

Claude Desktop (claude_desktop_config.json):
    {
      "mcpServers": {
        "attachments": {
          "command": "uvx",
          "args": ["--from", "attachments[mcp]", "attachments-mcp"]
        }
      }
    }

Environment:
    ATTACHMENTS_API_KEY        Hosted-tier API key (enables service fallback)
    ATTACHMENTS_SERVICE_URL    Service endpoint for hosted-tier proxying
                               (OCR/audio without local optional deps)
    ATTACHMENTS_MCP_MAX_CHARS  Most characters per att result (default 16000,
                               0 = no limit), for clients that take more

Security: the server reads local files and fetches URLs with the user's
permissions — only attach it to agents you trust.
"""

_ATT_DESCRIPTION = """\
Turn any source into LLM-ready content — one universal ingestion tool.

Sources: local files ("report.pdf"), folders ("docs/" — an overview first:
file tree, git branch, what was skipped), patterns ("src/**/*.py"),
zip/tar archives, HTTP(S) URLs, and GitHub repos ("github://owner/repo").
Folders skip secrets (.env, keys), dependencies, hidden and .gitignore'd
files, and read at most 1000 files / 256 MiB (options: ignore, hidden,
glob, max_files, max_size, files: false for the overview only). Format
support includes PDF, XLSX/XLS, DOCX, PPTX, old .doc/.ppt (with
LibreOffice), HTML, CSV/TSV, images (with OCR), SVG, Jupyter notebooks,
audio transcription, and 20+ text/code formats.

Options go in the `options` dict (or inline DSL in the source string —
"report.pdf[pages: 1-4]" is the same as options={"pages": "1-4"}):
  - {"pages": "1-4"}          PDF page range
  - {"ocr": true}             force OCR on scanned pages/images
  - {"sheet": "Sales"}        one spreadsheet sheet
  - {"select": "table.data"}  CSS selection from HTML
  - {"links": true}           keep link URLs in web pages (main content
                              only by default; {"main": false} = whole page)
  - {"screenshot": true}      add pictures of a rendered web page
Call att_options to discover every option per format.

Returns extracted text (one "## <source>" block per file, a "[page N]",
"[slide N]" or "[sheet Name]" line where each starts) followed by the
pictures of those pages when present. Long results come in parts of at
most 16000 characters (`max_chars` can lower it, not raise it: longer
results get cut by agent clients): a "--- more ---" note then says what
was shown and how to get the rest (`start`, or the "pages" option to jump
to a page). For a long document, ask for a page range first. Errors
never raise: they come back as readable text under "--- notes ---"
(e.g. unpack-error, parse-error, missing-dependency with its pip install
remedy)."""

_ATT_OPTIONS_DESCRIPTION = """\
Discover per-format options for the att tool.

Pass an extension (".pdf", "xlsx") or source prefix ("github://") for one
table; omit it for the full catalog. Each option works both as a key in
att's `options` dict and inline in the source string as DSL:
path[key: value, key2: value2]."""


def _artifact_notes(artifacts: list[dict]) -> list[str]:
    """Collect teaching lines (errors, warnings, notes) from artifacts.

    Examples:
        >>> from attachments.types import error_artifact, make_artifact
        >>> _artifact_notes([make_artifact(text="fine")])
        []
        >>> _artifact_notes([error_artifact("f.pdf", "parse-error", "bad")])
        ['f.pdf: [parse-error] bad']
        >>> _artifact_notes([make_artifact(meta={"source": "s.pdf", "note": "hint"})])
        ['s.pdf: hint']
    """
    lines: list[str] = []
    for artifact in artifacts:
        meta = artifact.get("meta") or {}
        source = meta.get("source") or "(unknown)"
        error = meta.get("error")
        if isinstance(error, dict):
            lines.append(
                f"{source}: [{error.get('code', 'error')}] {error.get('message', '')}"
            )
        for warning in meta.get("warnings") or []:
            lines.append(f"{source}: {warning}")
        note = meta.get("note")
        if note:
            lines.append(f"{source}: {note}")
    return lines


def _marker(segment: dict, artifact: dict) -> str | None:
    """``[page 3]``, ``[slide 2]``, ``[sheet Sales]`` for a paged segment."""
    from ._watermark import page_label

    page = segment.get("page")
    if not isinstance(page, int) or isinstance(page, bool):
        return None
    if segment.get("kind") == "sheet":
        return f"[sheet {segment.get('label') or page}]"
    return f"[{page_label({'page': page}, artifact)}]"


def _render_marked(artifacts: list[dict]) -> tuple[str, list[tuple], list[tuple]]:
    """The text the tool returns, with a marker line before each page.

    Same blocks as ``render_text`` (``## <source>`` then the text), plus a
    ``[page N]`` / ``[slide N]`` / ``[sheet Name]`` line where each page,
    slide or sheet starts, so an agent can tell where it is in a document
    and ask for other pages.

    Returns ``(text, pages, images)``: *pages* lists ``(offset, source,
    page, pages_in_artifact, kind)`` for each marker; *images* lists ``(offset,
    image)``, the offset where the image belongs (the end of its page, or
    of its artifact), so a part of the text comes with its own pictures.

    Examples:
        >>> art = {
        ...     "text": "one\\n\\ntwo",
        ...     "images": [],
        ...     "meta": {
        ...         "source": "a.pdf",
        ...         "segments": [
        ...             {
        ...                 "kind": "page",
        ...                 "label": "page 1",
        ...                 "start": 0,
        ...                 "end": 3,
        ...                 "page": 1,
        ...             },
        ...             {
        ...                 "kind": "page",
        ...                 "label": "page 2",
        ...                 "start": 5,
        ...                 "end": 8,
        ...                 "page": 2,
        ...             },
        ...         ],
        ...     },
        ... }
        >>> print(_render_marked([art])[0])
        ## a.pdf
        [page 1]
        one
        <BLANKLINE>
        [page 2]
        two
    """
    from .render import _shown, _source

    out = ""
    pages: list[tuple] = []
    placed: list[tuple] = []
    for artifact in _shown(artifacts, True):
        body = artifact.get("text") or ""
        images = list(artifact.get("images") or [])
        if not body.strip() and not images:
            continue
        src = _source(artifact)
        out += ("\n\n" if out else "") + f"## {src}\n"
        segments = sorted(
            (
                s
                for s in ((artifact.get("meta") or {}).get("segments") or [])
                if isinstance(s.get("start"), int) and _marker(s, artifact)
            ),
            key=lambda s: s["start"],
        )
        page_end: dict[int, int] = {}
        if not body.strip():
            out += "\n".join(f"[image: {i.get('name') or 'image'}]" for i in images)
        elif not segments:
            out += body.strip()
        else:
            parts = []
            lead = body[: segments[0]["start"]].strip()
            if lead:
                parts.append((None, lead))
            for k, seg in enumerate(segments):
                stop = segments[k + 1]["start"] if k + 1 < len(segments) else len(body)
                parts.append((seg, body[seg["start"] : stop].strip()))
            mine = []
            for k, (seg, chunk) in enumerate(parts):
                if k:
                    out += "\n\n"
                if seg is not None:
                    mine.append((len(out), seg["page"]))
                    pages.append(
                        (len(out), src, seg["page"], len(segments), seg.get("kind"))
                    )
                    out += _marker(seg, artifact) + ("\n" + chunk if chunk else "")
                else:
                    out += chunk
            for k, (_offset, page) in enumerate(mine):
                page_end[page] = mine[k + 1][0] if k + 1 < len(mine) else len(out)
        for image in images:
            page = image.get("page")
            placed.append((page_end.get(page, len(out)), image))
    return out, pages, placed


def _content_from_artifacts(
    source: str,
    artifacts: list[dict],
    *,
    start: int = 0,
    max_chars: int | None = None,
) -> list[Any]:
    """Convert artifacts to MCP content blocks: text first, then images.

    The text is :func:`_render_marked` (``## <source>`` blocks with a
    ``[page N]`` line where each page starts) plus a ``--- notes ---`` tail
    carrying errors/warnings/notes (the teaching layer must reach the
    agent). At most *max_chars* (default :data:`MAX_CHARS`; ``0`` = no
    limit) characters from *start* are returned, cut where a page starts
    when one is near; a ``--- more ---`` note then says what was shown and
    how to get the rest (``start=``, or the ``pages`` option). Images
    follow: those of the pages shown, capped at :data:`MAX_IMAGES`; each
    image over :data:`MAX_IMAGE_BYTES` is skipped with a one-line note.
    Empty results produce explanatory text, never empty content.
    """
    from mcp.types import ImageContent, TextContent

    full, pages, placed = _render_marked(artifacts)
    notes = _artifact_notes(artifacts)
    budget, capped = effective_max_chars(max_chars)
    start = max(0, min(int(start or 0), len(full)))
    end = len(full)
    if budget and end - start > budget:
        limit = start + budget
        # Cut where a page starts, if one does in the second half of the part.
        starts = [p[0] for p in pages if start + budget // 2 < p[0] <= limit]
        if starts:
            end = max(starts)
        else:
            newline = full.rfind("\n", start + budget // 2, limit)
            end = newline + 1 if newline > 0 else limit
    text = full[start:end].rstrip()
    if start:
        text = f"(continued from character {start} of {len(full)})\n{text}"
    more: list[str] = []
    if start or end < len(full):
        shown = [p for p in pages if start <= p[0] < end]
        line = f"Shown: characters {start}-{end} of {len(full)}."
        if end < len(full):
            line += (
                f" The rest: call att again with the same source and options "
                f"and start={end}."
            )
        if capped:
            line += (
                f" (max_chars is at most {budget} here: agent clients cut longer "
                "results in the middle without saying so)"
            )
        more.append(line)
        by_source: dict[str, list[tuple]] = {}
        for p in shown:
            by_source.setdefault(p[1], []).append(p)
        for src, ps in by_source.items():
            first, last, total, kind = ps[0][2], ps[-1][2], ps[0][3], ps[-1][4]
            unit = (
                "sheets"
                if kind == "sheet"
                else "slides"
                if kind == "slide"
                else "pages"
            )
            if first == 1 and last == total:
                more.append(f"{src}: all {total} {unit} shown")
            elif kind == "sheet":
                more.append(
                    f"{src}: sheets {first}-{last} shown, of {total}; one sheet "
                    'directly: options {"sheet": "<name>"}'
                )
            else:
                nxt = f"{last + 1}-{min(total, last + 10)}"
                more.append(
                    f"{src}: {unit} {first}-{last} shown, of {total}; any {unit} "
                    f'directly: options {{"pages": "{nxt}"}} '
                    '(or "pages": "N" for one)'
                )

    image_blocks: list[Any] = []
    # The pictures of the pages shown (a page ending exactly at *start* was
    # shown, with its pictures, in the previous part).
    images = [
        image
        for offset, image in placed
        if (start == 0 or offset > start) and offset <= end
    ]
    for image in images:
        if len(image_blocks) >= MAX_IMAGES:
            notes.append(
                f"{len(images) - MAX_IMAGES} more image(s) omitted "
                f"(cap: {MAX_IMAGES} per call; ask for fewer pages to see them)"
            )
            break
        raw = image.get("bytes")
        if not isinstance(raw, bytes | bytearray):
            continue
        if len(raw) > MAX_IMAGE_BYTES:
            name = image.get("name") or "image"
            size_mb = len(raw) / 1_000_000
            cap_mb = MAX_IMAGE_BYTES / 1_000_000
            notes.append(
                f"image skipped: {name} ({size_mb:.1f} MB > {cap_mb:.1f} MB cap)"
            )
            continue
        import base64

        image_blocks.append(
            ImageContent(
                type="image",
                data=base64.b64encode(bytes(raw)).decode("ascii"),
                mimeType=image.get("mimetype") or "application/octet-stream",
            )
        )

    if not text and not image_blocks and not notes:
        text = f"(no content extracted from {source})"
    if more:
        text = f"{text}\n\n--- more ---\n" + "\n".join(more)
    if notes:
        tail = "\n".join(notes)
        text = f"{text}\n\n--- notes ---\n{tail}" if text else f"--- notes ---\n{tail}"

    return [TextContent(type="text", text=text), *image_blocks]


def _normalize_options_key(key: str | None) -> str | None:
    """Normalize an att_options key the way the CLI does.

    Examples:
        >>> _normalize_options_key("pdf")
        '.pdf'
        >>> _normalize_options_key(".PDF")
        '.pdf'
        >>> _normalize_options_key("github://")
        'github://'
        >>> _normalize_options_key(None) is None
        True
    """
    if key is None:
        return None
    if "://" in key:
        return key
    if not key.startswith((".", "__")):
        key = "." + key
    return key.lower()


def create_server() -> Any:
    """Build the MCP server with the two attachments tools.

    Works with the ``mcp`` SDK 1.x (``FastMCP``) and 2.x, where the same
    class was renamed ``MCPServer``; everything used here is unchanged.

    Raises:
        ImportError: With the teaching install message when the ``mcp``
            SDK is not installed.
    """
    try:
        from mcp.server.mcpserver import MCPServer as Server  # mcp 2.x
    except ImportError:
        try:
            from mcp.server.fastmcp import FastMCP as Server  # mcp 1.x
        except ImportError as exc:
            try:
                from importlib.metadata import version

                installed = version("mcp")
            except Exception:  # not installed at all
                raise ImportError(_MISSING_MCP_MESSAGE) from exc
            raise ImportError(
                f"attachments-mcp does not support the installed mcp {installed} "
                f"({exc}). Install a supported one with: pip install 'mcp>=1.17'"
            ) from exc

    server = Server(
        "attachments",
        instructions=(
            "Universal file/URL ingestion for prompts. Use the att tool to "
            "read anything (PDF, Office, images with OCR, repos, URLs); use "
            "att_options to discover per-format options."
        ),
    )

    @server.tool(name="att", description=_ATT_DESCRIPTION, structured_output=False)
    def att_tool(
        source: str,
        options: dict | None = None,
        start: int = 0,
        max_chars: int | None = None,
    ) -> list[Any]:
        from . import att

        artifacts = att(source, **(options or {}))
        return _content_from_artifacts(
            source, artifacts, start=start, max_chars=max_chars
        )

    @server.tool(
        name="att_options",
        description=_ATT_OPTIONS_DESCRIPTION,
        structured_output=False,
    )
    def att_options_tool(extension: str | None = None) -> str:
        from ._options import options

        table = repr(options(_normalize_options_key(extension)))
        return (
            f"{table}\n\n"
            "DSL syntax: path[key: value, key2: value2] — every option also "
            "works as a key in the att tool's `options` dict."
        )

    return server


def main(argv: list[str] | None = None) -> int:
    """Run the server on stdio (or print usage with ``--help``)."""
    args = sys.argv[1:] if argv is None else argv
    if any(a in {"-h", "--help", "help"} for a in args):
        print(_HELP)
        return 0
    try:
        server = create_server()
    except ImportError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    server.run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
