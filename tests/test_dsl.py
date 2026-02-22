"""
Tests for the DSL (Domain Specific Language) parser.

=============================================================================
TEST GUIDELINES FOR DSL
=============================================================================

GOOD tests for DSL parsing:
    - Test each value type: integers, booleans, ranges, strings, quoted strings
    - Test all key aliases (pages/page, rows/max_rows, etc.)
    - Test edge cases: empty options, whitespace, special characters
    - Test malformed input: unbalanced brackets, missing colons
    - Test that explicit kwargs override DSL options (in core.py)

BAD tests for DSL:
    - Testing actual file processing (that's test_core.py)
    - Duplicating doctest examples exactly (doctests already cover basic cases)
    - Testing internal helper functions if public API covers them

COVERAGE NOTES:
    - Doctests cover happy paths and basic usage
    - These tests cover edge cases, errors, and complex scenarios

=============================================================================
"""

from __future__ import annotations

import pytest

from attachments.dsl import (
    KEY_ALIASES,
    _expand_option,
    _parse_value,
    _split_options,
    format_dsl,
    parse_dsl,
)


class TestParseValue:
    """Tests for _parse_value - converts string values to Python types."""

    def test_integer_positive(self):
        assert _parse_value("42") == 42
        assert _parse_value("0") == 0
        assert _parse_value("999999") == 999999

    def test_integer_negative(self):
        assert _parse_value("-1") == -1
        assert _parse_value("-100") == -100

    def test_boolean_true_variants(self):
        for val in ("true", "True", "TRUE", "yes", "Yes", "on", "ON", "1"):
            assert _parse_value(val) is True, f"Expected True for {val!r}"

    def test_boolean_false_variants(self):
        for val in ("false", "False", "FALSE", "no", "No", "off", "OFF", "0"):
            assert _parse_value(val) is False, f"Expected False for {val!r}"

    def test_range_simple(self):
        assert _parse_value("1-4") == (1, 4)
        assert _parse_value("10-20") == (10, 20)

    def test_range_with_whitespace(self):
        assert _parse_value("1 - 4") == (1, 4)
        assert _parse_value("5  -  10") == (5, 10)

    def test_range_same_numbers(self):
        """A range like 5-5 means just page 5."""
        assert _parse_value("5-5") == (5, 5)

    def test_float(self):
        assert _parse_value("3.14") == 3.14
        assert _parse_value("0.5") == 0.5

    def test_quoted_string_double(self):
        assert _parse_value('"hello world"') == "hello world"
        assert _parse_value('"with, comma"') == "with, comma"

    def test_quoted_string_single(self):
        assert _parse_value("'hello world'") == "hello world"

    def test_unquoted_string(self):
        assert _parse_value("Sales") == "Sales"
        assert _parse_value("my-sheet-name") == "my-sheet-name"

    def test_whitespace_stripped(self):
        assert _parse_value("  42  ") == 42
        assert _parse_value("  true  ") is True
        assert _parse_value("  Sales  ") == "Sales"


class TestExpandOption:
    """Tests for _expand_option - converts DSL keys to processor kwargs."""

    def test_pages_range(self):
        """pages: 1-4 becomes page_start=0, page_end=4 (0-indexed start)."""
        result = _expand_option("pages", (1, 4))
        assert result == {"page_start": 0, "page_end": 4}

    def test_page_single(self):
        """page: 3 means just page 3 (pages 3-3)."""
        result = _expand_option("page", 3)
        assert result == {"page_start": 2, "page_end": 3}

    def test_rows_alias(self):
        result = _expand_option("rows", 100)
        assert result == {"max_rows": 100}

    def test_dpi_alias(self):
        result = _expand_option("dpi", 300)
        assert result == {"images_dpi": 300}

    def test_images_alias(self):
        result = _expand_option("images", True)
        assert result == {"render_images": True}

    def test_branch_to_ref(self):
        result = _expand_option("branch", "main")
        assert result == {"ref": "main"}

    def test_password_passthrough(self):
        result = _expand_option("password", "secret")
        assert result == {"password": "secret"}

    def test_unknown_key_passthrough(self):
        """Unknown keys pass through unchanged."""
        result = _expand_option("custom_option", "value")
        assert result == {"custom_option": "value"}

    def test_key_normalization(self):
        """Keys are normalized: lowercase, underscores."""
        result = _expand_option("MAX-ROWS", 50)
        assert result == {"max_rows": 50}


class TestSplitOptions:
    """Tests for _split_options - splits on comma respecting quotes."""

    def test_simple_split(self):
        parts = _split_options("a: 1, b: 2")
        assert len(parts) == 2

    def test_quoted_comma(self):
        """Commas inside quotes should not split."""
        parts = _split_options('name: "hello, world", count: 5')
        assert len(parts) == 2
        assert '"hello, world"' in parts[0]

    def test_single_option(self):
        parts = _split_options("pages: 1-4")
        assert len(parts) == 1


class TestParseDsl:
    """Tests for parse_dsl - the main DSL parser."""

    def test_no_options(self):
        path, opts = parse_dsl("document.pdf")
        assert path == "document.pdf"
        assert opts == {}

    def test_empty_brackets(self):
        path, opts = parse_dsl("file.pdf[]")
        assert path == "file.pdf"
        assert opts == {}

    def test_single_option(self):
        path, opts = parse_dsl("file.pdf[pages: 1-4]")
        assert path == "file.pdf"
        assert opts == {"page_start": 0, "page_end": 4}

    def test_multiple_options(self):
        path, opts = parse_dsl("doc.pdf[pages: 1-4, dpi: 300, images: true]")
        assert path == "doc.pdf"
        assert opts["page_start"] == 0
        assert opts["page_end"] == 4
        assert opts["images_dpi"] == 300
        assert opts["render_images"] is True

    def test_url_with_options(self):
        path, opts = parse_dsl("https://example.com/doc.pdf[pages: 1-5]")
        assert path == "https://example.com/doc.pdf"
        assert opts == {"page_start": 0, "page_end": 5}

    def test_github_with_branch(self):
        path, opts = parse_dsl("github://owner/repo[branch: develop]")
        assert path == "github://owner/repo"
        assert opts == {"ref": "develop"}

    def test_xlsx_options(self):
        path, opts = parse_dsl("data.xlsx[sheet: Sales, rows: 50]")
        assert path == "data.xlsx"
        assert opts == {"sheet": "Sales", "max_rows": 50}

    def test_password_option(self):
        path, opts = parse_dsl("encrypted.pdf[password: secret123]")
        assert path == "encrypted.pdf"
        assert opts == {"password": "secret123"}

    def test_whitespace_handling(self):
        path, opts = parse_dsl("  file.pdf[ pages : 1-4 , dpi : 300 ]  ")
        assert path == "file.pdf"
        assert opts["page_start"] == 0
        assert opts["images_dpi"] == 300

    def test_nested_brackets_in_url(self):
        """URLs with brackets (rare but possible) should work."""
        # This is an edge case - we take the LAST balanced [] as options
        path, opts = parse_dsl("file[weird].pdf[pages: 1]")
        assert path == "file[weird].pdf"
        assert opts == {"page_start": 0, "page_end": 1}

    def test_no_closing_bracket(self):
        """Unbalanced brackets should return as-is."""
        path, opts = parse_dsl("file.pdf[pages: 1-4")
        assert path == "file.pdf[pages: 1-4"
        assert opts == {}

    def test_only_opening_bracket(self):
        path, opts = parse_dsl("file[.pdf")
        assert path == "file[.pdf"
        assert opts == {}


class TestFormatDsl:
    """Tests for format_dsl - converts back to DSL string."""

    def test_no_options(self):
        result = format_dsl("file.pdf", {})
        assert result == "file.pdf"

    def test_single_option(self):
        result = format_dsl("file.pdf", {"page_start": 0})
        assert result == "file.pdf[page_start: 0]"

    def test_boolean_formatting(self):
        result = format_dsl("file.pdf", {"render_images": True})
        assert "true" in result

        result = format_dsl("file.pdf", {"render_images": False})
        assert "false" in result

    def test_string_with_special_chars(self):
        """Strings with comma or colon should be quoted."""
        result = format_dsl("file.xlsx", {"sheet": "Sales, 2024"})
        assert '"Sales, 2024"' in result


class TestKeyAliases:
    """Verify all documented key aliases exist."""

    def test_page_aliases_exist(self):
        assert "pages" in KEY_ALIASES
        assert "page" in KEY_ALIASES

    def test_sheet_alias_exists(self):
        assert "sheet" in KEY_ALIASES

    def test_rows_alias_exists(self):
        assert "rows" in KEY_ALIASES
        assert "max_rows" in KEY_ALIASES

    def test_branch_aliases_exist(self):
        assert "branch" in KEY_ALIASES
        assert "ref" in KEY_ALIASES
        assert "tag" in KEY_ALIASES

    def test_password_aliases_exist(self):
        assert "password" in KEY_ALIASES
        assert "pw" in KEY_ALIASES


class TestRoundTrip:
    """Test that parse -> format -> parse gives consistent results."""

    @pytest.mark.parametrize(
        "original",
        [
            "file.pdf[pages: 1-4]",
            "data.xlsx[sheet: Sales]",
            "doc.pdf[dpi: 300]",
        ],
    )
    def test_roundtrip_consistency(self, original: str):
        """Parsing and re-formatting should preserve semantics."""
        path1, opts1 = parse_dsl(original)
        formatted = format_dsl(path1, opts1)
        path2, opts2 = parse_dsl(formatted)

        assert path1 == path2
        assert opts1 == opts2
