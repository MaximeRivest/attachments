"""Processor for Jupyter notebooks (.ipynb).

Zero dependencies — a notebook is just JSON (stdlib ``json``). Markdown
cells are emitted verbatim, code cells are fenced with the notebook
language (``\\`\\`\\`python``), raw cells are emitted as-is. With
``outputs: true`` the per-cell text outputs (stream text and the
``text/plain`` of execute_result/display_data) are appended as fenced
``output`` blocks (truncated per-output at ~2000 chars), and embedded
``image/png`` outputs become image items named
``<file>-cell-N-output.png``.

Only nbformat 4 (the ``cells`` key, standard since 2015) is supported.
nbformat 3 notebooks (the legacy ``worksheets`` layout) return a clean
``parse-error`` artifact explaining the situation and the remedy
(``jupyter nbconvert --to notebook`` upgrades them) — supporting the
dead format was judged not worth the parallel extraction path.
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

from .._options import Option, register_options
from ..types import ERROR_PARSE, error_artifact, make_artifact
from . import register_processor

log = logging.getLogger("attachments.processors.ipynb")

_CELL_SEPARATOR = "\n\n"

#: Per-output text truncation threshold (characters).
_OUTPUT_CHAR_LIMIT = 2000

_TRUNCATION_MARKER = "… (truncated)"


def _join_source(source: Any) -> str:
    """Normalize a cell's ``source`` (string or list of lines) to one string.

    Examples:
        >>> _join_source(["a\\n", "b"])
        'a\\nb'
        >>> _join_source("plain")
        'plain'
        >>> _join_source(None)
        ''
    """
    if isinstance(source, list):
        return "".join(str(line) for line in source)
    return "" if source is None else str(source)


def _truncate(text: str) -> str:
    """Cap one output's text at ~2000 chars with a truncation marker.

    Examples:
        >>> _truncate("short")
        'short'
        >>> _truncate("x" * 3000).endswith("… (truncated)")
        True
        >>> len(_truncate("x" * 3000)) <= 2000 + len("\\n… (truncated)")
        True
    """
    if len(text) <= _OUTPUT_CHAR_LIMIT:
        return text
    return text[:_OUTPUT_CHAR_LIMIT].rstrip() + "\n" + _TRUNCATION_MARKER


def _output_texts(cell: dict) -> list[str]:
    """Collect text renderings of a code cell's outputs (truncated each)."""
    texts: list[str] = []
    for out in cell.get("outputs") or []:
        if not isinstance(out, dict):
            continue
        otype = out.get("output_type")
        if otype == "stream":
            text = _join_source(out.get("text"))
        elif otype in ("execute_result", "display_data"):
            text = _join_source((out.get("data") or {}).get("text/plain"))
        elif otype == "error":
            text = "\n".join(str(line) for line in out.get("traceback") or [])
        else:
            text = ""
        text = text.strip("\n")
        if text:
            texts.append(_truncate(text))
    return texts


def _output_images(cell: dict, cell_no: int, stem: str) -> list[dict[str, Any]]:
    """Extract image/png outputs of one cell as ImageItems.

    The first image of cell N is named ``<stem>-cell-N-output.png``;
    further images in the same cell get a ``-2``, ``-3``, ... suffix.
    """
    images: list[dict[str, Any]] = []
    for out in cell.get("outputs") or []:
        if not isinstance(out, dict):
            continue
        b64 = (out.get("data") or {}).get("image/png")
        if not b64:
            continue
        try:
            blob = base64.b64decode(_join_source(b64))
        except Exception as exc:
            log.debug("skipping undecodable image in cell %d: %s", cell_no, exc)
            continue
        suffix = "" if not images else f"-{len(images) + 1}"
        images.append(
            {
                "name": f"{stem}-cell-{cell_no}-output{suffix}.png",
                "mimetype": "image/png",
                "bytes": blob,
            }
        )
    return images


def _render_cell(cell: dict, language: str, outputs: bool) -> tuple[str, str]:
    """Render one cell; return ``(cell_type, cell_text)``."""
    cell_type = str(cell.get("cell_type") or "raw")
    source = _join_source(cell.get("source"))
    if cell_type == "code":
        parts = [f"```{language}\n{source}\n```"]
        if outputs:
            parts += [f"```output\n{t}\n```" for t in _output_texts(cell)]
        return "code", "\n\n".join(parts)
    if cell_type == "markdown":
        return "markdown", source
    return "raw", source


def ipynb_processor(
    data: bytes,
    *,
    filename: str | None = None,
    outputs: bool = False,
    **_opts: Any,
) -> dict[str, Any]:
    """Jupyter notebook (.ipynb) -> artifact dict (text, images, meta).

    Options (via att(..., **options)):
      - outputs: include per-cell text outputs as fenced ``output``
        blocks (truncated at ~2000 chars each) and extract image/png
        outputs as image items. Default False.

    meta.kind is ``"notebook"``; meta.segments has one ``"section"``
    segment per cell labelled ``cell N (markdown|code|raw)`` whose
    offsets slice ``text`` exactly to that cell's rendered text.
    """
    source = filename or "file.ipynb"
    stem = source.rsplit("/", 1)[-1]
    stem = stem[:-6] if stem.lower().endswith(".ipynb") else stem

    try:
        nb = json.loads(data.decode("utf-8", errors="replace"))
    except Exception as e:
        return error_artifact(source, ERROR_PARSE, f"Failed to parse notebook: {e}")

    if not isinstance(nb, dict):
        return error_artifact(
            source, ERROR_PARSE, "Failed to parse notebook: not a JSON object"
        )
    cells = nb.get("cells")
    if cells is None:
        if "worksheets" in nb:
            return error_artifact(
                source,
                ERROR_PARSE,
                "Notebook uses the legacy nbformat 3 layout ('worksheets'); "
                "only nbformat 4 is supported. Upgrade it with: "
                "jupyter nbconvert --to notebook file.ipynb",
            )
        return error_artifact(
            source, ERROR_PARSE, "Failed to parse notebook: missing 'cells' key"
        )
    if not isinstance(cells, list):
        return error_artifact(
            source, ERROR_PARSE, "Failed to parse notebook: 'cells' is not a list"
        )

    metadata = nb.get("metadata") or {}
    language = (
        (metadata.get("language_info") or {}).get("name")
        or (metadata.get("kernelspec") or {}).get("language")
        or "python"
    )

    parts: list[str] = []
    segments: list[dict] = []
    images: list[dict[str, Any]] = []
    counts = {"code": 0, "markdown": 0, "raw": 0}
    offset = 0
    for cell_no, cell in enumerate(cells, start=1):
        if not isinstance(cell, dict):
            cell = {}
        cell_type, cell_text = _render_cell(cell, language, outputs)
        counts[cell_type] += 1
        if outputs and cell_type == "code":
            images.extend(_output_images(cell, cell_no, stem))
        if parts:
            offset += len(_CELL_SEPARATOR)
        segments.append(
            {
                "kind": "section",
                "label": f"cell {cell_no} ({cell_type})",
                "start": offset,
                "end": offset + len(cell_text),
            }
        )
        parts.append(cell_text)
        offset += len(cell_text)

    extra: dict[str, Any] = {
        "cell_counts": counts,
        "language": language,
        "nbformat": nb.get("nbformat", 4),
    }
    meta: dict[str, Any] = {"kind": "notebook", "extra": extra}
    if segments:
        meta["segments"] = segments
    return make_artifact(text=_CELL_SEPARATOR.join(parts), images=images, meta=meta)


#: Extensions handled by this processor.
EXTENSIONS = (".ipynb",)

#: Declared option schema (see attachments.options).
OPTIONS: tuple[Option, ...] = (
    Option(
        name="outputs",
        type="bool",
        default=False,
        help=(
            "Include per-cell execution outputs: text outputs as fenced "
            "blocks (truncated at ~2000 chars each) and image/png outputs "
            "as image items."
        ),
        example="outputs: true",
    ),
)


def register() -> None:
    """Register the ipynb processor and its option schema (idempotent)."""
    for ext in EXTENSIONS:
        register_processor(ext, ipynb_processor)
        register_options(ext, OPTIONS)


register()
