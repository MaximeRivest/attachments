"""Image presenters for various content types."""

import base64
import io
from typing import List, Any

try:
    from pypdf import PdfReader
    _PdfReader = PdfReader
except ImportError:
    _PdfReader = None  # type: ignore

try:
    import pypdfium2 as pdfium
    _pdfium = pdfium
except ImportError:
    _pdfium = None  # type: ignore

try:
    import fitz
    _fitz = fitz
except ImportError:
    _fitz = None  # type: ignore

try:
    from PIL import Image
    _Image = Image
except ImportError:
    _Image = None  # type: ignore

from ..core.decorators import presenter
# PowerPointContent removed - now we load raw pptx.Presentation objects
from ..modifiers.tile import TiledContent


@presenter
def images(tiled: TiledContent) -> List[str]:
    """Extract images from TiledContent, prioritizing the contact sheet."""
    return tiled.images  # Already ordered: [tiled_image] + individual_images


# PowerPoint images presenter removed - raw pptx.Presentation objects 
# don't contain embedded images in the same way. Individual slide images
# can be rendered using pypdfium2 or similar tools if needed.


if _Image:
    @presenter
    def images(pil_image: _Image.Image) -> List[str]:
        """Convert PIL Image to base64 data URL."""
        img_byte_arr = io.BytesIO()
        # Convert to PNG for consistency
        if pil_image.mode in ('RGBA', 'LA'):
            pil_image.save(img_byte_arr, format='PNG')
        else:
            pil_image = pil_image.convert('RGB')
            pil_image.save(img_byte_arr, format='PNG')
        
        png_bytes = img_byte_arr.getvalue()
        b64_string = base64.b64encode(png_bytes).decode('utf-8')
        return [f"data:image/png;base64,{b64_string}"]


if _PdfReader and _pdfium:
    @presenter
    def images(pdf_reader: _PdfReader) -> List[str]:
        """
        Convert PDF pages to PNG images using pypdfium2 (MIT-compatible).
        
        Args:
            pdf_reader: pypdf PdfReader object
            
        Returns:
            List of base64-encoded PNG data URLs
        """
        images = []
        
        try:
            # Get the PDF bytes for pypdfium2
            if hasattr(pdf_reader, 'stream') and pdf_reader.stream:
                # Save current position
                original_pos = pdf_reader.stream.tell()
                # Read the PDF bytes
                pdf_reader.stream.seek(0)
                pdf_bytes = pdf_reader.stream.read()
                # Restore position
                pdf_reader.stream.seek(original_pos)
            else:
                # Try to get bytes from the file path if available
                if hasattr(pdf_reader, 'stream') and hasattr(pdf_reader.stream, 'name'):
                    with open(pdf_reader.stream.name, 'rb') as f:
                        pdf_bytes = f.read()
                else:
                    raise Exception("Cannot access PDF bytes for rendering")
            
            # Open with pypdfium2
            pdf_doc = _pdfium.PdfDocument(pdf_bytes)
            num_pages = len(pdf_doc)
            
            # Limit to reasonable number of pages
            max_pages = min(num_pages, 10)
            
            for page_idx in range(max_pages):
                page = pdf_doc[page_idx]
                
                # Render at 2x scale for better quality
                pil_image = page.render(scale=2).to_pil()
                
                # Convert to PNG bytes
                img_byte_arr = io.BytesIO()
                pil_image.save(img_byte_arr, format='PNG')
                png_bytes = img_byte_arr.getvalue()
                
                # Encode as base64 data URL
                b64_string = base64.b64encode(png_bytes).decode('utf-8')
                images.append(f"data:image/png;base64,{b64_string}")
                
                # Clean up
                page.close()
            
            pdf_doc.close()
            return images
            
        except Exception as e:
            # Fallback: return empty list with error info
            return [f"data:text/plain;base64,{base64.b64encode(f'Error rendering PDF: {e}'.encode()).decode()}"]


if _fitz:  # PyMuPDF fallback (AGPL)
    @presenter
    def images(pdf_doc: _fitz.Document) -> List[str]:
        """
        Convert PDF pages to PNG images using PyMuPDF (AGPL license).
        
        Args:
            pdf_doc: PyMuPDF Document object
            
        Returns:
            List of base64-encoded PNG data URLs
        """
        images = []
        
        try:
            # Limit to reasonable number of pages
            max_pages = min(len(pdf_doc), 10)
            
            for page_num in range(max_pages):
                page = pdf_doc[page_num]
                
                # Render at 2x scale for better quality
                mat = _fitz.Matrix(2, 2)
                pix = page.get_pixmap(matrix=mat)
                
                # Convert to PNG bytes
                png_bytes = pix.tobytes("png")
                
                # Encode as base64 data URL
                b64_string = base64.b64encode(png_bytes).decode('utf-8')
                images.append(f"data:image/png;base64,{b64_string}")
            
            return images
            
        except Exception as e:
            # Fallback: return empty list with error info
            return [f"data:text/plain;base64,{base64.b64encode(f'Error rendering PDF: {e}'.encode()).decode()}"]


@presenter
def images(content: object) -> List[str]:
    """Fallback: cannot generate images from this content type."""
    return [] 