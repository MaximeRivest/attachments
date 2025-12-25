"""DSL parser for inline options in input strings.

Allows specifying processing options directly in the input path:

    att("report.pdf[pages: 1-4]")
    att("data.xlsx[sheet: Sales, rows: 100]")
    att("https://example.com/doc.pdf[pages: 5-10, images: true]")
    att("github://org/repo[ref: main]")

Syntax:
    path[key: value, key2: value2, ...]

Value types:
    - Integers: "100", "42"
    - Booleans: "true", "false", "yes", "no"
    - Ranges: "1-4" (for page ranges)
    - Strings: anything else (quotes optional)
"""

from __future__ import annotations

import re
from typing import Any

# Aliases for common option keys
# Maps DSL key -> processor kwarg(s)
KEY_ALIASES: dict[str, str | tuple[str, str]] = {
    # PDF options
    "pages": ("page_start", "page_end"),  # "1-4" → page_start=0, page_end=4
    "page": ("page_start", "page_end"),
    "password": "password",
    "pw": "password",
    "dpi": "images_dpi",
    "images": "render_images",
    "render": "render_images",
    # Excel options
    "sheet": "sheet",
    "rows": "max_rows",
    "max_rows": "max_rows",
    # GitHub options
    "branch": "ref",
    "ref": "ref",
    "tag": "ref",
    # Generic
    "start": "page_start",
    "end": "page_end",
}


def _parse_value(value: str) -> Any:
    """Parse a value string into appropriate Python type."""
    value = value.strip()

    # Remove surrounding quotes if present
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]

    # Boolean
    if value.lower() in ("true", "yes", "on", "1"):
        return True
    if value.lower() in ("false", "no", "off", "0"):
        return False

    # Integer
    if value.isdigit() or (value.startswith("-") and value[1:].isdigit()):
        return int(value)

    # Float
    try:
        if "." in value:
            return float(value)
    except ValueError:
        pass

    # Range (e.g., "1-4", "5-10")
    range_match = re.match(r"^(\d+)\s*-\s*(\d+)$", value)
    if range_match:
        return (int(range_match.group(1)), int(range_match.group(2)))

    # String (default)
    return value


def _expand_option(key: str, value: Any) -> dict[str, Any]:
    """Expand a DSL key-value pair into processor kwargs."""
    # Normalize key
    key_lower = key.lower().replace("-", "_").replace(" ", "_")

    # Check for alias
    alias = KEY_ALIASES.get(key_lower, key_lower)

    # Handle range values for page options
    if isinstance(alias, tuple) and isinstance(value, tuple):
        # e.g., "pages: 1-4" → page_start=0, page_end=4
        start_key, end_key = alias
        start_val, end_val = value
        # Convert to 0-based indexing (user says "1-4", means pages 1,2,3,4)
        return {start_key: start_val - 1, end_key: end_val}

    # Handle single value for range keys
    if isinstance(alias, tuple):
        # e.g., "page: 3" → just that page
        start_key, end_key = alias
        if isinstance(value, int):
            return {start_key: value - 1, end_key: value}
        return {}  # Can't handle non-int for page

    # Simple key-value
    return {alias: value}


def parse_dsl(input: str) -> tuple[str, dict[str, Any]]:
    """Parse input string with optional DSL options.

    Args:
        input: Input string, optionally with [key: value, ...] suffix

    Returns:
        Tuple of (clean_path, options_dict)

    Examples:
        >>> parse_dsl("file.pdf")
        ('file.pdf', {})

        >>> parse_dsl("file.pdf[pages: 1-4]")
        ('file.pdf', {'page_start': 0, 'page_end': 4})

        >>> parse_dsl("data.xlsx[sheet: Sales, rows: 100]")
        ('data.xlsx', {'sheet': 'Sales', 'max_rows': 100})

        >>> parse_dsl("doc.pdf[images: true, dpi: 300]")
        ('doc.pdf', {'render_images': True, 'images_dpi': 300})
    """
    input = input.strip()

    # Check for DSL suffix
    if "[" not in input or not input.endswith("]"):
        return input, {}

    # Find the last '[' that starts the options
    # Be careful with URLs that might contain [ ]
    bracket_depth = 0
    options_start = -1

    for i in range(len(input) - 1, -1, -1):
        if input[i] == "]":
            bracket_depth += 1
        elif input[i] == "[":
            bracket_depth -= 1
            if bracket_depth == 0:
                options_start = i
                break

    if options_start == -1:
        return input, {}

    # Split path and options
    path = input[:options_start].strip()
    options_str = input[options_start + 1 : -1].strip()

    if not options_str:
        return path, {}

    # Parse options
    options: dict[str, Any] = {}

    # Split by comma, but respect quoted strings
    parts = _split_options(options_str)

    for part in parts:
        part = part.strip()
        if not part:
            continue

        # Split key: value
        if ":" in part:
            key, _, value = part.partition(":")
            key = key.strip()
            value = value.strip()

            parsed_value = _parse_value(value)
            expanded = _expand_option(key, parsed_value)
            options.update(expanded)

    return path, options


def _split_options(options_str: str) -> list[str]:
    """Split options string by comma, respecting quotes."""
    parts = []
    current = []
    in_quotes = False
    quote_char = None

    for char in options_str:
        if char in ('"', "'") and not in_quotes:
            in_quotes = True
            quote_char = char
            current.append(char)
        elif char == quote_char and in_quotes:
            in_quotes = False
            quote_char = None
            current.append(char)
        elif char == "," and not in_quotes:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)

    if current:
        parts.append("".join(current))

    return parts


def format_dsl(path: str, options: dict[str, Any]) -> str:
    """Format a path and options back into DSL string.

    Args:
        path: The file path or URL
        options: Options dictionary

    Returns:
        DSL-formatted string

    Example:
        >>> format_dsl("file.pdf", {"page_start": 0, "page_end": 4})
        'file.pdf[page_start: 0, page_end: 4]'
    """
    if not options:
        return path

    parts = []
    for key, value in options.items():
        if isinstance(value, bool):
            value_str = "true" if value else "false"
        elif isinstance(value, str) and ("," in value or ":" in value):
            value_str = f'"{value}"'
        else:
            value_str = str(value)
        parts.append(f"{key}: {value_str}")

    return f"{path}[{', '.join(parts)}]"
