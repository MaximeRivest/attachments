"""Tests for the new modular attachments architecture."""

import pytest
import pandas as pd
import fitz
from PIL import Image
from pathlib import Path

# Test the core components
def test_core_imports():
    """Test that core components can be imported."""
    from attachments.core import Attachment, load, modify, present, adapt
    from attachments.core import loader, modifier, presenter, adapter
    
    # Check namespaces exist and have expected attributes
    assert hasattr(load, 'pdf')
    assert hasattr(load, 'csv') 
    assert hasattr(load, 'image')
    
    assert hasattr(modify, 'pages')
    assert hasattr(modify, 'sample')
    assert hasattr(modify, 'resize')
    
    assert hasattr(present, 'text')
    assert hasattr(present, 'images')
    assert hasattr(present, 'markdown')
    
    # Check that openai_chat adapter exists
    assert hasattr(adapt, 'openai_chat')


def test_attachment_creation():
    """Test basic Attachment creation and properties."""
    from attachments.core import Attachment
    
    content = "test content"
    source = "test.txt"
    commands = {"key": "value"}
    
    att = Attachment(content, source, commands)
    
    assert att.content == content
    assert att.source == source
    assert att.commands == commands
    assert att._pipeline_ready == True


def test_path_expression_parsing():
    """Test DSL path expression parsing."""
    from attachments.utils.parsing import parse_path_expression, parse_commands
    
    # Basic path without commands
    path, commands = parse_path_expression("file.pdf")
    assert path == "file.pdf"
    assert commands == {}
    
    # Path with commands
    path, commands = parse_path_expression("file.pdf[pages: 1-3, rotate: 90]")
    assert path == "file.pdf"
    assert commands == {"pages": "1-3", "rotate": "90"}
    
    # Test command parsing
    commands = parse_commands("key1: value1, key2: value2")
    assert commands == {"key1": "value1", "key2": "value2"}


def test_pdf_loading_and_text_extraction(sample_pdf_path):
    """Test PDF loading and text extraction."""
    from attachments.core import load, present
    
    # Load PDF
    att = load.pdf(sample_pdf_path)
    # Should be pypdf PdfReader (MIT-compatible), not fitz Document
    from pypdf import PdfReader
    assert isinstance(att.content, PdfReader)
    assert att.source == sample_pdf_path
    
    # Extract text
    text_att = present.text(att)
    assert isinstance(text_att.content, str)
    assert len(text_att.content) > 0


def test_pdf_image_extraction(sample_pdf_path):
    """Test PDF to images conversion."""
    from attachments.core import load, present
    
    # Load PDF
    att = load.pdf(sample_pdf_path)
    
    # Extract images
    images_att = present.images(att)
    assert isinstance(images_att.content, list)
    assert len(images_att.content) > 0
    assert all(img.startswith("data:image/png;base64,") for img in images_att.content)


def test_csv_loading_and_processing(sample_csv_path):
    """Test CSV loading and text conversion."""
    from attachments.core import load, present
    
    # Load CSV
    att = load.csv(sample_csv_path)
    assert isinstance(att.content, pd.DataFrame)
    
    # Extract text
    text_att = present.text(att)
    assert isinstance(text_att.content, str)
    
    # Extract markdown
    md_att = present.markdown(att)
    assert isinstance(md_att.content, str)
    assert "|" in md_att.content  # Markdown table should have pipes


def test_image_loading_and_processing(sample_image_path):
    """Test image loading and conversion."""
    from attachments.core import load, present
    
    # Load image
    att = load.image(sample_image_path)
    assert isinstance(att.content, Image.Image)
    
    # Convert to base64 images
    images_att = present.images(att)
    assert isinstance(images_att.content, list)
    assert len(images_att.content) == 1
    assert images_att.content[0].startswith("data:image/png;base64,")
    
    # Generate markdown
    md_att = present.markdown(att)
    assert isinstance(md_att.content, str)
    assert "![Image]" in md_att.content


def test_pdf_pages_modifier(sample_pdf_path):
    """Test PDF page extraction modifier."""
    from attachments.core import load, modify
    from pypdf import PdfReader
    
    # Load PDF with pages command
    att = load.pdf(f"{sample_pdf_path}[pages: 1]")
    
    # Apply pages modifier
    modified_att = modify.pages(att)
    
    # Should have fewer or same pages (using pypdf)
    assert isinstance(modified_att.content, PdfReader)
    assert len(modified_att.content.pages) <= len(att.content.pages)


def test_csv_sample_modifier(sample_csv_path):
    """Test CSV sampling modifier."""
    from attachments.core import load, modify
    
    # Load CSV
    att = load.csv(sample_csv_path)
    original_length = len(att.content)
    
    # Apply sample modifier
    n_samples = min(5, original_length)
    modified_att = modify.sample(att, n_samples)
    
    assert isinstance(modified_att.content, pd.DataFrame)
    assert len(modified_att.content) <= n_samples


def test_image_resize_modifier(sample_image_path):
    """Test image resize modifier."""
    from attachments.core import load, modify
    
    # Load image
    att = load.image(sample_image_path)
    original_size = att.content.size
    
    # Apply resize modifier - percentage
    modified_att = modify.resize(att, "50%")
    new_size = modified_att.content.size
    
    # Should be approximately half the size
    assert new_size[0] < original_size[0]
    assert new_size[1] < original_size[1]


def test_openai_adapter(sample_pdf_path):
    """Test OpenAI API adapter."""
    from attachments.core import load, adapt
    
    # Load PDF
    att = load.pdf(sample_pdf_path)
    
    # Convert to OpenAI format using the correct adapter name
    openai_content = adapt.openai_chat(att, "Analyze this document")
    
    assert isinstance(openai_content, list)
    assert len(openai_content) > 0
    
    # Should be a message with role and content
    message = openai_content[0]
    assert message["role"] == "user"
    assert "content" in message
    
    # Content should be a list of content items
    content_items = message["content"]
    assert isinstance(content_items, list)
    
    # Should have prompt text
    text_items = [item for item in content_items if item.get("type") == "text"]
    assert len(text_items) >= 1
    assert any("Analyze this document" in item.get("text", "") for item in text_items)
    
    # Should have images (PDFs get converted to images)
    image_items = [item for item in content_items if item.get("type") == "image_url"]
    assert len(image_items) > 0


def test_high_level_attachments_interface(sample_pdf_path, sample_csv_path):
    """Test the high-level Attachments interface."""
    from attachments import Attachments
    
    # Create with multiple files
    ctx = Attachments(sample_pdf_path, sample_csv_path)
    
    # Test basic properties
    assert len(ctx) == 2
    assert len(ctx.text) > 0
    assert len(ctx.images) > 0
    
    # Test string representation
    str_repr = str(ctx)
    assert "Attachments(2 files)" in str_repr
    
    # Test individual attachment access
    first_att = ctx[0]
    assert hasattr(first_att, 'content')
    assert hasattr(first_att, 'source')


def test_path_expression_with_commands(sample_pdf_path):
    """Test that path expressions with commands work end-to-end."""
    from attachments import Attachments
    
    # Create with path expression
    ctx = Attachments(f"{sample_pdf_path}[pages: 1]")
    
    assert len(ctx) == 1
    assert len(ctx.text) > 0


def test_multiple_dispatch_system():
    """Test that the multiple dispatch system works correctly."""
    from attachments.core import present
    import pandas as pd
    import numpy as np
    from PIL import Image
    
    # Test with DataFrame
    df = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
    text_result = present.text(df)
    assert isinstance(text_result, str)
    
    # Test with numpy array  
    arr = np.array([1, 2, 3])
    md_result = present.markdown(arr)
    assert isinstance(md_result, str)
    assert "```" in md_result


def test_decorator_registration():
    """Test that decorators properly register components."""
    from attachments.core.decorators import loader, presenter, modifier, adapter
    from attachments.core import load, present, modify, adapt
    
    # Test custom loader registration
    @loader(lambda path: path.endswith('.test'))
    def test_loader(path):
        return f"loaded:{path}"
    
    assert hasattr(load, 'test_loader')
    
    # Test custom presenter registration
    @presenter
    def test_presenter(content: str) -> str:
        return f"presented:{content}"
    
    assert hasattr(present, 'test_presenter')


# Fixtures for test data
@pytest.fixture
def sample_pdf_path():
    """Path to a sample PDF file."""
    return "examples/sample.pdf"


@pytest.fixture 
def sample_csv_path(tmp_path):
    """Create a sample CSV file."""
    csv_file = tmp_path / "sample.csv"
    df = pd.DataFrame({
        "Name": ["Alice", "Bob", "Charlie"],
        "Age": [25, 30, 35],
        "City": ["New York", "San Francisco", "Seattle"]
    })
    df.to_csv(csv_file, index=False)
    return str(csv_file)


@pytest.fixture
def sample_image_path(tmp_path):
    """Create a sample image file."""
    from PIL import Image
    
    img = Image.new('RGB', (100, 100), color='red')
    img_file = tmp_path / "sample.png"
    img.save(img_file)
    return str(img_file) 