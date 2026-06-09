"""
Tests for the Excel (XLSX) processor.

=============================================================================
TEST GUIDELINES FOR XLSX PROCESSOR
=============================================================================

GOOD tests for XLSX processor:
    - Use pytest.mark.skipif for optional deps
    - Test with real XLSX bytes (fixture from conftest.py or built in-test)
    - Test the all-sheets default and sheet selection options
    - Test row limiting per sheet
    - Test fallback between openpyxl and pandas

BAD tests:
    - Assuming pandas/openpyxl are always installed
    - Huge test files (use minimal fixtures)

NOTES:
    - XLSX processor uses openpyxl as the primary backend, pandas as fallback
    - Output is a "# <sheet name>" heading + CSV rows per sheet; with no
      'sheet' option ALL sheets are rendered, joined with a blank line
    - meta.segments carries one sheet segment per rendered sheet
    - Tests skip gracefully if deps not installed

=============================================================================
"""

from __future__ import annotations

from io import BytesIO

import pytest

from attachments.deps import check_dep
from attachments.processors import processors

# Skip all tests if no XLSX deps available
pytestmark = pytest.mark.skipif(
    not check_dep("xlsx").available,
    reason="XLSX deps (openpyxl) not installed",
)


def _build_workbook(sheets: dict[str, list[list]]) -> bytes:
    """Build a real multi-sheet XLSX in memory with openpyxl."""
    from openpyxl import Workbook

    wb = Workbook()
    first = True
    for name, rows in sheets.items():
        if first:
            ws = wb.active
            ws.title = name
            first = False
        else:
            ws = wb.create_sheet(name)
        for row in rows:
            ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture
def multi_sheet_xlsx_bytes() -> bytes:
    """Three-sheet workbook for segmentation tests."""
    return _build_workbook(
        {
            "Alpha": [["Name", "Age"], ["Alice", 30], ["Bob", 25]],
            "Beta": [["Product", "Revenue"], ["Widget", 1000]],
            "Gamma": [["X"], [1], [2], [3]],
        }
    )


class TestXlsxProcessor:
    """Tests for XLSX processor with real Excel files."""

    def test_processor_registered(self):
        assert ".xlsx" in processors

    def test_returns_artifact_structure(self, sample_xlsx_bytes: bytes):
        processor = processors[".xlsx"]
        result = processor(sample_xlsx_bytes)

        assert "text" in result
        assert "images" in result
        assert "audio" in result
        assert "video" in result
        assert "meta" in result

    def test_extracts_text_as_csv(self, sample_xlsx_bytes: bytes):
        processor = processors[".xlsx"]
        result = processor(sample_xlsx_bytes)

        # Should contain header row
        assert "Name" in result["text"]
        assert "Age" in result["text"]
        assert "City" in result["text"]

        # Should contain data
        assert "Alice" in result["text"]
        assert "30" in result["text"]

    def test_all_sheets_rendered_by_default(self, sample_xlsx_bytes: bytes):
        processor = processors[".xlsx"]
        result = processor(sample_xlsx_bytes)

        # Both sheets present, each with a heading line
        assert "# Sheet1" in result["text"]
        assert "# Sales" in result["text"]
        assert "Product" in result["text"]
        assert "Widget" in result["text"]
        # No sheet_used when several sheets are rendered
        assert "sheet_used" not in result["meta"]["extra"]

    def test_meta_includes_metadata(self, sample_xlsx_bytes: bytes):
        processor = processors[".xlsx"]
        result = processor(sample_xlsx_bytes)

        meta = result["meta"]
        assert meta["kind"] == "table"
        extra = meta["extra"]
        assert "sheets" in extra
        assert "engine" in extra

    def test_single_sheet_metadata(self, sample_xlsx_bytes: bytes):
        processor = processors[".xlsx"]
        result = processor(sample_xlsx_bytes, sheet="Sheet1")

        extra = result["meta"]["extra"]
        assert extra["sheet_used"] == "Sheet1"
        assert "rows" in extra
        assert "cols" in extra

    def test_extra_engine_is_pandas_or_openpyxl(self, sample_xlsx_bytes: bytes):
        processor = processors[".xlsx"]
        result = processor(sample_xlsx_bytes)

        assert result["meta"]["extra"]["engine"] in ("pandas", "openpyxl")


class TestXlsxProcessorOptions:
    """Tests for XLSX processor options."""

    def test_sheet_selection_by_name(self, sample_xlsx_bytes: bytes):
        processor = processors[".xlsx"]
        result = processor(sample_xlsx_bytes, sheet="Sales")

        # Should use the Sales sheet only
        assert result["meta"]["extra"]["sheet_used"] == "Sales"
        assert result["text"].startswith("# Sales\n")
        assert "Product" in result["text"]
        assert "Revenue" in result["text"]
        assert "# Sheet1" not in result["text"]

    def test_sheet_selection_by_index(self, sample_xlsx_bytes: bytes):
        processor = processors[".xlsx"]
        result = processor(sample_xlsx_bytes, sheet=1)  # Second sheet (Sales)

        assert result["meta"]["extra"]["sheet_used"] == "Sales"
        assert result["text"].startswith("# Sales\n")

    def test_sheet_selection_invalid_uses_first(self, sample_xlsx_bytes: bytes):
        processor = processors[".xlsx"]
        result = processor(sample_xlsx_bytes, sheet="NonexistentSheet")

        # Should fall back to first sheet
        assert result["meta"]["extra"]["sheet_used"] == "Sheet1"

    def test_max_rows_limits_output_per_sheet(self, multi_sheet_xlsx_bytes: bytes):
        processor = processors[".xlsx"]
        result = processor(multi_sheet_xlsx_bytes, max_rows=1)

        # Each sheet block: heading + header row + at most 1 data row
        for segment in result["meta"]["segments"]:
            block = result["text"][segment["start"] : segment["end"]]
            assert len(block.split("\n")) <= 3

        # Alpha (2 data rows) and Gamma (3 data rows) were truncated
        assert result["meta"]["extra"]["rows_truncated"] is True

    def test_max_rows_with_single_sheet(self, sample_xlsx_bytes: bytes):
        processor = processors[".xlsx"]
        result = processor(sample_xlsx_bytes, sheet="Sheet1", max_rows=2)

        # heading + header + 2 data rows
        lines = result["text"].strip().split("\n")
        assert len(lines) == 4
        assert result["meta"]["extra"]["rows_truncated"] is True

    def test_rows_truncated_absent_when_not_hit(self, sample_xlsx_bytes: bytes):
        processor = processors[".xlsx"]
        result = processor(sample_xlsx_bytes)

        # Default 200 rows is plenty for the fixture
        assert "rows_truncated" not in result["meta"]["extra"]

    def test_default_max_rows(self, sample_xlsx_bytes: bytes):
        processor = processors[".xlsx"]
        result = processor(sample_xlsx_bytes)

        # Default is 200 rows - our test file is smaller
        assert "text" in result


class TestXlsxProcessorErrors:
    """Tests for XLSX processor error handling."""

    def test_corrupt_xlsx_returns_parse_error(self, corrupt_xlsx_bytes: bytes):
        from attachments.types import ERROR_PARSE

        processor = processors[".xlsx"]
        result = processor(corrupt_xlsx_bytes)

        # Should return artifact with a typed error, not raise
        assert result["text"] == ""
        assert result["meta"]["error"]["code"] == ERROR_PARSE

    def test_empty_bytes_handled(self):
        processor = processors[".xlsx"]
        result = processor(b"")

        assert "meta" in result


class TestXlsxSheetDiscovery:
    """Tests for sheet discovery."""

    def test_sheets_list_populated(self, sample_xlsx_bytes: bytes):
        processor = processors[".xlsx"]
        result = processor(sample_xlsx_bytes)

        sheets = result["meta"]["extra"]["sheets"]
        assert isinstance(sheets, list)
        assert "Sheet1" in sheets
        assert "Sales" in sheets

    def test_sheet_count(self, sample_xlsx_bytes: bytes):
        processor = processors[".xlsx"]
        result = processor(sample_xlsx_bytes)

        assert len(result["meta"]["extra"]["sheets"]) == 2


@pytest.mark.skipif(
    not check_dep("xlsx-pandas").available,
    reason="pandas not installed",
)
class TestXlsxWithPandas:
    """The pandas fallback renders the same text layout as openpyxl."""

    def test_pandas_layout_matches_openpyxl(self, multi_sheet_xlsx_bytes: bytes):
        from attachments.processors.xlsx import (
            _xlsx_with_openpyxl,
            _xlsx_with_pandas,
        )

        text_o, segs_o, _ = _xlsx_with_openpyxl(
            multi_sheet_xlsx_bytes, sheet=None, max_rows=200
        )
        text_p, segs_p, extra_p = _xlsx_with_pandas(
            multi_sheet_xlsx_bytes, sheet=None, max_rows=200
        )

        assert text_p == text_o
        assert segs_p == segs_o
        assert extra_p["engine"] == "pandas"

    def test_pandas_single_sheet_matches_openpyxl(self, sample_xlsx_bytes: bytes):
        from attachments.processors.xlsx import (
            _xlsx_with_openpyxl,
            _xlsx_with_pandas,
        )

        text_o, segs_o, _ = _xlsx_with_openpyxl(
            sample_xlsx_bytes, sheet="Sales", max_rows=200
        )
        text_p, segs_p, extra_p = _xlsx_with_pandas(
            sample_xlsx_bytes, sheet="Sales", max_rows=200
        )

        assert text_p == text_o
        assert segs_p == segs_o
        assert extra_p["sheet_used"] == "Sales"


class TestXlsxSegments:
    """meta.segments carries one sheet segment per rendered sheet (IR contract)."""

    def test_all_sheets_segments_slice_exactly(self, multi_sheet_xlsx_bytes: bytes):
        processor = processors[".xlsx"]
        result = processor(multi_sheet_xlsx_bytes)

        text = result["text"]
        segments = result["meta"]["segments"]
        names = result["meta"]["extra"]["sheets"]
        assert names == ["Alpha", "Beta", "Gamma"]
        assert [s["label"] for s in segments] == names

        # Each segment slices exactly that sheet's block, heading included
        blocks = text.split("\n\n")
        assert len(blocks) == 3
        for segment, name, block in zip(segments, names, blocks, strict=False):
            assert segment["kind"] == "sheet"
            assert text[segment["start"] : segment["end"]] == block
            assert block.startswith(f"# {name}\n")

        # Segments tile the text: start at 0, end at len(text), separated
        # by exactly the two-character joiner.
        assert segments[0]["start"] == 0
        assert segments[-1]["end"] == len(text)
        for prev, nxt in zip(segments, segments[1:], strict=False):
            assert nxt["start"] == prev["end"] + 2

    def test_all_sheets_segment_content(self, multi_sheet_xlsx_bytes: bytes):
        processor = processors[".xlsx"]
        result = processor(multi_sheet_xlsx_bytes)

        text = result["text"]
        by_label = {s["label"]: s for s in result["meta"]["segments"]}
        beta = text[by_label["Beta"]["start"] : by_label["Beta"]["end"]]
        assert beta == "# Beta\nProduct,Revenue\nWidget,1000"

    def test_single_sheet_still_has_segment(self, multi_sheet_xlsx_bytes: bytes):
        processor = processors[".xlsx"]
        result = processor(multi_sheet_xlsx_bytes, sheet="Beta")

        segments = result["meta"]["segments"]
        assert len(segments) == 1
        segment = segments[0]
        assert segment["kind"] == "sheet"
        assert segment["label"] == "Beta"
        assert segment["start"] == 0
        assert segment["end"] == len(result["text"])

    def test_single_sheet_by_index_segment(self, multi_sheet_xlsx_bytes: bytes):
        processor = processors[".xlsx"]
        result = processor(multi_sheet_xlsx_bytes, sheet=2)

        segments = result["meta"]["segments"]
        assert len(segments) == 1
        assert segments[0]["label"] == "Gamma"
        assert result["text"].startswith("# Gamma\n")

    def test_sheet_segment_label_follows_selection(self, sample_xlsx_bytes: bytes):
        processor = processors[".xlsx"]
        result = processor(sample_xlsx_bytes, sheet="Sales")

        assert result["meta"]["segments"][0]["label"] == "Sales"

    def test_segments_respect_max_rows(self, multi_sheet_xlsx_bytes: bytes):
        processor = processors[".xlsx"]
        result = processor(multi_sheet_xlsx_bytes, max_rows=1)

        text = result["text"]
        by_label = {s["label"]: s for s in result["meta"]["segments"]}
        gamma = text[by_label["Gamma"]["start"] : by_label["Gamma"]["end"]]
        # heading + header + exactly 1 data row
        assert gamma == "# Gamma\nX\n1"


# Missing-dependency behavior is covered by the always-runnable tests in
# tests/test_processors/test_missing_deps.py (this module is skipped
# entirely when XLSX deps are absent, so such tests could never run here).
