"""Plain text presenters for various data types."""

from ...core import Attachment, presenter


@presenter
def text(att: Attachment, df: 'pandas.DataFrame') -> Attachment:
    """Convert pandas DataFrame to plain text."""
    try:
        att.text += f"Data from {att.path}\n"
        att.text += "=" * len(f"Data from {att.path}") + "\n\n"
        att.text += df.to_string(index=False)
        att.text += f"\n\nShape: {df.shape}\n\n"
    except:
        att.text += f"Data from {att.path}\n*Could not convert to text*\n\n"
    return att


@presenter
def text(att: Attachment, pdf: 'pdfplumber.PDF') -> Attachment:
    """Extract plain text from PDF. Handles scanned PDFs gracefully."""
    # Use display_url from metadata if available (for URLs), otherwise use path
    display_path = att.metadata.get('display_url', att.path)
    att.text += f"PDF Document: {display_path}\n"
    att.text += "=" * len(f"PDF Document: {display_path}") + "\n\n"
    
    try:
        # Process ALL pages by default, or only selected pages if specified
        if 'selected_pages' in att.metadata:
            pages_to_process = att.metadata['selected_pages']
        else:
            # Process ALL pages by default
            pages_to_process = range(1, len(pdf.pages) + 1)
        
        total_text_length = 0
        pages_with_text = 0
        
        for page_num in pages_to_process:
            if 1 <= page_num <= len(pdf.pages):
                page = pdf.pages[page_num - 1]
                page_text = page.extract_text() or ""
                
                # Track text statistics
                if page_text.strip():
                    pages_with_text += 1
                    total_text_length += len(page_text.strip())
                
                # Only add page content if there's meaningful text
                if page_text.strip():
                    att.text += f"[Page {page_num}]\n{page_text}\n\n"
                else:
                    # For pages with no text, add a placeholder
                    att.text += f"[Page {page_num}]\n[No extractable text - likely scanned image]\n\n"
        
        # Detect if this is likely a scanned PDF (same logic as markdown presenter)
        avg_text_per_page = total_text_length / len(pages_to_process) if pages_to_process else 0
        is_likely_scanned = (
            pages_with_text == 0 or  # No pages have text
            avg_text_per_page < 50 or  # Very little text per page
            pages_with_text / len(pages_to_process) < 0.3  # Less than 30% of pages have text
        )
        
        if is_likely_scanned:
            att.text += f"\nDOCUMENT ANALYSIS: This appears to be a scanned PDF with little to no extractable text.\n\n"
            att.text += f"- Pages processed: {len(pages_to_process)}\n"
            att.text += f"- Pages with text: {pages_with_text}\n"
            att.text += f"- Average text per page: {avg_text_per_page:.0f} characters\n\n"
            att.text += f"SUGGESTIONS:\n"
            att.text += f"- Use the extracted images for vision-capable LLMs (Claude, GPT-4V)\n"
            att.text += f"- Consider OCR tools like pytesseract for text extraction\n"
            att.text += f"- The images are available in the images property for multimodal analysis\n\n"
            
            # Add metadata to help downstream processing (if not already added by markdown presenter)
            if 'is_likely_scanned' not in att.metadata:
                att.metadata.update({
                    'is_likely_scanned': True,
                    'pages_with_text': pages_with_text,
                    'total_pages': len(pages_to_process),
                    'avg_text_per_page': avg_text_per_page,
                    'text_extraction_quality': 'poor' if avg_text_per_page < 20 else 'limited'
                })
        else:
            # Add metadata for good text extraction (if not already added)
            if 'is_likely_scanned' not in att.metadata:
                att.metadata.update({
                    'is_likely_scanned': False,
                    'pages_with_text': pages_with_text,
                    'total_pages': len(pages_to_process),
                    'avg_text_per_page': avg_text_per_page,
                    'text_extraction_quality': 'good'
                })
                
    except:
        att.text += "*Error extracting PDF text*\n\n"
    
    return att


@presenter
def text(att: Attachment, soup: 'bs4.BeautifulSoup') -> Attachment:
    """Extract text from BeautifulSoup object with proper spacing."""
    # Use space separator to ensure proper spacing between elements
    att.text += soup.get_text(separator=' ', strip=True)
    return att


@presenter
def html(att: Attachment, soup: 'bs4.BeautifulSoup') -> Attachment:
    """Get formatted HTML from BeautifulSoup object."""
    att.text += soup.prettify()
    return att


@presenter
def text(att: Attachment, pres: 'pptx.Presentation') -> Attachment:
    """Extract plain text from PowerPoint slides."""
    att.text += f"Presentation: {att.path}\n"
    att.text += "=" * len(f"Presentation: {att.path}") + "\n\n"
    
    try:
        slide_indices = att.metadata.get('selected_slides', range(len(pres.slides)))
        
        for i, slide_idx in enumerate(slide_indices):
            if 0 <= slide_idx < len(pres.slides):
                slide = pres.slides[slide_idx]
                att.text += f"[Slide {slide_idx + 1}]\n"
                
                slide_text = ""
                for shape in slide.shapes:
                    if hasattr(shape, 'text') and shape.text.strip():
                        slide_text += f"{shape.text}\n"
                
                if slide_text.strip():
                    att.text += f"{slide_text}\n"
                else:
                    att.text += "[No text content]\n\n"
        
        att.text += f"Slides processed: {len(slide_indices)}\n\n"
    except Exception as e:
        att.text += f"Error extracting slides: {e}\n\n"
    
    return att


@presenter
def text(att: Attachment, doc: 'docx.Document') -> Attachment:
    """Extract plain text from DOCX document."""
    att.text += f"Document: {att.path}\n"
    att.text += "=" * len(f"Document: {att.path}") + "\n\n"
    
    try:
        # Extract text from all paragraphs
        for paragraph in doc.paragraphs:
            if paragraph.text.strip():
                att.text += f"{paragraph.text}\n\n"
        
        # Add basic document info
        att.text += f"*Document processed: {len(doc.paragraphs)} paragraphs*\n\n"
        
    except Exception as e:
        att.text += f"*Error extracting DOCX text: {e}*\n\n"
    
    return att


@presenter
def text(att: Attachment, workbook: 'openpyxl.Workbook') -> Attachment:
    """Extract plain text summary from Excel workbook."""
    att.text += f"Workbook: {att.path}\n"
    att.text += "=" * len(f"Workbook: {att.path}") + "\n\n"
    
    try:
        # Get selected sheets (respects pages DSL command for sheet selection)
        sheet_indices = att.metadata.get('selected_sheets', range(len(workbook.worksheets)))
        
        for i, sheet_idx in enumerate(sheet_indices):
            if 0 <= sheet_idx < len(workbook.worksheets):
                sheet = workbook.worksheets[sheet_idx]
                att.text += f"[Sheet {sheet_idx + 1}: {sheet.title}]\n"
                
                # Get sheet dimensions
                max_row = sheet.max_row
                max_col = sheet.max_column
                att.text += f"Dimensions: {max_row} rows × {max_col} columns\n"
                
                # Show all rows
                for row_idx in range(1, max_row + 1):
                    row_data = []
                    for col_idx in range(1, max_col + 1):
                        cell = sheet.cell(row=row_idx, column=col_idx)
                        value = str(cell.value) if cell.value is not None else ""
                        row_data.append(value)
                    att.text += f"Row {row_idx}: {' | '.join(row_data)}\n"
                
                att.text += "\n"
        
        att.text += f"*Workbook processed: {len(sheet_indices)} sheets*\n\n"
        
    except Exception as e:
        att.text += f"*Error extracting Excel content: {e}*\n\n"
    
    return att


@presenter
def text(att: Attachment) -> Attachment:
    """Fallback text presenter for unknown types."""
    # Append to existing text instead of overwriting it
    # This preserves warnings and other content added by previous presenters
    att.text += f"{att.path}: {str(att._obj)}\n\n"
    return att 