"""Page selection modifier for PDF documents."""

import io
from typing import List, Optional, Any

try:
    from pypdf import PdfReader, PdfWriter
    _PdfReader = PdfReader
    _PdfWriter = PdfWriter
except ImportError:
    _PdfReader = None  # type: ignore
    _PdfWriter = None  # type: ignore

try:
    import fitz
    _fitz = fitz
except ImportError:
    _fitz = None  # type: ignore

from ..core.decorators import modifier


if _PdfReader and _PdfWriter:
    @modifier
    def pages(pdf_reader: _PdfReader, page_spec: Optional[str] = None) -> _PdfReader:
        """
        Select specific pages from PDF using pypdf (MIT-compatible).
        
        Args:
            pdf_reader: pypdf PdfReader object
            page_spec: Page specification string like "1,3-5,-1" or ":3"
                      If None, uses commands from attachment
                      
        Returns:
            New PdfReader with selected pages
            
        Examples:
            pages(pdf, "1,3-5")    # Pages 1, 3, 4, 5
            pages(pdf, ":3")       # First 3 pages  
            pages(pdf, "-1")       # Last page
            pages(pdf, "N")        # Last page (alternative)
        """
        # Get page specification from attachment commands if not provided
        if page_spec is None:
            if hasattr(pdf_reader, '_attachment_commands'):
                page_spec = pdf_reader._attachment_commands.get('pages', '')
            else:
                return pdf_reader  # No page specification, return original
        
        if not page_spec:
            return pdf_reader
            
        total_pages = len(pdf_reader.pages)
        wanted_pages: List[int] = []
        
        # Parse page specification (same logic as your original transform)
        page_spec = page_spec.replace(" ", "")
        specs = page_spec.split(",")
        
        for spec in specs:
            if spec == "":  # ignore stray commas
                continue
                
            if spec.startswith(":"):  # leading range :3 == first 3 pages
                end_user_indexed = int(spec[1:]) if spec[1:] else total_pages
                end_0_indexed = min(end_user_indexed, total_pages)
                wanted_pages.extend(range(0, end_0_indexed))
                continue
                
            if spec.upper() == "N" or spec == "-1":  # Last page
                if total_pages > 0:
                    wanted_pages.append(total_pages - 1)
                continue
                
            if "-" in spec:  # Range e.g., "3-5" (pages 3, 4, 5)
                start_str, end_str = spec.split("-")
                start_0_indexed = int(start_str) - 1  # Convert to 0-indexed
                end_0_indexed = int(end_str) - 1      # Convert to 0-indexed (inclusive)
                
                if 0 <= start_0_indexed < total_pages and start_0_indexed <= end_0_indexed:
                    wanted_pages.extend(range(start_0_indexed, min(end_0_indexed + 1, total_pages)))
                continue
                
            # Single page "4" (page 4, which is index 3)
            page_0_indexed = int(spec) - 1
            if 0 <= page_0_indexed < total_pages:
                wanted_pages.append(page_0_indexed)
        
        # Remove duplicates and sort
        wanted_pages = sorted(list(set(p for p in wanted_pages if 0 <= p < total_pages)))
        
        # If no pages selected or all pages selected, return original
        if not wanted_pages or len(wanted_pages) == total_pages:
            return pdf_reader
        
        # Create new PDF with selected pages
        if _PdfWriter is None:
            raise ImportError("pypdf PdfWriter not available")
        
        writer = _PdfWriter()
        for page_index in wanted_pages:
            writer.add_page(pdf_reader.pages[page_index])
        
        # Write to in-memory stream and return new PdfReader
        output_stream = io.BytesIO()
        writer.write(output_stream)
        output_stream.seek(0)
        
        if _PdfReader is None:
            raise ImportError("pypdf PdfReader not available")
        
        return _PdfReader(output_stream)


if _fitz:
    @modifier
    def pages(pdf_doc: Any, page_spec: Optional[str] = None) -> Any:
        """
        Select specific pages from PDF using PyMuPDF/fitz (AGPL).
        
        Note: This uses AGPL-licensed PyMuPDF.
        
        Args:
            pdf_doc: fitz Document object
            page_spec: Page specification string
            
        Returns:
            New fitz Document with selected pages
        """
        if page_spec is None:
            if hasattr(pdf_doc, '_attachment_commands'):
                page_spec = pdf_doc._attachment_commands.get('pages', '')
            else:
                return pdf_doc
        
        if not page_spec:
            return pdf_doc
            
        total_pages = pdf_doc.page_count
        wanted_pages: List[int] = []
        
        # Parse page specification (same logic)
        page_spec = page_spec.replace(" ", "")
        specs = page_spec.split(",")
        
        for spec in specs:
            if spec == "":
                continue
                
            if spec.startswith(":"):
                end_user_indexed = int(spec[1:]) if spec[1:] else total_pages
                end_0_indexed = min(end_user_indexed, total_pages)
                wanted_pages.extend(range(0, end_0_indexed))
                continue
                
            if spec.upper() == "N" or spec == "-1":
                if total_pages > 0:
                    wanted_pages.append(total_pages - 1)
                continue
                
            if "-" in spec:
                start_str, end_str = spec.split("-")
                start_0_indexed = int(start_str) - 1
                end_0_indexed = int(end_str) - 1
                
                if 0 <= start_0_indexed < total_pages and start_0_indexed <= end_0_indexed:
                    wanted_pages.extend(range(start_0_indexed, min(end_0_indexed + 1, total_pages)))
                continue
                
            page_0_indexed = int(spec) - 1
            if 0 <= page_0_indexed < total_pages:
                wanted_pages.append(page_0_indexed)
        
        wanted_pages = sorted(list(set(p for p in wanted_pages if 0 <= p < total_pages)))
        
        if not wanted_pages or len(wanted_pages) == total_pages:
            return pdf_doc
        
        # Create new document with selected pages
        new_doc = _fitz.open()
        for page_index in wanted_pages:
            new_doc.insert_pdf(pdf_doc, from_page=page_index, to_page=page_index)
        
        return new_doc 