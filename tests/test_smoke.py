"""Smoke tests for basic functionality."""

import pytest
import tempfile
from pathlib import Path

from attachments import Attachments
import attachments


@pytest.fixture
def text_file():
    """Create a temporary text file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("Hello world test content")
        yield f.name
    Path(f.name).unlink(missing_ok=True)


@pytest.fixture
def multiple_text_files():
    """Create multiple temporary text files."""
    files = []
    for i in range(2):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(f"Test content {i}")
            files.append(f.name)
    yield files
    for file_path in files:
        Path(file_path).unlink(missing_ok=True)


def test_import_works():
    """Test that basic imports work."""
    assert hasattr(attachments, 'Attachments')
    assert hasattr(attachments, '__version__')


def test_version_is_correct():
    """Test that version matches expected value."""
    assert attachments.__version__ == "0.10.0"


def test_text_file_processing():
    """Test basic text file processing."""
    # Create a temporary text file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("Hello, world!\nThis is a test file.")
        temp_path = f.name
    
    try:
        ctx = Attachments(temp_path)
        assert len(ctx) == 1
        assert len(str(ctx)) > 0
        assert "Hello, world!" in str(ctx)
    finally:
        Path(temp_path).unlink()


def test_multiple_files():
    """Test processing multiple files."""
    # Create temporary files
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f1:
        f1.write("File 1 content")
        path1 = f1.name
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f2:
        f2.write("File 2 content")
        path2 = f2.name
    
    try:
        ctx = Attachments(path1, path2)
        assert len(ctx) == 2
        text = str(ctx)
        assert "File 1 content" in text
        assert "File 2 content" in text
        assert "Processing Summary: 2 files processed" in text
    finally:
        Path(path1).unlink()
        Path(path2).unlink()


def test_str_conversion_works():
    """Test that string conversion works."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("Test content")
        temp_path = f.name
    
    try:
        ctx = Attachments(temp_path)
        text = str(ctx)
        assert isinstance(text, str)
        assert "Test content" in text
    finally:
        Path(temp_path).unlink()


def test_f_string_works():
    """Test that f-string formatting works."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("Test content")
        temp_path = f.name
    
    try:
        ctx = Attachments(temp_path)
        formatted = f"Context: {ctx}"
        assert isinstance(formatted, str)
        assert "Test content" in formatted
    finally:
        Path(temp_path).unlink()


def test_images_property_works():
    """Test that images property returns a list."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("Test content")
        temp_path = f.name
    
    try:
        ctx = Attachments(temp_path)
        images = ctx.images
        assert isinstance(images, list)
        # Text files shouldn't have images
        assert len(images) == 0
    finally:
        Path(temp_path).unlink()


def test_nonexistent_file_raises():
    """Test that nonexistent files are handled gracefully."""
    # Should not crash, but create an error attachment
    ctx = Attachments("nonexistent_file.txt")
    assert len(ctx) == 1
    text = str(ctx)
    # The actual output shows the filename and None object type
    assert "nonexistent_file.txt" in text
    assert "NoneType" in text or "None" in text


def test_readme_url_example():
    """Test the exact URL example from the README."""
    # This is the example from the top of the README
    ctx = Attachments("https://github.com/MaximeRivest/attachments/raw/main/src/attachments/data/sample.pdf",
                      "https://github.com/MaximeRivest/attachments/raw/main/src/attachments/data/sample_multipage.pptx")
    
    # Should process both files
    assert len(ctx) == 2
    
    # Should have text from both
    text = str(ctx)
    assert len(text) > 200
    assert "Processing Summary: 2 files processed" in text
    
    # Should have images from PDF
    assert len(ctx.images) >= 1
    
    # Should have content from both files
    assert "PDF Document" in text
    assert "Presentation" in text


def test_local_data_files():
    """Test using local files from the data directory."""
    from attachments.data import get_sample_path
    
    # Test with local sample files
    pdf_path = get_sample_path("sample.pdf")
    txt_path = get_sample_path("sample.txt")
    
    ctx = Attachments(pdf_path, txt_path)
    
    # Should process both files
    assert len(ctx) == 2
    
    # Should have text from both
    text = str(ctx)
    assert len(text) > 200
    assert "Processing Summary: 2 files processed" in text
    
    # Should have content from both files
    assert "PDF Document" in text or "Hello PDF!" in text
    assert "Welcome to the Attachments Library!" in text
    
    # PDF should provide images
    assert len(ctx.images) >= 1


def test_mixed_local_and_url():
    """Test mixing local files and URLs."""
    from attachments.data import get_sample_path
    
    # Mix local and remote files
    local_txt = get_sample_path("sample.txt")
    remote_pdf = "https://github.com/MaximeRivest/attachments/raw/main/src/attachments/data/sample.pdf"
    
    ctx = Attachments(local_txt, remote_pdf)
    
    # Should process both files
    assert len(ctx) == 2
    
    # Should have text from both
    text = str(ctx)
    assert len(text) > 200
    assert "Processing Summary: 2 files processed" in text
    
    # Should have content from both files
    assert "Welcome to the Attachments Library!" in text
    assert "PDF Document" in text or "Hello PDF!" in text


def test_multiple_file_types():
    """Test the multiple file types example from README."""
    from attachments.data import get_sample_path
    
    # Test with different file types
    docx_path = get_sample_path("test_document.docx")
    csv_path = get_sample_path("test.csv")
    json_path = get_sample_path("sample.json")
    
    ctx = Attachments(docx_path, csv_path, json_path)
    
    # Should process all three files
    assert len(ctx) == 3
    
    # Should have text from all files
    text = str(ctx)
    assert len(text) > 500  # Should have substantial content
    assert "Processing Summary: 3 files processed" in text 


def test_css_highlighting_feature():
    """Test the advanced CSS highlighting feature for webpage screenshots."""
    from attachments import Attachments
    
    # Test with a simple webpage that has CSS selector highlighting using DSL syntax
    ctx = Attachments("https://httpbin.org/html[select:h1]")
    
    # Check that the command was registered
    assert len(ctx.attachments) == 1
    att = ctx.attachments[0]
    assert 'select' in att.commands
    assert att.commands['select'] == 'h1'
    
    # The images should be generated (though we can't test Playwright without it installed)
    # At minimum, the attachment should be created and the command should be stored
    assert att.commands.get('select') == 'h1'
    
    # Test multiple selectors
    ctx2 = Attachments("https://httpbin.org/html[select:h1, p]")
    att2 = ctx2.attachments[0]
    assert att2.commands.get('select') == 'h1, p' 