"""One-screen interactive overview, attached as ``att.help`` (att.help()).

Like the ``help`` builtin, :func:`att_help` PRINTS and returns ``None``.
It reads the LIVE processor registry (so third-party processors show up),
imports nothing heavy, and never touches the network.
"""

from __future__ import annotations

#: Processor module basename -> human group label (live registry grouping).
_GROUP_BY_MODULE = {
    "text": "text/code",
    "pdf": "pdf",
    "xlsx": "office",
    "docx": "office",
    "pptx": "office",
    "html": "html",
    "image": "images",
}

#: Preferred group print order; unknown groups follow alphabetically.
_GROUP_ORDER = ("text/code", "pdf", "office", "html", "images")


def _format_groups() -> list[str]:
    """Group registered extensions by processor module, one line per group.

    Examples:
        >>> lines = _format_groups()
        >>> any(line.startswith("pdf") and ".pdf" in line for line in lines)
        True
        >>> any(line.startswith("office") and ".xlsx" in line for line in lines)
        True
    """
    from ._processors import processors

    groups: dict[str, list[str]] = {}
    for key, proc in processors.items():
        if key.startswith("__"):
            continue  # sentinel keys like __text__ (text heuristic fallback)
        module = getattr(proc, "__module__", "").rsplit(".", 1)[-1]
        label = _GROUP_BY_MODULE.get(module, module or "other")
        groups.setdefault(label, []).append(key)
    ordered = [g for g in _GROUP_ORDER if g in groups]
    ordered += sorted(g for g in groups if g not in _GROUP_ORDER)
    width = max(len(g) for g in ordered) if ordered else 0
    return [
        f"{label.ljust(width)}  {' '.join(sorted(groups[label]))}" for label in ordered
    ]


def att_help() -> None:
    """Print a one-screen overview of attachments (returns None, like help()).

    Examples:
        >>> att_help()  # doctest: +ELLIPSIS
        attachments ... — turn anything into LLM-ready artifacts
        ...
    """
    from . import __version__
    from ._unpack import extra_unpack_handlers

    sources = "local files, directories, zip/tar archives, http(s)://, github://"
    extra = sorted(prefix for prefix in extra_unpack_handlers)
    if extra:
        sources += ", " + ", ".join(extra)

    lines = [
        f"attachments {__version__} — turn anything into LLM-ready artifacts",
        "",
        "Formats (live registry):",
        *(f"  {line}" for line in _format_groups()),
        "  (plus: anything that sniffs as text)",
        "",
        f"Sources: {sources}",
        "",
        "Try:",
        '  a = att("report.pdf[pages: 1-4, images: true]")  # DSL options inline',
        '  a.claude("Summarize.")          # Claude messages (a.openai(...) too)',
        "  a.chunk(max_chars=4000)         # segment-aware RAG chunks",
        "",
        "More:",
        "  att.options('.pdf')   options for one processor (att.options() = all)",
        "  docs/dsl-options.md   generated cheatsheet",
        "  spec/                 the binding IR contract & DSL grammar",
    ]
    print("\n".join(lines))
