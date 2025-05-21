import pytest
from unittest.mock import patch, MagicMock
import io
import sys
from src.attachments.__main__ import cli
from src.attachments.registry import REGISTRY

def test_cli_no_args_dumps_registry(capsys):
    """Test that CLI with no args dumps the registry."""
    with patch.object(REGISTRY, 'dump') as mock_dump:
        with pytest.raises(SystemExit) as e:
            cli(args=[])
        assert e.value.code == 0
        mock_dump.assert_called_once()
    
    # Verify some output was captured to stdout that mentions the registry
    captured = capsys.readouterr()
    assert "[attachments] Plugin registry:" in captured.out

def test_cli_with_path(capsys):
    """Test CLI with a file path, expecting text output."""
    # Create a dummy Attachments class that doesn't depend on registry
    class DummyAttachments:
        def __init__(self, *paths):
            # Record the paths for verification
            self.paths = paths
        
        def __str__(self):
            return "This is a sample text file for testing."
        
        @property
        def images(self):
            return None
    
    # Invoke CLI with our dummy class
    with pytest.raises(SystemExit) as e:
        cli(args=['sample.txt'], attachments_cls=DummyAttachments)
    assert e.value.code == 0
    
    # Check output
    captured = capsys.readouterr()
    assert "[attachments] Text output:" in captured.out
    assert "This is a sample text file for testing." in captured.out
    assert "[attachments] 0 image(s) extracted" in captured.out

def test_cli_with_image_path(capsys):
    """Test CLI with an image path, expecting image count output."""
    # Create a dummy Attachments class for image testing
    class DummyImageAttachments:
        def __init__(self, *paths):
            # Record the paths for verification
            self.paths = paths
        
        def __str__(self):
            return "Description of image"
        
        @property
        def images(self):
            return ["data:image/png;base64,abc123"]
    
    # Invoke CLI with our dummy class
    with pytest.raises(SystemExit) as e:
        cli(args=['sample.png'], attachments_cls=DummyImageAttachments)
    assert e.value.code == 0
    
    # Check output
    captured = capsys.readouterr()
    assert "[attachments] Text output:" in captured.out
    assert "Description of image" in captured.out
    assert "[attachments] 1 image(s) extracted" in captured.out

# To run this, we might need a fixture like sample_txt if it doesn't exist
# For now, assuming sample_txt and sample_img fixtures from conftest.py 