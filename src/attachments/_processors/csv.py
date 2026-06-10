"""Processor for delimited text tables (.csv, .tsv).

Always works with the stdlib only: bytes are decoded with
:func:`attachments.utils.guess_decode` (latin-1 tolerant), the delimiter is
sniffed with :class:`csv.Sniffer` (restricted to ``,;\\t|``), and the rows
are rendered as a markdown pipe table capped at ``rows`` data rows.

Deliberate divergences from attachments v1:
    - ``.tsv`` is parsed as a real table (v1 dumped it in a fenced code block).
    - rows are capped at 200 by default (v1 had no cap; 5000-row CSVs became
      ~85KB of markdown). Override with ``rows`` / ``max_rows`` / ``limit``.
    - empty input yields an empty artifact with ``meta.note = "empty CSV"``
      instead of v1's NoneType-fallback garbage.
    - v1's ``head``, ``format`` and ``select`` options are dropped (redundant
      with ``rows``, owned by the render layer, and unreachable in v1's
      high-level API, respectively).
    - ``summary: true`` without pandas does NOT return a missing-dependency
      artifact: the stdlib table succeeded, so the table is returned with a
      ``meta.warnings`` entry carrying the install hint. This is a deliberate
      softening of the missing-dep protocol ("stdlib always works").

Optional pandas enhancement (``pip install attachments[csv-pandas]``):
``summary: true`` appends a ``## Summary`` section with shape, per-column
dtypes and min/mean/max for numeric columns.
"""

from __future__ import annotations

import csv  # stdlib (absolute imports), not this module
import io
import sys
from typing import Any

from .._options import Option, register_options
from ..types import ERROR_PARSE, error_artifact, make_artifact
from ..utils import guess_decode
from . import register_processor

#: Word aliases accepted by the ``delimiter`` option.
_DELIMITER_WORDS = {
    "tab": "\t",
    "comma": ",",
    "semicolon": ";",
    "pipe": "|",
}

#: Candidate delimiters offered to csv.Sniffer.
_SNIFF_DELIMITERS = ",;\t|"

#: How much text the sniffer sees.
_SNIFF_WINDOW = 8192


def _resolve_delimiter(delimiter: str | None, text: str, source: str) -> str:
    """Pick the delimiter: explicit option > sniffing > extension default.

    Examples:
        >>> _resolve_delimiter("tab", "x", "f.csv")
        '\\t'
        >>> _resolve_delimiter(";", "x", "f.csv")
        ';'
        >>> _resolve_delimiter(None, "a;b\\n1;2\\n", "f.csv")
        ';'
        >>> _resolve_delimiter(None, "single", "f.tsv")
        '\\t'
        >>> _resolve_delimiter(None, "single", "f.csv")
        ','
    """
    if delimiter:
        word = str(delimiter).strip().lower()
        if word in _DELIMITER_WORDS:
            return _DELIMITER_WORDS[word]
        return str(delimiter)[0]
    try:
        return (
            csv.Sniffer()
            .sniff(text[:_SNIFF_WINDOW], delimiters=_SNIFF_DELIMITERS)
            .delimiter
        )
    except Exception:
        return "\t" if source.lower().endswith(".tsv") else ","


def _cell(value: Any) -> str:
    """Render one cell for a markdown pipe table.

    Pipes are escaped and newlines collapsed to spaces.

    Examples:
        >>> _cell("a|b")
        'a\\\\|b'
        >>> _cell("two\\nlines")
        'two lines'
        >>> _cell(None)
        ''
    """
    s = "" if value is None else str(value)
    return (
        s.replace("\r\n", " ").replace("\n", " ").replace("\r", " ").replace("|", "\\|")
    )


def _render_table(header: list[Any], rows: list[list[Any]]) -> str:
    """Render header + rows as a markdown pipe table.

    Examples:
        >>> print(_render_table(["a", "b"], [["1", "2"]]))
        | a | b |
        | --- | --- |
        | 1 | 2 |
    """
    lines = [
        "| " + " | ".join(_cell(v) for v in header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_cell(v) for v in row) + " |")
    return "\n".join(lines)


def _pandas_summary(text: str, delim: str) -> str:
    """Build the ``## Summary`` section with pandas (raises on import failure)."""
    import pandas as pd  # type: ignore

    df = pd.read_csv(io.StringIO(text), sep=delim)
    lines = [
        "## Summary",
        "",
        f"- Rows: {df.shape[0]}",
        f"- Columns: {df.shape[1]}",
        "",
        "### Column types",
        "",
    ]
    for col, dtype in df.dtypes.items():
        lines.append(f"- {col}: {dtype}")
    numeric = df.select_dtypes(include="number")
    if not numeric.empty:
        lines += ["", "### Numeric columns (min / mean / max)", ""]
        for col in numeric.columns:
            s = numeric[col]
            lines.append(f"- {col}: {s.min()} / {s.mean()} / {s.max()}")
    return "\n".join(lines)


def csv_processor(
    data: bytes,
    *,
    filename: str | None = None,
    max_rows: int = 200,
    summary: bool = False,
    delimiter: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    """Delimited text -> artifact carrying a markdown pipe table.

    Options:
        filename: Original filename (delimiter default for ``.tsv``).
        max_rows: Maximum number of data rows rendered (default 200).
        summary: Append a pandas-backed ``## Summary`` section when true.
        delimiter: Literal character or one of tab/comma/semicolon/pipe;
            overrides sniffing.

    Never raises: parse failures yield a ``parse-error`` artifact; a missing
    pandas with ``summary: true`` only adds a ``meta.warnings`` entry.
    """
    source = filename or "table.csv"

    try:
        encoding, text = guess_decode(data)

        if not text.strip():
            return make_artifact(
                text="",
                meta={
                    "kind": "table",
                    "note": "empty CSV",
                    "extra": {"rows": 0, "encoding": encoding, "engine": "stdlib"},
                },
            )

        delim = _resolve_delimiter(delimiter, text, source)
        # The stdlib default field limit (131072 chars) aborts parsing of
        # legitimate CSVs with large quoted fields (embedded JSON/text
        # blobs), contradicting "always works with the stdlib". Raise the
        # process-global limit for the duration of the parse and restore it.
        old_limit = csv.field_size_limit()
        try:
            csv.field_size_limit(sys.maxsize)
            records = list(csv.reader(io.StringIO(text), delimiter=delim))
        finally:
            csv.field_size_limit(old_limit)
        header, data_rows = records[0], records[1:]

        limit = int(max_rows)
        truncated = len(data_rows) > limit
        rendered = _render_table(header, data_rows[:limit])

        extra: dict[str, Any] = {
            "rows": len(data_rows),
            "cols": len(header),
            "delimiter": delim,
            "encoding": encoding,
            "engine": "stdlib",
        }
        if truncated:
            extra["rows_truncated"] = True

        meta: dict[str, Any] = {"kind": "table", "extra": extra}

        if summary:
            try:
                rendered += "\n\n" + _pandas_summary(text, delim)
                extra["summary_engine"] = "pandas"
            except ImportError:
                from ..deps import check_dep

                hint = check_dep("csv-pandas").install_hint
                meta["warnings"] = [
                    f"summary requested but pandas is not installed "
                    f"(install with: {hint})"
                ]

        return make_artifact(text=rendered, meta=meta)
    except Exception as e:
        return error_artifact(source, ERROR_PARSE, f"Failed to parse CSV: {e}")


#: Extensions handled by this processor (overrides text.py's registration).
EXTENSIONS = (".csv", ".tsv")

#: Declared option schema (see attachments.options).
OPTIONS = (
    Option(
        name="rows",
        type="int",
        aliases=("max_rows", "limit"),
        param="max_rows",
        default=200,
        help="Maximum number of data rows rendered as text.",
        example="rows: 100",
    ),
    Option(
        name="summary",
        type="bool",
        default=False,
        help="Append a pandas-backed summary (shape, dtypes, numeric stats).",
        example="summary: true",
    ),
    Option(
        name="delimiter",
        type="str",
        aliases=("sep",),
        help="Field delimiter: a literal character or tab/comma/semicolon/pipe. "
        "Overrides sniffing.",
        example="delimiter: semicolon",
    ),
)


def register() -> None:
    """Register the csv processor and its option schema (idempotent)."""
    for ext in EXTENSIONS:
        register_processor(ext, csv_processor)
        register_options(ext, OPTIONS)


register()
