"""
Tests for the Excel (XLSX) processor.

=============================================================================
TEST GUIDELINES FOR XLSX PROCESSOR
=============================================================================

GOOD tests for XLSX processor:
    - Use pytest.mark.skipif for optional deps
    - Test with real XLSX bytes (fixture from conftest.py)
    - Test sheet selection options
    - Test row limiting
    - Test fallback between pandas and openpyxl

BAD tests:
    - Assuming pandas/openpyxl are always installed
    - Testing CSV output format exactly (implementation detail)
    - Huge test files (use minimal fixtures)

NOTES:
    - XLSX processor prefers pandas if available, falls back to openpyxl
    - Output is CSV-formatted text for LLM consumption
    - Tests skip gracefully if deps not installed

=============================================================================
"""

from __future__ import annotations

import pytest

from attachments.deps import check_dep
from attachments.processors import processors

# Skip all tests if no XLSX deps available
pytestmark = pytest.mark.skipif(
    not check_dep("xlsx").available,
    reason="XLSX deps (openpyxl) not installed",
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
        assert "flags" in result

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

    def test_flags_include_metadata(self, sample_xlsx_bytes: bytes):
        processor = processors[".xlsx"]
        result = processor(sample_xlsx_bytes)

        flags = result["flags"]
        assert flags["kind"] == "table"
        assert "rows" in flags
        assert "cols" in flags
        assert "sheets" in flags
        assert "engine" in flags

    def test_flags_engine_is_pandas_or_openpyxl(self, sample_xlsx_bytes: bytes):
        processor = processors[".xlsx"]
        result = processor(sample_xlsx_bytes)

        assert result["flags"]["engine"] in ("pandas", "openpyxl")


class TestXlsxProcessorOptions:
    """Tests for XLSX processor options."""

    def test_sheet_selection_by_name(self, sample_xlsx_bytes: bytes):
        processor = processors[".xlsx"]
        result = processor(sample_xlsx_bytes, sheet="Sales")

        # Should use the Sales sheet
        assert result["flags"]["sheet_used"] == "Sales"
        assert "Product" in result["text"]
        assert "Revenue" in result["text"]

    def test_sheet_selection_by_index(self, sample_xlsx_bytes: bytes):
        processor = processors[".xlsx"]
        result = processor(sample_xlsx_bytes, sheet=1)  # Second sheet (Sales)

        assert result["flags"]["sheet_used"] == "Sales"

    def test_sheet_selection_invalid_uses_first(self, sample_xlsx_bytes: bytes):
        processor = processors[".xlsx"]
        result = processor(sample_xlsx_bytes, sheet="NonexistentSheet")

        # Should fall back to first sheet
        assert result["flags"]["sheet_used"] == "Sheet1"

    def test_max_rows_limits_output(self, sample_xlsx_bytes: bytes):
        processor = processors[".xlsx"]
        result = processor(sample_xlsx_bytes, max_rows=2)

        # Should have limited rows (header + 2 data rows max)
        lines = result["text"].strip().split("\n")
        assert len(lines) <= 3  # header + 2 rows

    def test_default_max_rows(self, sample_xlsx_bytes: bytes):
        processor = processors[".xlsx"]
        result = processor(sample_xlsx_bytes)

        # Default is 200 rows - our test file is smaller
        assert "text" in result


class TestXlsxProcessorErrors:
    """Tests for XLSX processor error handling."""

    def test_corrupt_xlsx_returns_error(self, corrupt_xlsx_bytes: bytes):
        processor = processors[".xlsx"]
        result = processor(corrupt_xlsx_bytes)

        # Should return artifact with error, not raise
        assert "flags" in result
        # Either has error or empty text
        has_error = "error" in result["flags"] or "pandas_exc" in result["flags"]
        is_empty = result["text"] == ""
        assert has_error or is_empty

    def test_empty_bytes_handled(self):
        processor = processors[".xlsx"]
        result = processor(b"")

        assert "flags" in result


class TestXlsxSheetDiscovery:
    """Tests for sheet discovery."""

    def test_sheets_list_populated(self, sample_xlsx_bytes: bytes):
        processor = processors[".xlsx"]
        result = processor(sample_xlsx_bytes)

        sheets = result["flags"]["sheets"]
        assert isinstance(sheets, list)
        assert "Sheet1" in sheets
        assert "Sales" in sheets

    def test_sheet_count(self, sample_xlsx_bytes: bytes):
        processor = processors[".xlsx"]
        result = processor(sample_xlsx_bytes)

        assert len(result["flags"]["sheets"]) == 2


@pytest.mark.skipif(
    not check_dep("xlsx-pandas").available,
    reason="pandas not installed",
)
class TestXlsxWithPandas:
    """Tests specific to pandas engine."""

    def test_uses_pandas_when_available(self, sample_xlsx_bytes: bytes):
        processor = processors[".xlsx"]
        result = processor(sample_xlsx_bytes)

        # Should prefer pandas
        assert result["flags"]["engine"] == "pandas"


class TestXlsxProcessorWithoutDeps:
    """Tests for XLSX processor behavior when deps are missing."""

    @pytest.mark.skipif(
        check_dep("xlsx").available,
        reason="Test only relevant when XLSX deps missing",
    )
    def test_missing_deps_returns_error(self):
        processor = processors[".xlsx"]
        result = processor(b"fake xlsx content")

        assert "error" in result["flags"]
