"""DSL parser for inline options in input strings (spec/dsl-grammar.md).

The DSL embeds processing options in the input string::

    source[key:value, key2:value2, ...]

This parser is a pure function ``string -> (source, options)`` and performs
**no alias resolution and no validation** — it returns the source plus raw
typed options. Mapping keys to processor parameters, alias handling, and
"did you mean" warnings are the router's job, driven by each processor's
declared option schema (see ``attachments.options``).

The normative test vectors live in ``spec/dsl-test-vectors.json``; every
implementation, in any language, must pass all of them.

Value typing (in order):
    1. Quoted (``"..."``/``'...'``) -> string, no further typing
    2. Boolean: ``true``/``false``/``yes``/``no``/``on``/``off``
       (case-insensitive; ``1`` and ``0`` are integers, not booleans)
    3. Integer: optional leading ``-``, all digits
    4. Float: digits containing exactly one ``.``
    5. Range: ``N-M`` with both sides non-negative integers -> ``(N, M)``
    6. Otherwise: string, verbatim
"""

from __future__ import annotations

import re
from typing import Any

_INT_RE = re.compile(r"-?[0-9]+")
_FLOAT_RE = re.compile(r"-?(?:[0-9]+\.[0-9]*|\.[0-9]+)")
_RANGE_RE = re.compile(r"([0-9]+)\s*-\s*([0-9]+)")
_KEY_SEPARATORS_RE = re.compile(r"[\s-]+")


def _normalize_key(key: str) -> str:
    """Normalize an option key: trim, lowercase, ``-``/spaces -> ``_``.

    Examples:
        >>> _normalize_key("Max-Rows")
        'max_rows'
        >>> _normalize_key("  max rows ")
        'max_rows'
    """
    return _KEY_SEPARATORS_RE.sub("_", key.strip().lower())


def _type_value(raw: str) -> Any:
    """Type a raw option value per the grammar's typing rules.

    Examples:
        >>> _type_value("42")
        42
        >>> _type_value("-3")
        -3
        >>> _type_value("true")
        True
        >>> _type_value("Off")
        False
        >>> _type_value("1")  # integer, NOT a boolean
        1
        >>> _type_value("1.5")
        1.5
        >>> _type_value("1-4")
        (1, 4)
        >>> _type_value('"42"')  # quoted stays string
        '42'
        >>> _type_value("Sales")
        'Sales'
    """
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    lowered = value.lower()
    if lowered in ("true", "yes", "on"):
        return True
    if lowered in ("false", "no", "off"):
        return False
    if _INT_RE.fullmatch(value):
        return int(value)
    if _FLOAT_RE.fullmatch(value):
        return float(value)
    range_match = _RANGE_RE.fullmatch(value)
    if range_match:
        return (int(range_match.group(1)), int(range_match.group(2)))
    return value


def _split_outside_quotes(text: str, separator: str) -> list[str]:
    """Split *text* on *separator*, ignoring separators inside quotes.

    Examples:
        >>> _split_outside_quotes("a: 1, b: 2", ",")
        ['a: 1', ' b: 2']
        >>> _split_outside_quotes('name: "hello, world", count: 5', ",")
        ['name: "hello, world"', ' count: 5']
    """
    parts: list[str] = []
    current: list[str] = []
    quote_char: str | None = None
    for char in text:
        if quote_char is None and char in "\"'":
            quote_char = char
        elif char == quote_char:
            quote_char = None
        elif char == separator and quote_char is None:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    parts.append("".join(current))
    return parts


def _find_colon_outside_quotes(segment: str) -> int:
    """Return the index of the first ``:`` outside quotes, or -1."""
    quote_char: str | None = None
    for i, char in enumerate(segment):
        if quote_char is None and char in "\"'":
            quote_char = char
        elif char == quote_char:
            quote_char = None
        elif char == ":" and quote_char is None:
            return i
    return -1


def parse_dsl(input: str) -> tuple[str, dict[str, Any]]:
    """Parse an input string into ``(source, raw_options)``.

    The options block is the final balanced ``[...]`` group, recognized only
    when the input ends with ``]`` and every comma-separated segment contains
    a ``:`` outside quotes. Otherwise the whole group stays in the source.
    Keys are normalized; values are typed but NOT resolved against any
    processor schema (that happens in ``attachments.options``).

    Examples:
        >>> parse_dsl("file.pdf")
        ('file.pdf', {})
        >>> parse_dsl("file.pdf[pages: 1-4]")
        ('file.pdf', {'pages': (1, 4)})
        >>> parse_dsl("data.xlsx[sheet: Sales, rows: 100]")
        ('data.xlsx', {'sheet': 'Sales', 'rows': 100})
        >>> parse_dsl("github://org/repo[branch: main]")
        ('github://org/repo', {'branch': 'main'})
        >>> parse_dsl("doc.pdf[password: a:b]")  # later colons join the value
        ('doc.pdf', {'password': 'a:b'})
        >>> parse_dsl("doc.pdf[]")  # empty block stripped
        ('doc.pdf', {})
        >>> parse_dsl("archive[backup]")  # no colon -> not an options block
        ('archive[backup]', {})
    """
    input = input.strip()
    if not input.endswith("]"):
        return input, {}

    # Find the '[' matching the final ']' (the final balanced group).
    depth = 0
    block_start = -1
    for i in range(len(input) - 1, -1, -1):
        if input[i] == "]":
            depth += 1
        elif input[i] == "[":
            depth -= 1
            if depth == 0:
                block_start = i
                break
    if block_start == -1:
        return input, {}

    source = input[:block_start].strip()
    body = input[block_start + 1 : -1]

    # An empty group `[]` is an empty options block and is stripped.
    if not body.strip():
        return source, {}

    segments = _split_outside_quotes(body, ",")
    # Trailing comma tolerated: drop one final empty segment.
    if len(segments) > 1 and not segments[-1].strip():
        segments.pop()

    # Every segment must contain ':' outside quotes, else the whole group
    # is part of the source.
    splits: list[tuple[str, str]] = []
    for segment in segments:
        colon = _find_colon_outside_quotes(segment)
        if colon == -1:
            return input, {}
        splits.append((segment[:colon], segment[colon + 1 :]))

    options: dict[str, Any] = {}
    for raw_key, raw_value in splits:
        # Duplicate keys: last occurrence wins (plain dict assignment).
        options[_normalize_key(raw_key)] = _type_value(raw_value)
    return source, options


def _format_value(value: Any) -> str:
    """Render a typed option value back to DSL text.

    Strings that would re-parse as another type (or contain delimiters)
    are quoted so that ``parse_dsl(format_dsl(...))`` round-trips.

    Examples:
        >>> _format_value(True)
        'true'
        >>> _format_value((1, 4))
        '1-4'
        >>> _format_value(300)
        '300'
        >>> _format_value("Sales")
        'Sales'
        >>> _format_value("42")
        '"42"'
        >>> _format_value("hello, world")
        '"hello, world"'
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, tuple) and len(value) == 2:
        return f"{value[0]}-{value[1]}"
    if isinstance(value, int | float):
        return str(value)
    text = str(value)
    needs_quotes = (
        text != text.strip()
        or text == ""
        or any(c in text for c in ",[]'\"")
        or _type_value(text) != text
    )
    if needs_quotes:
        quote = "'" if '"' in text else '"'
        return f"{quote}{text}{quote}"
    return text


def format_dsl(source: str, options: dict[str, Any]) -> str:
    """Format a source and raw options back into a DSL string.

    The inverse of :func:`parse_dsl` for the raw option model (canonical
    DSL keys, typed values).

    Examples:
        >>> format_dsl("file.pdf", {})
        'file.pdf'
        >>> format_dsl("file.pdf", {"pages": (1, 4), "images": True})
        'file.pdf[pages: 1-4, images: true]'
        >>> parse_dsl(format_dsl("f.csv", {"name": "a, b", "id": "42"}))
        ('f.csv', {'name': 'a, b', 'id': '42'})
    """
    if not options:
        return source
    parts = [f"{key}: {_format_value(value)}" for key, value in options.items()]
    return f"{source}[{', '.join(parts)}]"
