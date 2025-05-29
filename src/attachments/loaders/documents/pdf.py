"""PDF document loader using pdfplumber."""

from ...core import Attachment, loader
from ... import matchers


@loader(match=matchers.pdf_match)
def pdf_to_pdfplumber(att: Attachment) -> Attachment:
    """Load PDF using pdfplumber with automatic input source handling."""
    try:
        import pdfplumber
        
        # Use the new input_source property - no more repetitive patterns!
        pdf_source = att.input_source
        
        # Try to create a temporary PDF with CropBox defined to silence warnings
        try:
            import pypdf
            from io import BytesIO
            import tempfile
            import os
            
            # Read the PDF bytes
            if isinstance(pdf_source, str):
                # File path
                with open(pdf_source, 'rb') as f:
                    pdf_bytes = f.read()
            else:
                # BytesIO or file-like object
                pdf_source.seek(0)
                pdf_bytes = pdf_source.read()
            
            # Process with pypdf to add CropBox
            reader = pypdf.PdfReader(BytesIO(pdf_bytes))
            writer = pypdf.PdfWriter()
            
            for page in reader.pages:
                # Set CropBox to MediaBox if not already defined
                if '/CropBox' not in page:
                    page.cropbox = page.mediabox
                writer.add_page(page)
            
            # Create a temporary file with the modified PDF
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
                writer.write(temp_file)
                temp_path = temp_file.name
            
            # Open the temporary PDF with pdfplumber
            att._obj = pdfplumber.open(temp_path)
            
            # Store the temp path for cleanup later
            att.metadata['temp_pdf_path'] = temp_path
            
        except (ImportError, Exception):
            # If CropBox fix fails, fall back to direct loading
            if isinstance(pdf_source, str):
                # File path
                att._obj = pdfplumber.open(pdf_source)
            else:
                # BytesIO - pdfplumber can handle this directly
                pdf_source.seek(0)
                att._obj = pdfplumber.open(pdf_source)
            
    except ImportError:
        raise ImportError("pdfplumber is required for PDF loading. Install with: pip install pdfplumber")
    return att 