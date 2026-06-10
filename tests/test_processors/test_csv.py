"""Tests for the csv/tsv processor (stdlib-first, optional pandas summary)."""

from __future__ import annotations

import sys

import pytest

from attachments._options import get_options
from attachments._processors import csv as csv_module
from attachments._processors import processors
from attachments._processors.csv import csv_processor
from attachments.deps import check_dep, clear_cache

HAS_PANDAS = check_dep("csv-pandas").available


@pytest.fixture(autouse=True)
def _ensure_registered():
    """Re-register the csv processor for every test.

    csv.py is not yet wired into _processors/__init__.py, so the conftest's
    autouse ``reset_processors()`` (which restores the built-in snapshot)
    would drop its registrations after the first test.
    """
    csv_module.register()


@pytest.fixture
def mask_modules(monkeypatch):
    """Hide modules from the import machinery (test_missing_deps pattern)."""

    def _mask(*names: str) -> None:
        for name in names:
            monkeypatch.setitem(sys.modules, name, None)
        clear_cache()

    yield _mask
    clear_cache()


class TestRegistration:
    @pytest.mark.parametrize("ext", [".csv", ".tsv"])
    def test_extensions_registered_with_options(self, ext):
        assert processors[ext] is csv_processor
        names = [o.name for o in get_options(ext)]
        assert names == ["rows", "summary", "delimiter"]

    def test_rows_option_aliases_and_default(self):
        rows = get_options(".csv")[0]
        assert rows.aliases == ("max_rows", "limit")  # limit honors v1 [limit:N]
        assert rows.param == "max_rows"
        assert rows.default == 200


class TestBasicRendering:
    def test_basic_table_exact_match(self):
        result = csv_processor(b"a,b\n1,2\n3,4\n", filename="t.csv")

        assert result["text"] == ("| a | b |\n| --- | --- |\n| 1 | 2 |\n| 3 | 4 |")
        assert "error" not in result["meta"]

    def test_quoted_fields_with_commas_and_newlines(self):
        data = b'name,desc\n"Smith, J","line1\nline2"\n'

        result = csv_processor(data, filename="t.csv")

        assert "| Smith, J | line1 line2 |" in result["text"]
        extra = result["meta"]["extra"]
        assert extra["rows"] == 1
        assert extra["cols"] == 2

    def test_pipe_escaping(self):
        result = csv_processor(b"a,b\nx|y,z\n", filename="t.csv")

        assert "| x\\|y | z |" in result["text"]

    def test_kind_and_extra(self):
        result = csv_processor(b"a,b\n1,2\n", filename="t.csv")

        meta = result["meta"]
        assert meta["kind"] == "table"
        extra = meta["extra"]
        assert extra["rows"] == 1
        assert extra["cols"] == 2
        assert extra["delimiter"] == ","
        assert extra["encoding"] == "utf-8"
        assert extra["engine"] == "stdlib"
        assert "rows_truncated" not in extra
        assert "summary_engine" not in extra


class TestDelimiters:
    def test_semicolon_sniffed(self):
        result = csv_processor(b"a;b\n1;2\n3;4\n", filename="t.csv")

        assert result["text"].startswith("| a | b |")
        assert result["meta"]["extra"]["delimiter"] == ";"

    def test_tsv_defaults_to_tab_when_sniff_fails(self):
        # Single column: nothing for the sniffer to find.
        result = csv_processor(b"a\n1\n", filename="t.tsv")

        assert result["meta"]["extra"]["delimiter"] == "\t"
        assert result["text"].startswith("| a |")

    def test_tsv_parsed_as_real_table(self):
        # v3 divergence: v1 rendered .tsv as a fenced code block.
        result = csv_processor(b"a\tb\n1\t2\n", filename="t.tsv")

        assert result["text"] == "| a | b |\n| --- | --- |\n| 1 | 2 |"

    def test_explicit_delimiter_char_overrides_sniff(self):
        result = csv_processor(b"a|b\n1|2\n", filename="t.csv", delimiter="|")

        assert result["meta"]["extra"]["delimiter"] == "|"
        assert result["text"].startswith("| a | b |")

    @pytest.mark.parametrize(
        ("word", "char"),
        [("tab", "\t"), ("comma", ","), ("semicolon", ";"), ("pipe", "|")],
    )
    def test_delimiter_word_forms(self, word, char):
        data = f"a{char}b\n1{char}2\n".encode()

        result = csv_processor(data, filename="t.csv", delimiter=word)

        assert result["meta"]["extra"]["delimiter"] == char
        assert result["text"].startswith("| a | b |")


class TestEncoding:
    def test_latin1_bytes_round_trip(self):
        data = "name,city\nJosé,Münich\n".encode("latin-1")

        result = csv_processor(data, filename="t.csv")

        assert "José" in result["text"]
        assert "Münich" in result["text"]
        assert "error" not in result["meta"]


class TestEdgeCases:
    @pytest.mark.parametrize("data", [b"", b"   \n  \n"])
    def test_empty_input_is_not_an_error(self, data):
        result = csv_processor(data, filename="t.csv")

        assert result["text"] == ""
        meta = result["meta"]
        assert "error" not in meta
        assert meta["note"] == "empty CSV"
        assert meta["extra"]["rows"] == 0

    def test_header_only(self):
        result = csv_processor(b"a,b\n", filename="t.csv")

        assert result["text"] == "| a | b |\n| --- | --- |"
        assert result["meta"]["extra"]["rows"] == 0

    def test_corruptish_input_never_raises(self):
        for data in (b"\x00\x01\x02", b'"unclosed,\xff\xfe', b"\xff" * 64):
            result = csv_processor(data, filename="bad.csv")
            assert isinstance(result, dict)
            assert "meta" in result  # artifact, error or not — never raised


class TestTruncation:
    def test_default_cap_at_200(self):
        data = b"a\n" + b"\n".join(b"%d" % i for i in range(300)) + b"\n"

        result = csv_processor(data, filename="t.csv")

        extra = result["meta"]["extra"]
        assert extra["rows"] == 300
        assert extra["rows_truncated"] is True
        # header + separator + 200 data rows
        assert result["text"].count("\n") == 201

    def test_limit_alias_via_max_rows_param(self):
        # the DSL alias "limit" maps to the max_rows kwarg
        data = b"a\n1\n2\n3\n"

        result = csv_processor(data, filename="t.csv", max_rows=2)

        assert result["meta"]["extra"]["rows_truncated"] is True
        assert result["text"] == "| a |\n| --- |\n| 1 |\n| 2 |"


class TestSummary:
    @pytest.mark.skipif(not HAS_PANDAS, reason="pandas not installed")
    def test_summary_with_pandas(self):
        data = b"name,age\nann,30\nbob,40\n"

        result = csv_processor(data, filename="t.csv", summary=True)

        text = result["text"]
        assert "## Summary" in text
        assert "- Rows: 2" in text
        assert "- Columns: 2" in text
        assert "age" in text
        assert "30" in text and "35.0" in text and "40" in text  # min/mean/max
        assert result["meta"]["extra"]["summary_engine"] == "pandas"
        assert text.startswith("| name | age |")  # table still first

    def test_summary_without_pandas_keeps_table_and_warns(self, mask_modules):
        mask_modules("pandas")

        result = csv_processor(b"a,b\n1,2\n", filename="t.csv", summary=True)

        # Deliberate softening of the missing-dep protocol: the stdlib table
        # succeeded, so no missing-dependency artifact.
        assert "error" not in result["meta"]
        assert result["text"].startswith("| a | b |")
        assert "## Summary" not in result["text"]
        warnings = result["meta"]["warnings"]
        assert any("pip install attachments[csv-pandas]" in w for w in warnings)
        assert "summary_engine" not in result["meta"]["extra"]

    def test_no_summary_by_default(self):
        result = csv_processor(b"a,b\n1,2\n", filename="t.csv")

        assert "## Summary" not in result["text"]
        assert "warnings" not in result["meta"]
