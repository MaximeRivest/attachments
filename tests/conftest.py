"""
Shared pytest fixtures for attachments tests.

=============================================================================
FIXTURE GUIDELINES
=============================================================================

GOOD fixtures:
    - Are focused and do ONE thing (create a temp dir, provide sample bytes)
    - Have clear names that describe what they provide
    - Clean up after themselves (use tmp_path, context managers)
    - Are reusable across multiple test files
    - Document what they return

BAD fixtures:
    - Do too much setup (split into smaller fixtures)
    - Have side effects on global state without cleanup
    - Are only used by one test (just inline the setup)
    - Have vague names like "setup" or "data"

SCOPE GUIDELINES:
    - function (default): Fresh for each test. Use for mutable state.
    - module: Shared within a file. Use for expensive, read-only fixtures.
    - session: Shared across all tests. Use sparingly (e.g., test server).

=============================================================================
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    pass


# =============================================================================
# CONFIG FIXTURES - Reset global state between tests
# =============================================================================


@pytest.fixture(autouse=True)
def reset_global_config():
    """Reset configuration after each test to ensure isolation.

    This runs automatically for every test (autouse=True).
    """
    from attachments.config import reset_config

    yield
    reset_config()


@pytest.fixture(autouse=True)
def reset_processor_registry():
    """Reset processor registry after each test.

    Ensures custom processors registered in tests don't leak.
    """
    from attachments.processors import reset_processors

    yield
    reset_processors()


# =============================================================================
# SAMPLE FILE FIXTURES - Provide realistic test data
# =============================================================================


@pytest.fixture
def sample_text_bytes() -> bytes:
    """Simple UTF-8 text content."""
    return b"Hello, World!\nThis is a test file.\n"


@pytest.fixture
def sample_text_latin1() -> bytes:
    """Latin-1 encoded text with special characters."""
    return "Café résumé naïve".encode("latin-1")


@pytest.fixture
def sample_json_bytes() -> bytes:
    """Valid JSON content."""
    return b'{"name": "test", "value": 42, "nested": {"key": "value"}}'


@pytest.fixture
def sample_binary_bytes() -> bytes:
    """Binary content that should NOT be detected as text."""
    return bytes(range(256))  # All byte values including NUL


# =============================================================================
# ARCHIVE FIXTURES - ZIP and TAR files
# =============================================================================


@pytest.fixture
def sample_zip_bytes(sample_text_bytes: bytes) -> bytes:
    """A ZIP archive containing a single text file."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("hello.txt", sample_text_bytes)
    return buf.getvalue()


@pytest.fixture
def nested_zip_bytes(sample_text_bytes: bytes) -> bytes:
    """A ZIP containing another ZIP (nested archives)."""
    # Inner zip
    inner_buf = io.BytesIO()
    with zipfile.ZipFile(inner_buf, "w") as inner_zf:
        inner_zf.writestr("inner/deep.txt", b"Deep nested content\n")
    inner_bytes = inner_buf.getvalue()

    # Outer zip containing inner zip and a regular file
    outer_buf = io.BytesIO()
    with zipfile.ZipFile(outer_buf, "w") as outer_zf:
        outer_zf.writestr("outer.txt", sample_text_bytes)
        outer_zf.writestr("nested.zip", inner_bytes)
    return outer_buf.getvalue()


@pytest.fixture
def zip_with_traversal_attempt() -> bytes:
    """A ZIP with path traversal attempts (../../../etc/passwd).

    Used to test that path sanitization works correctly.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        # These should be sanitized to safe paths
        zf.writestr("../../../etc/passwd", b"should be sanitized")
        zf.writestr("normal/path.txt", b"normal file")
        zf.writestr("/absolute/path.txt", b"absolute path")
    return buf.getvalue()


# =============================================================================
# DIRECTORY FIXTURES - Temp directories with files
# =============================================================================


@pytest.fixture
def sample_directory(tmp_path: Path, sample_text_bytes: bytes) -> Path:
    """A directory with mixed file types for testing unpack."""
    # Text files
    (tmp_path / "readme.txt").write_bytes(sample_text_bytes)
    (tmp_path / "data.json").write_bytes(b'{"key": "value"}')

    # Subdirectory
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    (subdir / "nested.md").write_bytes(b"# Nested Markdown\n\nContent here.")

    # Binary file (should not be processed as text)
    (tmp_path / "binary.bin").write_bytes(bytes(range(256)))

    return tmp_path


@pytest.fixture
def sample_directory_with_zip(sample_directory: Path, sample_zip_bytes: bytes) -> Path:
    """A directory containing a ZIP file that should be expanded."""
    (sample_directory / "archive.zip").write_bytes(sample_zip_bytes)
    return sample_directory


# =============================================================================
# EXCEL FIXTURES - Real XLSX files
# =============================================================================


@pytest.fixture
def sample_xlsx_bytes() -> bytes:
    """A minimal valid XLSX file with sample data.

    Creates a real XLSX using openpyxl if available, otherwise skips.
    """
    pytest.importorskip("openpyxl")
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"

    # Header row
    ws.append(["Name", "Age", "City"])
    # Data rows
    ws.append(["Alice", 30, "New York"])
    ws.append(["Bob", 25, "San Francisco"])
    ws.append(["Charlie", 35, "Chicago"])

    # Second sheet
    ws2 = wb.create_sheet("Sales")
    ws2.append(["Product", "Revenue"])
    ws2.append(["Widget", 1000])
    ws2.append(["Gadget", 2500])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture
def corrupt_xlsx_bytes() -> bytes:
    """Invalid XLSX content (not a real ZIP/XLSX)."""
    return b"This is not a valid XLSX file"


# =============================================================================
# PDF FIXTURES - Real PDF files
# =============================================================================


@pytest.fixture
def sample_pdf_bytes() -> bytes:
    """A minimal valid PDF with extractable text.

    Creates a real PDF using pypdf if available, otherwise skips.
    """
    pytest.importorskip("pypdf")
    from pypdf import PdfWriter

    writer = PdfWriter()

    # Create a minimal page with text
    # This creates a very basic PDF structure
    writer.add_blank_page(width=612, height=792)

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


@pytest.fixture
def minimal_pdf_bytes() -> bytes:
    """A hand-crafted minimal PDF (no external deps needed)."""
    # Minimal valid PDF structure
    return b"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >> endobj
xref
0 4
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
trailer << /Size 4 /Root 1 0 R >>
startxref
196
%%EOF
"""


@pytest.fixture
def corrupt_pdf_bytes() -> bytes:
    """Invalid PDF content."""
    return b"This is not a valid PDF file"


# =============================================================================
# MOCK FIXTURES - For service/HTTP testing
# =============================================================================


@pytest.fixture
def mock_service_response() -> dict:
    """Standard successful service response format."""
    return {
        "text": "Extracted text from service",
        "images": [],
        "audio": [],
        "video": [],
        "flags": {"via": "service", "format": "pdf"},
    }


@pytest.fixture
def mock_httpx(monkeypatch):
    """Mock httpx for service tests without network calls.

    Usage:
        def test_service(mock_httpx):
            mock_httpx.set_response({"text": "mocked"})
            result = process_via_service(data)
    """

    class MockResponse:
        def __init__(self, json_data: dict, status_code: int = 200):
            self._json = json_data
            self.status_code = status_code

        def json(self):
            return self._json

        def raise_for_status(self):
            if self.status_code >= 400:
                raise Exception(f"HTTP {self.status_code}")

    class MockClient:
        def __init__(self):
            self.response_data = {
                "text": "",
                "images": [],
                "audio": [],
                "video": [],
                "flags": {},
            }
            self.status_code = 200
            self.last_request = None

        def set_response(self, data: dict, status_code: int = 200):
            self.response_data = data
            self.status_code = status_code

        def post(self, url, **kwargs):
            self.last_request = {"url": url, "kwargs": kwargs}
            return MockResponse(self.response_data, self.status_code)

        def get(self, url, **kwargs):
            self.last_request = {"url": url, "kwargs": kwargs}
            return MockResponse(self.response_data, self.status_code)

    mock = MockClient()

    # Patch httpx module
    class MockHttpx:
        Client = lambda *a, **kw: mock  # noqa: E731

    monkeypatch.setattr("attachments.service._get_client", lambda: MockHttpx())

    return mock


# =============================================================================
# HELPER FIXTURES
# =============================================================================


@pytest.fixture
def assert_artifact():
    """Helper to validate artifact structure.

    Usage:
        def test_something(assert_artifact):
            result = att("file.txt")
            assert_artifact(result[0], has_text=True)
    """

    def _assert(
        artifact: dict,
        *,
        has_text: bool = False,
        has_error: bool = False,
        has_images: bool = False,
    ):
        # Check required keys exist
        assert "text" in artifact, "Artifact missing 'text' key"
        assert "images" in artifact, "Artifact missing 'images' key"
        assert "audio" in artifact, "Artifact missing 'audio' key"
        assert "video" in artifact, "Artifact missing 'video' key"
        assert "flags" in artifact, "Artifact missing 'flags' key"

        # Check types
        assert isinstance(artifact["text"], str)
        assert isinstance(artifact["images"], list)
        assert isinstance(artifact["flags"], dict)

        # Check content expectations
        if has_text:
            assert artifact["text"].strip(), "Expected non-empty text"
        if has_error:
            assert "error" in artifact["flags"], "Expected error in flags"
        if has_images:
            assert len(artifact["images"]) > 0, "Expected images"

    return _assert
