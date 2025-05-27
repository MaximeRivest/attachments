"""Test API methods mentioned in README."""

import pytest
import tempfile
from pathlib import Path

from attachments import Attachments


@pytest.fixture
def text_file():
    """Create a temporary text file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("Hello world test content")
        yield f.name
    Path(f.name).unlink(missing_ok=True)


def test_claude_method_exists(text_file):
    """Test that .claude() method exists and returns expected format."""
    ctx = Attachments(text_file)
    result = ctx.claude("Test prompt")
    
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["role"] == "user"
    assert "content" in result[0]


def test_openai_chat_method_exists(text_file):
    """Test that .openai_chat() method exists and returns expected format."""
    ctx = Attachments(text_file)
    result = ctx.openai_chat("Test prompt")
    
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["role"] == "user"
    assert "content" in result[0]


def test_openai_alias_method_exists(text_file):
    """Test that .openai() method exists as alias."""
    ctx = Attachments(text_file)
    result = ctx.openai("Test prompt")
    
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["role"] == "user"
    assert "content" in result[0]


def test_openai_responses_method_exists(text_file):
    """Test that .openai_responses() method exists and has different format."""
    ctx = Attachments(text_file)
    result = ctx.openai_responses("Test prompt")
    
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["role"] == "user"
    assert "content" in result[0]


def test_openai_formats_are_different(text_file):
    """Test that openai_chat and openai_responses have different formats."""
    ctx = Attachments(text_file)
    
    chat_result = ctx.openai_chat("Test prompt")
    responses_result = ctx.openai_responses("Test prompt")
    
    # Both should be valid lists
    assert isinstance(chat_result, list)
    assert isinstance(responses_result, list)
    
    # Get the content arrays
    chat_content = chat_result[0]["content"]
    responses_content = responses_result[0]["content"]
    
    # Find text content in both
    chat_text = next((item for item in chat_content if item.get("type") == "text"), None)
    responses_text = next((item for item in responses_content if item.get("type") == "input_text"), None)
    
    # Chat format should use "text" type
    assert chat_text is not None
    assert chat_text["type"] == "text"
    
    # Responses format should use "input_text" type
    assert responses_text is not None
    assert responses_text["type"] == "input_text"


def test_dspy_method_exists(text_file):
    """Test that .dspy() method exists."""
    ctx = Attachments(text_file)
    result = ctx.dspy()
    
    # Should return either a DSPy object or a dict fallback
    assert result is not None
    # If it's a dict (fallback), check structure
    if isinstance(result, dict):
        assert "text" in result
        assert "images" in result
        assert "_type" in result


def test_basic_properties(text_file):
    """Test basic properties mentioned in README."""
    ctx = Attachments(text_file)
    
    # Test .text property
    assert isinstance(ctx.text, str)
    assert len(ctx.text) > 0
    
    # Test .images property
    assert isinstance(ctx.images, list)
    
    # Test str() conversion
    text_output = str(ctx)
    assert isinstance(text_output, str)
    assert len(text_output) > 0


def test_multiple_files_api():
    """Test API with multiple files."""
    files = []
    try:
        # Create two test files
        for i in range(2):
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                f.write(f"Test content {i}")
                files.append(f.name)
        
        ctx = Attachments(*files)
        
        # Test that all API methods work with multiple files
        claude_result = ctx.claude("Analyze these files")
        openai_result = ctx.openai_chat("Analyze these files")
        dspy_result = ctx.dspy()
        
        assert isinstance(claude_result, list)
        assert isinstance(openai_result, list)
        assert dspy_result is not None
        
    finally:
        for file_path in files:
            Path(file_path).unlink(missing_ok=True) 