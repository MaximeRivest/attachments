"""PDF file loader using pypdf (BSD license, MIT-compatible)."""

from pathlib import Path
from typing import Optional

try:
    from pypdf import PdfReader
    _PdfReader = PdfReader
except ImportError:
    _PdfReader = None  # type: ignore

from ..core.decorators import loader


@loader(lambda path: Path(path).suffix.lower() == '.pdf')
def pdf(path: str):
    """
    Load a PDF file using pypdf (BSD license).
    
    Args:
        path: Path to the PDF file
        
    Returns:
        Attachment with PdfReader content
        
    Raises:
        ImportError: If pypdf is not installed
        Exception: If PDF cannot be loaded
    """
    if _PdfReader is None:
        raise ImportError(
            "pypdf is required for PDF loading. Install with: pip install 'attachments[pdf]'"
        )
    
    from ..core.attachment import Attachment
    from ..utils.parsing import parse_path_expression
    
    # Parse any DSL commands from the path
    actual_path, commands = parse_path_expression(path)
    
    try:
        # Load the PDF using pypdf
        pdf_reader = _PdfReader(actual_path)
        
        # Return just the PdfReader - decorator will wrap it
        return pdf_reader
        
    except Exception as e:
        raise Exception(f"Failed to load PDF {actual_path}: {e}")