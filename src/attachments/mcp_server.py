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

Security: the server reads local files and fetches URLs with the user's
permissions — only attach it to agents you trust.
"""

_ATT_DESCRIPTION = """\
Turn any source into LLM-ready content — one universal ingestion tool.

Sources: local files ("report.pdf"), directories ("docs/"), glob patterns
("src/**/*.py"), zip/tar archives, HTTP(S) URLs, and GitHub repos
("github://owner/repo"). Format support includes PDF, XLSX/XLS, DOCX,
PPTX, HTML, CSV/TSV, images (with OCR), SVG, Jupyter notebooks, audio
transcription, and 20+ text/code formats.

Options go in the `options` dict (or inline DSL in the source string —
"report.pdf[pages: 1-4]" is the same as options={"pages": "1-4"}):
  - {"pages": "1-4"}          PDF page range
  - {"ocr": true}             force OCR on scanned pages/images
  - {"sheet": "Sales"}        one spreadsheet sheet
  - {"select": "table.data"}  CSS selection from HTML
Call att_options to discover every option per format.

Returns extracted text (one "## <source>" block per file) followed by
page/slide images when present. Errors never raise: they come back as
readable text under "--- notes ---" (e.g. unpack-error, parse-error,
missing-dependency with its pip install remedy)."""

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


def _content_from_artifacts(source: str, artifacts: list[dict]) -> list[Any]:
    """Convert artifacts to MCP content blocks: text first, then images.

    The text block is ``render_text(artifacts)`` plus a ``--- notes ---``
    tail carrying errors/warnings/notes (the teaching layer must reach the
    agent). Image blocks follow, capped at :data:`MAX_IMAGES`; each image
    over :data:`MAX_IMAGE_BYTES` is skipped with a one-line text note.
    Empty results produce explanatory text, never empty content.
    """
    from mcp.types import ImageContent, TextContent

    from .render import render_text

    text = render_text(artifacts)
    notes = _artifact_notes(artifacts)

    image_blocks: list[Any] = []
    images = [
        image for artifact in artifacts for image in (artifact.get("images") or [])
    ]
    for image in images:
        if len(image_blocks) >= MAX_IMAGES:
            notes.append(
                f"{len(images) - MAX_IMAGES} more image(s) omitted "
                f"(cap: {MAX_IMAGES} per call)"
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
    """Build the FastMCP server with the two attachments tools.

    Raises:
        ImportError: With the teaching install message when the ``mcp``
            SDK is not installed.
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise ImportError(_MISSING_MCP_MESSAGE) from exc

    server = FastMCP(
        "attachments",
        instructions=(
            "Universal file/URL ingestion for prompts. Use the att tool to "
            "read anything (PDF, Office, images with OCR, repos, URLs); use "
            "att_options to discover per-format options."
        ),
    )

    @server.tool(name="att", description=_ATT_DESCRIPTION, structured_output=False)
    def att_tool(source: str, options: dict | None = None) -> list[Any]:
        from . import att

        artifacts = att(source, **(options or {}))
        return _content_from_artifacts(source, artifacts)

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
