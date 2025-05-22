"""PowerPoint file loader that loads the raw presentation object."""

from pathlib import Path
from typing import Optional

try:
    from pptx import Presentation
    _pptx_available = True
except ImportError:
    _pptx_available = False

from ..core.decorators import loader


@loader(lambda path: Path(path).suffix.lower() == '.pptx')
def pptx(path: str):
    """
    Load a PowerPoint file as a python-pptx Presentation object.
    
    This gives maximum flexibility - different presenters can then extract:
    - Markdown via markitdown
    - Raw XML structure  
    - Plain text
    - Individual slide images
    - Tables and charts
    - etc.
    
    Args:
        path: Path to the PPTX file
        
    Returns:
        python-pptx Presentation object
        
    Raises:
        ImportError: If python-pptx is not installed
        Exception: If PowerPoint file cannot be loaded
    """
    if not _pptx_available:
        raise ImportError(
            "python-pptx is required for PowerPoint loading. Install with: "
            "pip install 'attachments[extended]'"
        )
    
    from ..utils.parsing import parse_path_expression
    
    # Parse any DSL commands from the path
    actual_path, commands = parse_path_expression(path)
    
    try:
        # Load the PowerPoint file using python-pptx
        # This gives us maximum flexibility for different presenters
        presentation = Presentation(actual_path)
        return presentation
        
    except Exception as e:
        raise Exception(f"Failed to load PowerPoint {actual_path}: {e}") 