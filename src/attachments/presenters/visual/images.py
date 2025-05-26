"""Image and visual presenters."""

import base64
import io
from ...core import Attachment, presenter


@presenter
def images(att: Attachment) -> Attachment:
    """Fallback images presenter - does nothing if no specific handler."""
    return att


@presenter
def images(att: Attachment, img: 'PIL.Image.Image') -> Attachment:
    """Convert PIL Image to base64 PNG."""
    try:
        # Check if resize was already applied by a modifier
        resize_already_applied = att.metadata.get('resize_applied', False)
        
        # Apply resize if specified in DSL commands and not already applied
        resize = att.commands.get('resize')
        if resize and not resize_already_applied:
            # Import PIL here to avoid issues with type checking
            from PIL import Image
            if 'x' in resize:
                # Format: 800x600
                w, h = map(int, resize.split('x'))
                img = img.resize((w, h), Image.Resampling.LANCZOS)
            elif resize.endswith('%'):
                # Format: 50%
                scale = int(resize[:-1]) / 100
                new_width = int(img.width * scale)
                new_height = int(img.height * scale)
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # Convert to PNG bytes
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG')
        png_bytes = img_byte_arr.getvalue()
        
        # Encode as base64 data URL
        b64_string = base64.b64encode(png_bytes).decode('utf-8')
        att.images.append(f"data:image/png;base64,{b64_string}")
        
        # Add metadata about image processing
        att.metadata.update({
            'image_format': 'PNG',
            'image_size': img.size,
            'image_mode': img.mode,
            'resize_applied': resize if resize else resize_already_applied
        })
        
        return att
        
    except Exception as e:
        # Add error info to metadata instead of failing
        att.metadata['image_processing_error'] = f"Error processing image: {e}"
        return att


@presenter
def images(att: Attachment, pdf_reader: 'pdfplumber.PDF') -> Attachment:
    """Convert PDF pages to PNG images using pypdfium2."""
    try:
        # Try to import pypdfium2
        import pypdfium2 as pdfium
    except ImportError:
        # Fallback: add error message to metadata
        att.metadata['pdf_images_error'] = "pypdfium2 not installed. Install with: pip install pypdfium2"
        return att
    
    # Get resize parameter from DSL commands
    resize = att.commands.get('resize_images') or att.commands.get('resize')
    
    images = []
    
    try:
        # Get the PDF bytes for pypdfium2
        # Check if we have a temporary PDF path (with CropBox already fixed)
        if 'temp_pdf_path' in att.metadata:
            # Use the temporary PDF file that already has CropBox defined
            with open(att.metadata['temp_pdf_path'], 'rb') as f:
                pdf_bytes = f.read()
        elif hasattr(pdf_reader, 'stream') and pdf_reader.stream:
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
            elif att.path:
                # Use the attachment path directly
                with open(att.path, 'rb') as f:
                    pdf_bytes = f.read()
            else:
                raise Exception("Cannot access PDF bytes for rendering")
        
        # Open with pypdfium2 (CropBox should already be defined if temp file was used)
        pdf_doc = pdfium.PdfDocument(pdf_bytes)
        num_pages = len(pdf_doc)
        
        # Limit to reasonable number of pages (respect pages command if present)
        if 'pages' in att.commands:
            # If pages are specified, use those
            max_pages = min(num_pages, 20)  # Still cap at 20 for safety
        else:
            # Default limit
            max_pages = min(num_pages, 10)
        
        for page_idx in range(max_pages):
            page = pdf_doc[page_idx]
            
            # Render at 2x scale for better quality
            pil_image = page.render(scale=2).to_pil()
            
            # Apply resize if specified
            if resize:
                if 'x' in resize:
                    # Format: 800x600
                    w, h = map(int, resize.split('x'))
                    pil_image = pil_image.resize((w, h))
                elif resize.endswith('%'):
                    # Format: 50%
                    scale = int(resize[:-1]) / 100
                    new_width = int(pil_image.width * scale)
                    new_height = int(pil_image.height * scale)
                    pil_image = pil_image.resize((new_width, new_height))
            
            # Convert to PNG bytes
            img_byte_arr = io.BytesIO()
            pil_image.save(img_byte_arr, format='PNG')
            png_bytes = img_byte_arr.getvalue()
            
            # Encode as base64 data URL
            b64_string = base64.b64encode(png_bytes).decode('utf-8')
            images.append(f"data:image/png;base64,{b64_string}")
        
        # Clean up PDF document
        pdf_doc.close()
        
        # Add images to attachment
        att.images.extend(images)
        
        # Add metadata about image extraction
        att.metadata.update({
            'pdf_pages_rendered': len(images),
            'pdf_total_pages': num_pages,
            'pdf_resize_applied': resize if resize else None
        })
        
        return att
        
    except Exception as e:
        # Add error info to metadata instead of failing
        att.metadata['pdf_images_error'] = f"Error rendering PDF: {e}"
        return att


@presenter
def thumbnails(att: Attachment, pdf: 'pdfplumber.PDF') -> Attachment:
    """Generate page thumbnails from PDF."""
    try:
        pages_to_process = att.metadata.get('selected_pages', range(1, min(4, len(pdf.pages) + 1)))
        
        for page_num in pages_to_process:
            if 1 <= page_num <= len(pdf.pages):
                # Placeholder for PDF page thumbnail
                att.images.append(f"thumbnail_page_{page_num}_base64_placeholder")
    except:
        pass
    
    return att


@presenter
def contact_sheet(att: Attachment, pres: 'pptx.Presentation') -> Attachment:
    """Create a contact sheet image from slides."""
    try:
        slide_indices = att.metadata.get('selected_slides', range(len(pres.slides)))
        if slide_indices:
            # Placeholder for contact sheet
            att.images.append("contact_sheet_base64_placeholder")
    except:
        pass
    
    return att 