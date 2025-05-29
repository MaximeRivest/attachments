"""Image and visual presenters."""

import base64
import io
from ...core import Attachment, presenter


@presenter
def images(att: Attachment) -> Attachment:
    """Fallback images presenter - does nothing if no specific handler."""
    return att


@presenter
def images(att: Attachment, pil_image: 'PIL.Image.Image') -> Attachment:
    """Convert PIL Image to base64 data URL."""
    try:
        # Convert to RGB if necessary (from legacy implementation)
        if hasattr(pil_image, 'mode') and pil_image.mode in ('RGBA', 'P'):
            pil_image = pil_image.convert('RGB')
        
        # Convert PIL image to PNG bytes
        img_byte_arr = io.BytesIO()
        pil_image.save(img_byte_arr, format='PNG')
        png_bytes = img_byte_arr.getvalue()
        
        # Encode as base64 data URL
        b64_string = base64.b64encode(png_bytes).decode('utf-8')
        att.images.append(f"data:image/png;base64,{b64_string}")
        
        # Add metadata
        att.metadata.update({
            'image_format': getattr(pil_image, 'format', 'Unknown'),
            'image_size': getattr(pil_image, 'size', 'Unknown'),
            'image_mode': getattr(pil_image, 'mode', 'Unknown')
        })
        
    except Exception as e:
        att.metadata['image_error'] = f"Error processing image: {e}"
    
    return att


@presenter
def images(att: Attachment, doc: 'docx.Document') -> Attachment:
    """Convert DOCX pages to PNG images by converting to PDF first, then rendering."""
    try:
        # Try to import required libraries
        import pypdfium2 as pdfium
        import subprocess
        import shutil
        import tempfile
        import os
        from pathlib import Path
    except ImportError as e:
        att.metadata['docx_images_error'] = f"Required libraries not installed: {e}. Install with: pip install pypdfium2"
        return att
    
    # Get resize parameter from DSL commands
    resize = att.commands.get('resize_images')
    
    images = []
    
    try:
        # Convert DOCX to PDF first (using LibreOffice/soffice)
        def convert_docx_to_pdf(docx_path: str) -> str:
            """Convert DOCX to PDF using LibreOffice/soffice."""
            # Try to find LibreOffice or soffice
            soffice = shutil.which("libreoffice") or shutil.which("soffice")
            if not soffice:
                raise RuntimeError("LibreOffice/soffice not found. Install LibreOffice to convert DOCX to PDF.")
            
            # Create temporary directory for PDF output
            temp_dir = tempfile.mkdtemp()
            docx_path_obj = Path(docx_path)
            
            # Run LibreOffice conversion
            subprocess.run(
                [soffice, "--headless", "--convert-to", "pdf", "--outdir", temp_dir, str(docx_path_obj)],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=60  # 60 second timeout
            )
            
            # Find the generated PDF
            pdf_path = Path(temp_dir) / (docx_path_obj.stem + ".pdf")
            if not pdf_path.exists():
                raise RuntimeError(f"PDF conversion failed - output file not found: {pdf_path}")
            
            return str(pdf_path)
        
        # Convert DOCX to PDF
        if not att.path:
            raise RuntimeError("No file path available for DOCX conversion")
        
        pdf_path = convert_docx_to_pdf(att.path)
        
        try:
            # Open the PDF with pypdfium2
            pdf_doc = pdfium.PdfDocument(pdf_path)
            num_pages = len(pdf_doc)
            
            # Process all pages (no artificial limits) - respect selected_pages if set
            if hasattr(att, 'metadata') and 'selected_pages' in att.metadata:
                # Use user-specified pages
                selected_pages = att.metadata['selected_pages']
                page_indices = [p - 1 for p in selected_pages if 1 <= p <= num_pages]  # Convert to 0-based
            else:
                # Process all pages by default
                page_indices = range(num_pages)
            
            for page_idx in page_indices:
                page = pdf_doc[page_idx]
                
                # Render at 2x scale for better quality (like PDF processor)
                pil_image = page.render(scale=2).to_pil()
                
                # Apply resize if specified
                if resize:
                    if 'x' in resize:
                        # Format: 800x600
                        w, h = map(int, resize.split('x'))
                        pil_image = pil_image.resize((w, h), pil_image.Resampling.LANCZOS)
                    elif resize.endswith('%'):
                        # Format: 50%
                        scale = int(resize[:-1]) / 100
                        new_width = int(pil_image.width * scale)
                        new_height = int(pil_image.height * scale)
                        pil_image = pil_image.resize((new_width, new_height), pil_image.Resampling.LANCZOS)
                
                # Convert to PNG bytes
                img_byte_arr = io.BytesIO()
                pil_image.save(img_byte_arr, format='PNG')
                png_bytes = img_byte_arr.getvalue()
                
                # Encode as base64 data URL (consistent with PDF processor)
                b64_string = base64.b64encode(png_bytes).decode('utf-8')
                images.append(f"data:image/png;base64,{b64_string}")
            
            # Clean up PDF document
            pdf_doc.close()
            
        finally:
            # Clean up temporary PDF file
            try:
                os.unlink(pdf_path)
                os.rmdir(os.path.dirname(pdf_path))
            except:
                pass  # Ignore cleanup errors
        
        # Add images to attachment
        att.images.extend(images)
        
        # Add metadata about image extraction (consistent with PDF processor)
        att.metadata.update({
            'docx_pages_rendered': len(images),
            'docx_total_pages': num_pages,
            'docx_resize_applied': resize if resize else None,
            'docx_conversion_method': 'libreoffice_to_pdf'
        })
        
        return att
        
    except subprocess.TimeoutExpired:
        att.metadata['docx_images_error'] = "DOCX to PDF conversion timed out (>60s)"
        return att
    except subprocess.CalledProcessError as e:
        att.metadata['docx_images_error'] = f"LibreOffice conversion failed: {e}"
        return att
    except Exception as e:
        # Add error info to metadata instead of failing
        att.metadata['docx_images_error'] = f"Error rendering DOCX pages: {e}"
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
        
        # Process all pages (no artificial limits) - respect selected_pages if set
        if hasattr(att, 'metadata') and 'selected_pages' in att.metadata:
            # Use user-specified pages
            selected_pages = att.metadata['selected_pages']
            page_indices = [p - 1 for p in selected_pages if 1 <= p <= num_pages]  # Convert to 0-based
        else:
            # Process all pages by default
            page_indices = range(num_pages)
        
        for page_idx in page_indices:
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
        att.metadata['pdf_images_error'] = f"Error rendering PDF pages: {e}"
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


@presenter
def images(att: Attachment, pres: 'pptx.Presentation') -> Attachment:
    """Convert PPTX slides to PNG images by converting to PDF first, then rendering."""
    try:
        # Try to import required libraries
        import pypdfium2 as pdfium
        import subprocess
        import shutil
        import tempfile
        import os
        from pathlib import Path
    except ImportError as e:
        att.metadata['pptx_images_error'] = f"Required libraries not installed: {e}. Install with: pip install pypdfium2"
        return att
    
    # Get resize parameter from DSL commands
    resize = att.commands.get('resize_images')
    
    images = []
    
    try:
        # Convert PPTX to PDF first (using LibreOffice/soffice)
        def convert_pptx_to_pdf(pptx_path: str) -> str:
            """Convert PPTX to PDF using LibreOffice/soffice."""
            # Try to find LibreOffice or soffice
            soffice = shutil.which("libreoffice") or shutil.which("soffice")
            if not soffice:
                raise RuntimeError("LibreOffice/soffice not found. Install LibreOffice to convert PPTX to PDF.")
            
            # Create temporary directory for PDF output
            temp_dir = tempfile.mkdtemp()
            pptx_path_obj = Path(pptx_path)
            
            # Run LibreOffice conversion
            subprocess.run(
                [soffice, "--headless", "--convert-to", "pdf", "--outdir", temp_dir, str(pptx_path_obj)],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=60  # 60 second timeout
            )
            
            # Find the generated PDF
            pdf_path = Path(temp_dir) / (pptx_path_obj.stem + ".pdf")
            if not pdf_path.exists():
                raise RuntimeError(f"PDF conversion failed - output file not found: {pdf_path}")
            
            return str(pdf_path)
        
        # Convert PPTX to PDF
        if not att.path:
            raise RuntimeError("No file path available for PPTX conversion")
        
        pdf_path = convert_pptx_to_pdf(att.path)
        
        try:
            # Open the PDF with pypdfium2
            pdf_doc = pdfium.PdfDocument(pdf_path)
            num_pages = len(pdf_doc)
            
            # Process all pages (no artificial limits) - respect selected_pages if set
            if hasattr(att, 'metadata') and 'selected_pages' in att.metadata:
                # Use user-specified pages
                selected_pages = att.metadata['selected_pages']
                page_indices = [p - 1 for p in selected_pages if 1 <= p <= num_pages]  # Convert to 0-based
            else:
                # Process all pages by default
                page_indices = range(num_pages)
            
            for page_idx in page_indices:
                page = pdf_doc[page_idx]
                
                # Render at 2x scale for better quality (like PDF processor)
                pil_image = page.render(scale=2).to_pil()
                
                # Apply resize if specified
                if resize:
                    if 'x' in resize:
                        # Format: 800x600
                        w, h = map(int, resize.split('x'))
                        pil_image = pil_image.resize((w, h), pil_image.Resampling.LANCZOS)
                    elif resize.endswith('%'):
                        # Format: 50%
                        scale = int(resize[:-1]) / 100
                        new_width = int(pil_image.width * scale)
                        new_height = int(pil_image.height * scale)
                        pil_image = pil_image.resize((new_width, new_height), pil_image.Resampling.LANCZOS)
                
                # Convert to PNG bytes
                img_byte_arr = io.BytesIO()
                pil_image.save(img_byte_arr, format='PNG')
                png_bytes = img_byte_arr.getvalue()
                
                # Encode as base64 data URL (consistent with PDF processor)
                b64_string = base64.b64encode(png_bytes).decode('utf-8')
                images.append(f"data:image/png;base64,{b64_string}")
            
            # Clean up PDF document
            pdf_doc.close()
            
        finally:
            # Clean up temporary PDF file
            try:
                os.unlink(pdf_path)
                os.rmdir(os.path.dirname(pdf_path))
            except:
                pass  # Ignore cleanup errors
        
        # Add images to attachment
        att.images.extend(images)
        
        # Add metadata about image extraction (consistent with PDF processor)
        att.metadata.update({
            'pptx_slides_rendered': len(images),
            'pptx_total_slides': num_pages,
            'pptx_resize_applied': resize if resize else None,
            'pptx_conversion_method': 'libreoffice_to_pdf'
        })
        
        return att
        
    except subprocess.TimeoutExpired:
        att.metadata['pptx_images_error'] = "PPTX to PDF conversion timed out (>60s)"
        return att
    except subprocess.CalledProcessError as e:
        att.metadata['pptx_images_error'] = f"LibreOffice conversion failed: {e}"
        return att
    except Exception as e:
        # Add error info to metadata instead of failing
        att.metadata['pptx_images_error'] = f"Error rendering PPTX slides: {e}"
        return att


@presenter
def images(att: Attachment, workbook: 'openpyxl.Workbook') -> Attachment:
    """Convert Excel sheets to PNG images by converting to PDF first, then rendering."""
    try:
        # Try to import required libraries
        import pypdfium2 as pdfium
        import subprocess
        import shutil
        import tempfile
        import os
        from pathlib import Path
    except ImportError as e:
        att.metadata['excel_images_error'] = f"Required libraries not installed: {e}. Install with: pip install pypdfium2"
        return att
    
    # Get resize parameter from DSL commands
    resize = att.commands.get('resize_images')
    
    images = []
    
    try:
        # Convert Excel to PDF first (using LibreOffice/soffice)
        def convert_excel_to_pdf(excel_path: str) -> str:
            """Convert Excel to PDF using LibreOffice/soffice."""
            # Try to find LibreOffice or soffice
            soffice = shutil.which("libreoffice") or shutil.which("soffice")
            if not soffice:
                raise RuntimeError("LibreOffice/soffice not found. Install LibreOffice to convert Excel to PDF.")
            
            # Create temporary directory for PDF output
            temp_dir = tempfile.mkdtemp()
            excel_path_obj = Path(excel_path)
            
            # Run LibreOffice conversion
            subprocess.run(
                [soffice, "--headless", "--convert-to", "pdf", "--outdir", temp_dir, str(excel_path_obj)],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=60  # 60 second timeout
            )
            
            # Find the generated PDF
            pdf_path = Path(temp_dir) / (excel_path_obj.stem + ".pdf")
            if not pdf_path.exists():
                raise RuntimeError(f"PDF conversion failed - output file not found: {pdf_path}")
            
            return str(pdf_path)
        
        # Convert Excel to PDF
        if not att.path:
            raise RuntimeError("No file path available for Excel conversion")
        
        pdf_path = convert_excel_to_pdf(att.path)
        
        try:
            # Open the PDF with pypdfium2
            pdf_doc = pdfium.PdfDocument(pdf_path)
            num_pages = len(pdf_doc)
            
            # Process all pages (no artificial limits) - respect selected_pages if set
            if hasattr(att, 'metadata') and 'selected_pages' in att.metadata:
                # Use user-specified pages
                selected_pages = att.metadata['selected_pages']
                page_indices = [p - 1 for p in selected_pages if 1 <= p <= num_pages]  # Convert to 0-based
            else:
                # Process all pages by default
                page_indices = range(num_pages)
            
            for page_idx in page_indices:
                page = pdf_doc[page_idx]
                
                # Render at 2x scale for better quality (like PDF processor)
                pil_image = page.render(scale=2).to_pil()
                
                # Apply resize if specified
                if resize:
                    if 'x' in resize:
                        # Format: 800x600
                        w, h = map(int, resize.split('x'))
                        pil_image = pil_image.resize((w, h), pil_image.Resampling.LANCZOS)
                    elif resize.endswith('%'):
                        # Format: 50%
                        scale = int(resize[:-1]) / 100
                        new_width = int(pil_image.width * scale)
                        new_height = int(pil_image.height * scale)
                        pil_image = pil_image.resize((new_width, new_height), pil_image.Resampling.LANCZOS)
                
                # Convert to PNG bytes
                img_byte_arr = io.BytesIO()
                pil_image.save(img_byte_arr, format='PNG')
                png_bytes = img_byte_arr.getvalue()
                
                # Encode as base64 data URL (consistent with PDF processor)
                b64_string = base64.b64encode(png_bytes).decode('utf-8')
                images.append(f"data:image/png;base64,{b64_string}")
            
            # Clean up PDF document
            pdf_doc.close()
            
        finally:
            # Clean up temporary PDF file
            try:
                os.unlink(pdf_path)
                os.rmdir(os.path.dirname(pdf_path))
            except:
                pass  # Ignore cleanup errors
        
        # Add images to attachment
        att.images.extend(images)
        
        # Add metadata about image extraction (consistent with PDF processor)
        att.metadata.update({
            'excel_sheets_rendered': len(images),
            'excel_total_sheets': num_pages,
            'excel_resize_applied': resize if resize else None,
            'excel_conversion_method': 'libreoffice_to_pdf'
        })
        
        return att
        
    except subprocess.TimeoutExpired:
        att.metadata['excel_images_error'] = "Excel to PDF conversion timed out (>60s)"
        return att
    except subprocess.CalledProcessError as e:
        att.metadata['excel_images_error'] = f"LibreOffice conversion failed: {e}"
        return att
    except Exception as e:
        # Add error info to metadata instead of failing
        att.metadata['excel_images_error'] = f"Error rendering Excel sheets: {e}"
        return att


@presenter
def images(att: Attachment, soup: 'bs4.BeautifulSoup') -> Attachment:
    """Capture webpage screenshot using Playwright with JavaScript rendering and CSS selector highlighting."""
    # First check if Playwright is available
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        # Check if CSS selector was requested (which requires Playwright for highlighting)
        css_selector = att.commands.get('select')
        if css_selector:
            # CSS selector highlighting was requested but Playwright isn't available
            error_msg = (
                f"🎯 CSS Selector Highlighting Unavailable: You requested CSS selector highlighting "
                f"with [select:{css_selector}], but Playwright is not installed.\n\n"
                f"To enable CSS selector highlighting and webpage screenshots:\n"
                f"  pip install playwright\n"
                f"  playwright install chromium\n\n"
                f"Alternative installation methods:\n"
                f"  # With uv:\n"
                f"  uv add playwright\n"
                f"  uv run playwright install chromium\n\n"
                f"  # With attachments browser extras:\n"
                f"  pip install attachments[browser]\n"
                f"  playwright install chromium\n\n"
                f"CSS selector highlighting provides:\n"
                f"  🎯 Visual highlighting of selected elements with animations\n"
                f"  📸 High-quality screenshots with JavaScript rendering\n"
                f"  🎨 Professional styling with glowing borders and badges\n"
                f"  🔍 Perfect for extracting specific page elements"
            )
            raise ImportError(error_msg)
        else:
            # Regular screenshot was requested
            raise ImportError("Playwright not available. Install with: pip install playwright && playwright install chromium")
    
    try:
        import asyncio
        import base64
        
        # Check if we have the original URL in metadata
        if 'original_url' in att.metadata:
            url = att.metadata['original_url']
        else:
            # Try to reconstruct URL from path (fallback)
            url = att.path
        
        # Get DSL command parameters
        viewport_str = att.commands.get('viewport', '1280x720')
        fullpage = att.commands.get('fullpage', 'true').lower() == 'true'
        wait_time = int(att.commands.get('wait', '200'))
        css_selector = att.commands.get('select')  # CSS selector for highlighting
        
        # Parse viewport dimensions
        try:
            width, height = map(int, viewport_str.split('x'))
        except:
            width, height = 1280, 720  # Default fallback
        
        async def capture_screenshot(url: str) -> str:
            """Capture screenshot using Playwright with optional CSS highlighting."""
            async with async_playwright() as p:
                browser = await p.chromium.launch()
                page = await browser.new_page(viewport={"width": width, "height": height})
                
                try:
                    await page.goto(url, wait_until="networkidle")
                    await page.wait_for_timeout(wait_time)  # Let fonts/images settle
                    
                    # Check if we have a CSS selector to highlight
                    if css_selector:
                        # Inject CSS to highlight selected elements (clean visual highlighting)
                        highlight_css = """
                        <style id="attachments-highlight">
                        .attachments-highlighted {
                            border: 5px solid #ff0080 !important;
                            outline: 3px solid #ffffff !important;
                            outline-offset: 2px !important;
                            background-color: rgba(255, 0, 128, 0.1) !important;
                            box-shadow: 
                                0 0 0 8px rgba(255, 0, 128, 0.3),
                                0 0 20px rgba(255, 0, 128, 0.5),
                                inset 0 0 0 3px rgba(255, 255, 255, 0.8) !important;
                            position: relative !important;
                            z-index: 9999 !important;
                            animation: attachments-glow 2s ease-in-out infinite alternate !important;
                            margin: 10px !important;
                            padding: 10px !important;
                        }
                        @keyframes attachments-glow {
                            0% { 
                                border-color: #ff0080;
                                box-shadow: 
                                    0 0 0 8px rgba(255, 0, 128, 0.3),
                                    0 0 20px rgba(255, 0, 128, 0.5),
                                    inset 0 0 0 3px rgba(255, 255, 255, 0.8);
                                transform: scale(1);
                            }
                            100% { 
                                border-color: #ff4da6;
                                box-shadow: 
                                    0 0 0 12px rgba(255, 0, 128, 0.4),
                                    0 0 30px rgba(255, 0, 128, 0.7),
                                    inset 0 0 0 3px rgba(255, 255, 255, 1);
                                transform: scale(1.02);
                            }
                        }
                        .attachments-highlighted::before {
                            content: "";
                            position: absolute !important;
                            top: -8px !important;
                            left: -8px !important;
                            right: -8px !important;
                            bottom: -8px !important;
                            border: 3px dashed #00ff80 !important;
                            border-radius: 8px !important;
                            z-index: -1 !important;
                            animation: attachments-dash 3s linear infinite !important;
                        }
                        @keyframes attachments-dash {
                            0% { border-color: #00ff80; }
                            33% { border-color: #ff0080; }
                            66% { border-color: #0080ff; }
                            100% { border-color: #00ff80; }
                        }
                        .attachments-highlighted::after {
                            content: "🎯 SELECTED" !important;
                            position: absolute !important;
                            top: -45px !important;
                            left: 50% !important;
                            transform: translateX(-50%) !important;
                            background: linear-gradient(135deg, #ff0080, #ff4da6) !important;
                            color: white !important;
                            padding: 10px 20px !important;
                            font-size: 16px !important;
                            font-weight: bold !important;
                            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
                            border-radius: 25px !important;
                            z-index: 10001 !important;
                            white-space: nowrap !important;
                            box-shadow: 
                                0 6px 20px rgba(0,0,0,0.4),
                                0 0 0 3px rgba(255, 255, 255, 1),
                                0 0 20px rgba(255, 0, 128, 0.6) !important;
                            border: 3px solid rgba(255, 255, 255, 1) !important;
                            animation: attachments-badge-bounce 2s ease-in-out infinite !important;
                        }
                        @keyframes attachments-badge-bounce {
                            0%, 100% { transform: translateX(-50%) translateY(0px) scale(1); }
                            50% { transform: translateX(-50%) translateY(-5px) scale(1.05); }
                        }
                        /* Special styling for multiple elements */
                        .attachments-highlighted.multiple-selection::after {
                            background: linear-gradient(135deg, #00ff80, #26ff9a) !important;
                        }
                        .attachments-highlighted.multiple-selection::before {
                            border-style: solid !important;
                            border-width: 4px !important;
                        }
                        /* Ensure visibility over any background */
                        .attachments-highlighted {
                            backdrop-filter: blur(2px) contrast(1.2) !important;
                        }
                        /* Make sure text inside highlighted elements is readable */
                        .attachments-highlighted * {
                            text-shadow: 0 0 5px rgba(255, 255, 255, 1) !important;
                        }
                        /* Add a pulsing outer glow */
                        .attachments-highlighted {
                            filter: drop-shadow(0 0 15px rgba(255, 0, 128, 0.8)) !important;
                        }
                        </style>
                        """
                        
                        # Inject the CSS
                        await page.add_style_tag(content=highlight_css)
                        
                        # Add highlighting class to selected elements
                        highlight_script = f"""
                        try {{
                            const elements = document.querySelectorAll('{css_selector}');
                            elements.forEach((el, index) => {{
                                el.classList.add('attachments-highlighted');
                                
                                // Add special class for multiple selections
                                if (elements.length > 1) {{
                                    el.classList.add('multiple-selection');
                                    // Create a unique style for each element's counter
                                    const style = document.createElement('style');
                                    const uniqueClass = 'attachments-element-' + index;
                                    el.classList.add(uniqueClass);
                                    style.textContent = 
                                        '.' + uniqueClass + '::after {{' +
                                        'content: "🎯 ' + el.tagName.toUpperCase() + ' (' + (index + 1) + '/' + elements.length + ')" !important;' +
                                        '}}';
                                    document.head.appendChild(style);
                                }} else {{
                                    // Single element - show tag name in badge
                                    const style = document.createElement('style');
                                    const uniqueClass = 'attachments-element-' + index;
                                    el.classList.add(uniqueClass);
                                    style.textContent = 
                                        '.' + uniqueClass + '::after {{' +
                                        'content: "🎯 ' + el.tagName.toUpperCase() + ' SELECTED" !important;' +
                                        '}}';
                                    document.head.appendChild(style);
                                }}
                                
                                // Scroll the first element into view for better visibility
                                if (index === 0) {{
                                    el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                                }}
                            }});
                            
                            console.log('Highlighted ' + elements.length + ' elements with selector: {css_selector}');
                            elements.length;
                        }} catch (e) {{
                            console.error('Error highlighting elements:', e);
                            0;
                        }}
                        """
                        
                        element_count = await page.evaluate(highlight_script)
                        
                        # Wait longer for highlighting and animations to render
                        await page.wait_for_timeout(500)
                        
                        # Store highlighting info in metadata
                        att.metadata.update({
                            'highlighted_selector': css_selector,
                            'highlighted_elements': element_count
                        })
                    
                    # Capture screenshot
                    png_bytes = await page.screenshot(full_page=fullpage)
                    
                    # Encode as base64 data URL
                    b64_string = base64.b64encode(png_bytes).decode('utf-8')
                    return f"data:image/png;base64,{b64_string}"
                    
                finally:
                    await browser.close()
        
        # Capture the screenshot with proper async handling for Jupyter
        try:
            # Check if we're already in an event loop (like in Jupyter)
            try:
                loop = asyncio.get_running_loop()
                # We're in an event loop (Jupyter), use nest_asyncio or create_task
                try:
                    import nest_asyncio
                    nest_asyncio.apply()
                    screenshot_data = asyncio.run(capture_screenshot(url))
                except ImportError:
                    # nest_asyncio not available, try alternative approach
                    # Create a new thread to run the async code
                    import concurrent.futures
                    import threading
                    
                    def run_in_thread():
                        # Create a new event loop in this thread
                        new_loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(new_loop)
                        try:
                            return new_loop.run_until_complete(capture_screenshot(url))
                        finally:
                            new_loop.close()
                    
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(run_in_thread)
                        screenshot_data = future.result(timeout=30)  # 30 second timeout
                        
            except RuntimeError:
                # No event loop running, safe to use asyncio.run()
                screenshot_data = asyncio.run(capture_screenshot(url))
            
            att.images.append(screenshot_data)
            
            # Add metadata about screenshot
            att.metadata.update({
                'screenshot_captured': True,
                'screenshot_viewport': f"{width}x{height}",
                'screenshot_fullpage': fullpage,
                'screenshot_wait_time': wait_time,
                'screenshot_url': url
            })
            
        except Exception as e:
            # Add error info to metadata instead of failing
            att.metadata['screenshot_error'] = f"Error capturing screenshot: {str(e)}"
        
        return att
        
    except Exception as e:
        att.metadata['screenshot_error'] = f"Error setting up screenshot: {str(e)}"
        return att 