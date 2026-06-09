"""
Tests for the DSL parser (spec/dsl-grammar.md).

=============================================================================
TEST GUIDELINES FOR DSL
=============================================================================

GOOD tests for DSL parsing:
    - Test each value type: integers, booleans, ranges, strings, quoted strings
    - Test recognition rules (final balanced group, segments without colons)
    - Test edge cases: empty options, whitespace, duplicate keys, trailing comma
    - Test malformed input: unbalanced brackets, missing colons
    - Round-trip with format_dsl

BAD tests for DSL:
    - Testing alias resolution or option semantics (that's test_options.py —
      the parser returns RAW typed options, no aliases, no validation)
    - Testing actual file processing (that's test_core.py)
    - Duplicating the normative vectors (tests/test_dsl_vectors.py runs all
      of spec/dsl-test-vectors.json)

=============================================================================
"""

from __future__ import annotations

import pytest

from attachments.dsl import format_dsl, parse_dsl


class TestParseValues:
    """Value typing through the public parser (grammar typing rules)."""

    def test_integer_positive(self):
        assert parse_dsl("f[k: 42]")[1] == {"k": 42}
        assert parse_dsl("f[k: 999999]")[1] == {"k": 999999}

    def test_integer_negative(self):
        assert parse_dsl("f[k: -1]")[1] == {"k": -1}

    def test_one_and_zero_are_integers_not_booleans(self):
        """The grammar is explicit: 1/0 are integers, never booleans."""
        assert parse_dsl("f[k: 1]")[1] == {"k": 1}
        assert parse_dsl("f[k: 0]")[1] == {"k": 0}

    @pytest.mark.parametrize("word", ["true", "True", "YES", "on", "ON"])
    def test_boolean_true_words(self, word: str):
        assert parse_dsl(f"f[k: {word}]")[1] == {"k": True}

    @pytest.mark.parametrize("word", ["false", "False", "NO", "off", "Off"])
    def test_boolean_false_words(self, word: str):
        assert parse_dsl(f"f[k: {word}]")[1] == {"k": False}

    def test_float(self):
        assert parse_dsl("f[k: 1.5]")[1] == {"k": 1.5}
        assert parse_dsl("f[k: 0.5]")[1] == {"k": 0.5}

    def test_range(self):
        assert parse_dsl("f[k: 1-4]")[1] == {"k": (1, 4)}
        assert parse_dsl("f[k: 5 - 10]")[1] == {"k": (5, 10)}
        assert parse_dsl("f[k: 5-5]")[1] == {"k": (5, 5)}

    def test_quoted_strings_skip_typing(self):
        assert parse_dsl('f[k: "42"]')[1] == {"k": "42"}
        assert parse_dsl('f[k: "true"]')[1] == {"k": "true"}
        assert parse_dsl("f[k: '1-4']")[1] == {"k": "1-4"}

    def test_quoted_string_with_comma(self):
        assert parse_dsl('f[k: "hello, world", n: 5]')[1] == {
            "k": "hello, world",
            "n": 5,
        }

    def test_bare_string(self):
        assert parse_dsl("f[k: Sales]")[1] == {"k": "Sales"}

    def test_value_with_colon(self):
        """Key/value split on the FIRST colon; later colons join the value."""
        assert parse_dsl("f[password: a:b]")[1] == {"password": "a:b"}


class TestKeyNormalization:
    """Keys are trimmed, lowercased, dashes/spaces collapsed to '_'."""

    def test_dashes_and_case(self):
        assert parse_dsl("f[Max-Rows: 50]")[1] == {"max_rows": 50}

    def test_spaces(self):
        assert parse_dsl("f[max rows: 50]")[1] == {"max_rows": 50}

    def test_no_alias_resolution(self):
        """The parser returns RAW keys — aliases are the resolver's job."""
        assert parse_dsl("f[pw: x]")[1] == {"pw": "x"}
        assert parse_dsl("f[branch: main]")[1] == {"branch": "main"}
        assert parse_dsl("f[pages: 1-4]")[1] == {"pages": (1, 4)}


class TestRecognitionRules:
    """The options block is the final balanced [...] under strict rules."""

    def test_no_options(self):
        assert parse_dsl("document.pdf") == ("document.pdf", {})

    def test_empty_brackets_stripped(self):
        assert parse_dsl("file.pdf[]") == ("file.pdf", {})

    def test_duplicate_key_last_wins(self):
        assert parse_dsl("f[dpi: 100, dpi: 300]")[1] == {"dpi": 300}

    def test_trailing_comma_tolerated(self):
        assert parse_dsl("f[dpi: 300,]")[1] == {"dpi": 300}

    def test_segment_without_colon_stays_in_source(self):
        assert parse_dsl("archive[backup]") == ("archive[backup]", {})
        assert parse_dsl("weird[1].bin") == ("weird[1].bin", {})

    def test_mixed_segments_without_colon_stay_in_source(self):
        source, opts = parse_dsl("f[a: 1, b]")
        assert source == "f[a: 1, b]"
        assert opts == {}

    def test_not_ending_with_bracket(self):
        assert parse_dsl("doc[pages: 1].pdf") == ("doc[pages: 1].pdf", {})

    def test_unbalanced_brackets(self):
        assert parse_dsl("file.pdf[pages: 1-4") == ("file.pdf[pages: 1-4", {})
        assert parse_dsl("file[.pdf") == ("file[.pdf", {})

    def test_brackets_in_source_untouched(self):
        source, opts = parse_dsl("https://x.com/a[1]/b.pdf[pages: 2-3]")
        assert source == "https://x.com/a[1]/b.pdf"
        assert opts == {"pages": (2, 3)}

    def test_whitespace_everywhere(self):
        source, opts = parse_dsl("  doc.pdf[  pages :  1-4 , dpi:300 ]  ")
        assert source == "doc.pdf"
        assert opts == {"pages": (1, 4), "dpi": 300}


class TestFormatDsl:
    """format_dsl renders the raw option model back to DSL text."""

    def test_no_options(self):
        assert format_dsl("file.pdf", {}) == "file.pdf"

    def test_typed_values(self):
        result = format_dsl("doc.pdf", {"pages": (1, 4), "images": True, "dpi": 300})
        assert result == "doc.pdf[pages: 1-4, images: true, dpi: 300]"

    def test_string_needing_quotes(self):
        assert '"Sales, 2024"' in format_dsl("f.xlsx", {"sheet": "Sales, 2024"})

    def test_string_that_would_retype_is_quoted(self):
        assert format_dsl("f.csv", {"id": "42"}) == 'f.csv[id: "42"]'


class TestRoundTrip:
    """parse(format(parse(s))) is stable for representative inputs."""

    @pytest.mark.parametrize(
        "original",
        [
            "file.pdf[pages: 1-4]",
            "data.xlsx[sheet: Sales, rows: 100]",
            "doc.pdf[images: true, dpi: 300]",
            'f.csv[name: "hello, world", id: "42"]',
            "doc.pdf[password: a:b]",
        ],
    )
    def test_roundtrip_consistency(self, original: str):
        source1, opts1 = parse_dsl(original)
        source2, opts2 = parse_dsl(format_dsl(source1, opts1))
        assert source1 == source2
        assert opts1 == opts2
