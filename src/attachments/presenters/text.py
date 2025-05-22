"""Text presenters for various content types."""

import pandas as pd
import numpy as np
from typing import Any

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

try:
    import fitz
except ImportError:
    fitz = None

from ..core.decorators import presenter


@presenter
def text(content: str) -> str:
    """Extract text from string content."""
    return content


@presenter
def text(content: pd.DataFrame) -> str:
    """Extract text representation from DataFrame."""
    return content.to_string()


@presenter
def text(content: np.ndarray) -> str:
    """Extract text representation from numpy array."""
    return str(content)


if PdfReader:
    @presenter
    def text(pdf_reader: PdfReader) -> str:
        """
        Extract text from PDF using pypdf (MIT-compatible).
        
        Args:
            pdf_reader: pypdf PdfReader object
            
        Returns:
            Extracted text from all pages
        """
        texts = []
        try:
            for page_num, page in enumerate(pdf_reader.pages):
                try:
                    page_text = page.extract_text()
                    if page_text.strip():
                        texts.append(f"=== Page {page_num + 1} ===\n{page_text.strip()}")
                except Exception as e:
                    texts.append(f"=== Page {page_num + 1} ===\n[Error extracting text: {e}]")
            
            return "\n\n".join(texts) if texts else "[No text found in PDF]"
            
        except Exception as e:
            return f"[Error reading PDF: {e}]"


if fitz:
    @presenter
    def text(pdf_doc: fitz.Document) -> str:
        """
        Extract text from PDF using PyMuPDF/fitz (AGPL).
        
        Note: This uses AGPL-licensed PyMuPDF.
        
        Args:
            pdf_doc: fitz Document object
            
        Returns:
            Extracted text from all pages
        """
        texts = []
        try:
            for page_num in range(pdf_doc.page_count):
                page = pdf_doc[page_num]
                page_text = page.get_text()
                if page_text.strip():
                    texts.append(f"=== Page {page_num + 1} ===\n{page_text.strip()}")
            
            return "\n\n".join(texts) if texts else "[No text found in PDF]"
            
        except Exception as e:
            return f"[Error reading PDF: {e}]"


@presenter  
def text(content: Any) -> str:
    """Fallback text presenter for any content type."""
    return str(content) 