"""Declared option schemas for processors and sources.

Options belong to processors, not to a central table: each processor
declares its option schema (name, type, aliases, default, help, example)
next to its registration, and everything else — validation, "did you mean"
warnings, ``att.options()`` runtime discovery, the ``dsl_schema()`` export
for editors — is generated from those declarations.

The DSL parser (``attachments.dsl``) returns raw typed options; this module
resolves them against a schema into processor kwargs. Unknown keys never
fail silently: they produce a human-readable warning and are dropped.

Example::

    from attachments import Option, register_options

    register_options(
        ".myf",
        (Option("depth", "int", help="How deep to parse.", example="depth: 3"),),
    )
"""

from __future__ import annotations

import difflib
import json
import logging
import re
import textwrap
from dataclasses import dataclass
from typing import Any

log = logging.getLogger("attachments.options")

#: Valid values for :attr:`Option.type`.
OPTION_TYPES = (
    "str",
    "int",
    "float",
    "bool",
    "pages",
    "bool_or_auto",
    "str_or_int",
)

_PAGE_RANGE_RE = re.compile(r"\s*([0-9]+)\s*-\s*([0-9]+)\s*")
_PAGE_SINGLE_RE = re.compile(r"\s*([0-9]+)\s*")
_BOOL_WORDS = {
    "true": True,
    "yes": True,
    "on": True,
    "false": False,
    "no": False,
    "off": False,
}


@dataclass(frozen=True)
class Option:
    """A single declared option for a processor or source.

    Attributes:
        name: Canonical DSL key (e.g. ``"pages"``).
        type: One of :data:`OPTION_TYPES`.
        aliases: Alternative DSL keys (e.g. ``("page",)``).
        param: Processor kwarg name; ``None`` means same as ``name``.
            Ignored for type ``"pages"`` — the resolver always emits
            ``page_start``/``page_end``. The param also acts as a hidden
            alias so kwargs like ``max_rows=`` keep working.
        default: Default value (informational, for docs/schema export).
        help: One-line human description.
        example: A valid DSL usage snippet (e.g. ``"pages: 1-4"``).

    Examples:
        >>> Option("dpi", "int", param="images_dpi", default=200)
        Option(name='dpi', type='int', aliases=(), param='images_dpi', \
default=200, help='', example='')
        >>> Option("dpi", "color")
        Traceback (most recent call last):
        ...
        ValueError: Option 'dpi' has invalid type 'color' (expected one of: \
str, int, float, bool, pages, bool_or_auto, str_or_int)
    """

    name: str
    type: str
    aliases: tuple[str, ...] = ()
    param: str | None = None
    default: Any = None
    help: str = ""
    example: str = ""

    def __post_init__(self) -> None:
        if self.type not in OPTION_TYPES:
            raise ValueError(
                f"Option {self.name!r} has invalid type {self.type!r} "
                f"(expected one of: {', '.join(OPTION_TYPES)})"
            )


# ---------------------------------------------------------------------------
# Registries (mirroring the processor registry in attachments._processors)
# ---------------------------------------------------------------------------

#: Option schemas keyed like the processor registry (".pdf", "__text__").
option_schemas: dict[str, tuple[Option, ...]] = {}

#: Option schemas for sources, keyed by URL prefix ("github://").
source_option_schemas: dict[str, tuple[Option, ...]] = {}

# Snapshots of the built-in schemas (populated at import time; additive so
# both processors/__init__.py and unpack.py can snapshot their built-ins).
_default_option_schemas: dict[str, tuple[Option, ...]] | None = None
_default_source_option_schemas: dict[str, tuple[Option, ...]] | None = None


def _normalize_key(key: str) -> str:
    """Normalize a schema key like the processor registry does.

    Source prefixes (containing ``://``) and sentinel keys (``__text__``)
    pass through unchanged; extensions get a leading dot and lowercase.

    Examples:
        >>> _normalize_key("PDF")
        '.pdf'
        >>> _normalize_key("__text__")
        '__text__'
        >>> _normalize_key("github://")
        'github://'
    """
    k = key.strip()
    if k.startswith("__") or "://" in k:
        return k
    if not k.startswith("."):
        k = "." + k
    return k.lower()


def register_options(key: str, options: tuple[Option, ...]) -> None:
    """Register the option schema for a processor key or source prefix.

    Keys containing ``://`` go to :data:`source_option_schemas`; everything
    else is normalized like a processor extension.

    Examples:
        >>> register_options(".demo", (Option("depth", "int"),))
        >>> get_options(".demo")[0].name
        'depth'
        >>> reset_options()  # clean up the example registration
    """
    normalized = _normalize_key(key)
    target = source_option_schemas if "://" in normalized else option_schemas
    target[normalized] = tuple(options)


def get_options(key: str) -> tuple[Option, ...]:
    """Return the declared schema for *key*, or ``()`` when none exists.

    Examples:
        >>> any(o.name == "pages" for o in get_options(".pdf"))
        True
        >>> get_options(".unknown-ext")
        ()
    """
    normalized = _normalize_key(key)
    if "://" in normalized:
        return source_option_schemas.get(normalized, ())
    return option_schemas.get(normalized, ())


def get_option_schemas_copy() -> dict[str, tuple[Option, ...]]:
    """Return a shallow copy of both registries merged into one dict.

    Extension keys and source prefixes never collide, so a single dict is
    safe. Useful for isolated registries in tests.
    """
    merged = dict(option_schemas)
    merged.update(source_option_schemas)
    return merged


def snapshot_option_defaults() -> None:
    """Capture the current schemas as the built-in defaults.

    Called at import time by ``processors/__init__.py`` (after the built-in
    processors register their schemas) and by ``unpack.py`` (after the
    built-in source schemas register). Additive: each call merges new keys
    into the snapshot without overwriting earlier ones.
    """
    global _default_option_schemas, _default_source_option_schemas
    if _default_option_schemas is None:
        _default_option_schemas = dict(option_schemas)
    else:
        for key, schema in option_schemas.items():
            _default_option_schemas.setdefault(key, schema)
    if _default_source_option_schemas is None:
        _default_source_option_schemas = dict(source_option_schemas)
    else:
        for key, schema in source_option_schemas.items():
            _default_source_option_schemas.setdefault(key, schema)


def reset_options() -> None:
    """Reset both schema registries to the built-in defaults.

    Mirrors ``processors.reset_processors`` (which also calls this) so
    custom schemas registered in tests don't leak.
    """
    if _default_option_schemas is not None:
        option_schemas.clear()
        option_schemas.update(_default_option_schemas)
    if _default_source_option_schemas is not None:
        source_option_schemas.clear()
        source_option_schemas.update(_default_source_option_schemas)


# ---------------------------------------------------------------------------
# Resolution: raw DSL/kwargs options -> processor kwargs + warnings
# ---------------------------------------------------------------------------


class _CoercionError(Exception):
    """Internal: a raw value does not fit the declared option type."""

    def __init__(self, expected: str):
        self.expected = expected
        super().__init__(expected)


def _coerce_pages(value: Any) -> tuple[int, int]:
    """Coerce a pages value to a 0-based ``(page_start, page_end)`` pair."""
    expected = "a 1-based page number or range like '1-4'"
    if isinstance(value, bool):
        raise _CoercionError(expected)
    if isinstance(value, int):
        if value < 1:
            raise _CoercionError(expected)
        return (value - 1, value)
    if isinstance(value, tuple | list) and len(value) == 2:
        start, end = value
        if (
            isinstance(start, int)
            and isinstance(end, int)
            and not isinstance(start, bool)
            and not isinstance(end, bool)
            and start >= 1
        ):
            return (start - 1, end)
        raise _CoercionError(expected)
    if isinstance(value, str):
        match = _PAGE_RANGE_RE.fullmatch(value)
        if match:
            start, end = int(match.group(1)), int(match.group(2))
            if start < 1:
                raise _CoercionError(expected)
            return (start - 1, end)
        match = _PAGE_SINGLE_RE.fullmatch(value)
        if match:
            page = int(match.group(1))
            if page < 1:
                raise _CoercionError(expected)
            return (page - 1, page)
        if "," in value:
            raise _CoercionError(
                "a single page or range — page lists like '1,3-5' are not supported yet"
            )
    raise _CoercionError(expected)


def _coerce(option: Option, value: Any) -> Any:
    """Coerce *value* to the option's declared type, or raise."""
    if option.type == "pages":
        return _coerce_pages(value)
    if option.type == "str":
        if isinstance(value, bool):
            return "true" if value else "false"
        return value if isinstance(value, str) else str(value)
    if option.type == "int":
        if isinstance(value, bool):
            raise _CoercionError("an integer")
        if isinstance(value, int):
            return value
        if isinstance(value, str) and re.fullmatch(r"-?[0-9]+", value.strip()):
            return int(value)
        raise _CoercionError("an integer")
    if option.type == "float":
        if isinstance(value, bool):
            raise _CoercionError("a number")
        if isinstance(value, int | float):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError as exc:
                raise _CoercionError("a number") from exc
        raise _CoercionError("a number")
    if option.type == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.strip().lower() in _BOOL_WORDS:
            return _BOOL_WORDS[value.strip().lower()]
        raise _CoercionError("a boolean (true/false)")
    if option.type == "bool_or_auto":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in ("auto", "always"):
                return lowered
            if lowered in _BOOL_WORDS:
                return _BOOL_WORDS[lowered]
        raise _CoercionError("a boolean, 'auto', or 'always'")
    if option.type == "str_or_int":
        if isinstance(value, bool):
            raise _CoercionError("a string or integer")
        if isinstance(value, str | int):
            return value
        raise _CoercionError("a string or integer")
    raise _CoercionError(f"a value of type {option.type!r}")  # pragma: no cover


def resolve_options(
    schema: tuple[Option, ...],
    raw: dict[str, Any],
    *,
    context: str,
) -> tuple[dict[str, Any], list[str]]:
    """Resolve raw DSL/kwargs options against a declared schema.

    Each raw key is matched against canonical names, aliases, and param
    names (the param acts as a hidden alias). Matched values are coerced to
    the declared type; ``pages`` emits 0-based ``page_start``/``page_end``.
    Unknown keys and coercion failures produce a warning and are dropped —
    resolution never raises. Later raw keys win on collision, so merging
    explicit kwargs after DSL options makes kwargs override the DSL.

    Args:
        schema: The declared options (may be empty).
        raw: Raw options from the DSL parser and/or explicit kwargs.
        context: Human-readable owner for warnings (e.g. ``".xlsx"``).

    Returns:
        ``(kwargs, warnings)`` — processor kwargs plus human-readable
        warnings (also emitted via ``log.warning``).

    Examples:
        >>> schema = (
        ...     Option("sheet", "str_or_int"),
        ...     Option("rows", "int", aliases=("max_rows",), param="max_rows"),
        ... )
        >>> resolve_options(schema, {"sheet": "Sales", "rows": 50}, context=".xlsx")
        ({'sheet': 'Sales', 'max_rows': 50}, [])
        >>> kwargs, warnings = resolve_options(schema, {"sheets": 0}, context=".xlsx")
        >>> kwargs
        {}
        >>> warnings
        ["Unknown option 'sheets' for .xlsx — did you mean 'sheet'?"]
    """
    lookup: dict[str, Option] = {}
    for option in schema:
        lookup.setdefault(option.name, option)
        for alias in option.aliases:
            lookup.setdefault(alias, option)
        if option.param:
            lookup.setdefault(option.param, option)
    suggestible = sorted(
        {o.name for o in schema} | {a for o in schema for a in o.aliases}
    )

    kwargs: dict[str, Any] = {}
    warnings: list[str] = []
    for key, value in raw.items():
        option = lookup.get(key)
        if option is None:
            message = f"Unknown option '{key}' for {context}"
            close = difflib.get_close_matches(key, suggestible, n=1)
            if close:
                message += f" — did you mean '{close[0]}'?"
            warnings.append(message)
            continue
        try:
            coerced = _coerce(option, value)
        except _CoercionError as exc:
            message = (
                f"Invalid value for option '{option.name}' on {context}: "
                f"expected {exc.expected}, got {value!r}"
            )
            if option.example:
                message += f" (e.g. [{option.example}])"
            warnings.append(message)
            continue
        if option.type == "pages":
            kwargs["page_start"], kwargs["page_end"] = coerced
        else:
            kwargs[option.param or option.name] = coerced

    for warning in warnings:
        log.warning("%s", warning)
    return kwargs, warnings


# ---------------------------------------------------------------------------
# Schema export & runtime discovery
# ---------------------------------------------------------------------------


def _option_as_dict(option: Option) -> dict[str, Any]:
    """Export one declared option as a JSON-serializable dict."""
    return {
        "name": option.name,
        "type": option.type,
        "aliases": list(option.aliases),
        "param": option.param,
        "default": option.default,
        "help": option.help,
        "example": option.example,
    }


def dsl_schema() -> dict[str, Any]:
    """Export every declared schema as a JSON-serializable dict.

    This is the future ``dsl-schema.json`` consumed by editor tooling.

    Examples:
        >>> schema = dsl_schema()
        >>> schema["version"]
        1
        >>> sorted(schema) == ["processors", "sources", "version"]
        True
        >>> any(o["name"] == "pages" for o in schema["processors"][".pdf"])
        True
        >>> [o["name"] for o in schema["sources"]["github://"]]
        ['ref']
    """
    return {
        "version": 1,
        "processors": {
            key: [_option_as_dict(o) for o in schema]
            for key, schema in sorted(option_schemas.items())
        },
        "sources": {
            key: [_option_as_dict(o) for o in schema]
            for key, schema in sorted(source_option_schemas.items())
        },
    }


#: Column headers for the plain-text option tables (repr of ``options()``).
_TABLE_COLUMNS = ("Option", "Type", "Aliases", "Default", "Example")

#: Target line width for the plain-text option tables.
_TABLE_WIDTH = 88


def _format_option_table(option_dicts: list[dict[str, Any]], indent: str = "") -> str:
    """Render option dicts as an aligned plain-text table (~88 cols).

    Columns: Option | Type | Aliases | Default | Example — with the help
    text as a wrapped Description column at the end.

    Examples:
        >>> print(_format_option_table([]))
        (no options declared)
    """
    if not option_dicts:
        return f"{indent}(no options declared)"
    rows = [
        (
            option["name"],
            option["type"],
            ", ".join(option["aliases"]) or "—",
            "—" if option["default"] is None else json.dumps(option["default"]),
            option["example"] or "—",
            " ".join(str(option["help"]).split()),
        )
        for option in option_dicts
    ]
    widths = [
        max(len(header), *(len(row[i]) for row in rows))
        for i, header in enumerate(_TABLE_COLUMNS)
    ]
    desc_start = len(indent) + sum(widths) + 2 * len(widths)
    desc_width = max(20, _TABLE_WIDTH - desc_start)
    lines: list[str] = []
    for cells in [(*_TABLE_COLUMNS, "Description"), *rows]:
        prefix = indent + "".join(
            cells[i].ljust(widths[i] + 2) for i in range(len(widths))
        )
        wrapped = textwrap.wrap(cells[5], width=desc_width) or [""]
        lines.append((prefix + wrapped[0]).rstrip())
        lines.extend(" " * desc_start + cont for cont in wrapped[1:])
    return "\n".join(lines)


def _group_by_schema(
    entries: dict[str, list[dict[str, Any]]],
) -> list[tuple[list[str], list[dict[str, Any]]]]:
    """Group keys whose exported option schemas are identical (sorted)."""
    keys_by_fingerprint: dict[str, list[str]] = {}
    options_by_fingerprint: dict[str, list[dict[str, Any]]] = {}
    for key in sorted(entries):
        fingerprint = json.dumps(entries[key], sort_keys=True)
        keys_by_fingerprint.setdefault(fingerprint, []).append(key)
        options_by_fingerprint[fingerprint] = entries[key]
    groups = [
        (keys, options_by_fingerprint[fingerprint])
        for fingerprint, keys in keys_by_fingerprint.items()
    ]
    groups.sort(key=lambda group: group[0][0])
    return groups


class _OptionList(list):
    """Per-key option dicts whose repr is an aligned plain-text table.

    Same data as a plain list — iteration, indexing, and ``json.dumps``
    are unchanged; only ``__repr__`` differs (REPL delight).
    """

    def __repr__(self) -> str:
        return _format_option_table(self)


class _OptionCatalog(dict):
    """Full schema export whose repr renders one table per schema group.

    Same data as the plain :func:`dsl_schema` dict — ``json.dumps`` and
    key access are unchanged; only ``__repr__`` differs.
    """

    def __repr__(self) -> str:
        lines = [f"DSL options (schema version {self.get('version')})"]
        for section, title in (("processors", "Processors"), ("sources", "Sources")):
            entries = self.get(section) or {}
            if not entries:
                continue
            lines += ["", title, ""]
            no_option_keys: list[str] = []
            for keys, option_dicts in _group_by_schema(entries):
                if not option_dicts:
                    no_option_keys.extend(keys)
                    continue
                lines.append(", ".join(keys))
                lines.append(_format_option_table(option_dicts, indent="  "))
                lines.append("")
            if no_option_keys:
                lines.append(
                    "\n".join(
                        textwrap.wrap(
                            "No options: " + ", ".join(no_option_keys),
                            width=_TABLE_WIDTH,
                            subsequent_indent="  ",
                        )
                    )
                )
                lines.append("")
        while lines and not lines[-1]:
            lines.pop()
        return "\n".join(lines)


def options(key: str | None = None) -> dict[str, Any] | list[dict[str, Any]]:
    """Runtime discovery of declared options (also exposed as ``att.options``).

    Returns the same data as always, wrapped in repr-friendly subclasses:
    a list subclass per key, a dict subclass for the full catalog. Both
    print aligned plain-text tables in a REPL while staying 100%
    JSON-serializable plain data (:func:`dsl_schema` itself stays a plain
    dict — it feeds asset generation).

    Args:
        key: A processor extension (``".pdf"``), sentinel (``"__text__"``),
            or source prefix (``"github://"``). ``None`` returns the full
            :func:`dsl_schema` export.

    Returns:
        A list of option dicts for one key, or the full schema dict.

    Examples:
        >>> [o["name"] for o in options(".pdf")]
        ['pages', 'password', 'images', 'dpi', 'max_pages']
        >>> options(".unknown-ext")
        (no options declared)
        >>> options()["version"]
        1
        >>> register_options(
        ...     ".demo", (Option("depth", "int", help="How deep.", example="depth: 2"),)
        ... )
        >>> options(".demo")
        Option  Type  Aliases  Default  Example   Description
        depth   int   —        —        depth: 2  How deep.
        >>> reset_options()  # clean up the example registration
        >>> import json
        >>> json.loads(json.dumps(options(".pdf")))[0]["name"]
        'pages'
    """
    if key is None:
        return _OptionCatalog(dsl_schema())
    return _OptionList(_option_as_dict(o) for o in get_options(key))
