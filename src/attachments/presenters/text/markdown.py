"""Markdown presenters for various data types."""

from ...core import Attachment, presenter


@presenter
def markdown(att: Attachment, df: 'pandas.DataFrame') -> Attachment:
    """Convert pandas DataFrame to markdown table."""
    try:
        att.text += f"## Data from {att.path}\n\n"
        att.text += df.to_markdown(index=False)
        att.text += f"\n\n*Shape: {df.shape}*\n\n"
    except:
        att.text += f"## Data from {att.path}\n\n*Could not convert to markdown*\n\n"
    return att


@presenter
def markdown(att: Attachment, pdf: 'pdfplumber.PDF') -> Attachment:
    """Convert PDF to markdown with text extraction. Handles scanned PDFs gracefully."""
    # Use display_url from metadata if available (for URLs), otherwise use path
    display_path = att.metadata.get('display_url', att.path)
    att.text += f"# PDF Document: {display_path}\n\n"
    
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
                    att.text += f"## Page {page_num}\n\n{page_text}\n\n"
                else:
                    # For pages with no text, add a placeholder
                    att.text += f"## Page {page_num}\n\n*[No extractable text - likely scanned image]*\n\n"
        
        # Detect if this is likely a scanned PDF
        avg_text_per_page = total_text_length / len(pages_to_process) if pages_to_process else 0
        is_likely_scanned = (
            pages_with_text == 0 or  # No pages have text
            avg_text_per_page < 50 or  # Very little text per page
            pages_with_text / len(pages_to_process) < 0.3  # Less than 30% of pages have text
        )
        
        if is_likely_scanned:
            att.text += f"\n📄 **Document Analysis**: This appears to be a scanned PDF with little to no extractable text.\n\n"
            att.text += f"- **Pages processed**: {len(pages_to_process)}\n"
            att.text += f"- **Pages with text**: {pages_with_text}\n"
            att.text += f"- **Average text per page**: {avg_text_per_page:.0f} characters\n\n"
            att.text += f"💡 **Suggestions**:\n"
            att.text += f"- Use the extracted images for vision-capable LLMs (Claude, GPT-4V)\n"
            att.text += f"- Consider OCR tools like `pytesseract` for text extraction\n"
            att.text += f"- The images are available in the `images` property for multimodal analysis\n\n"
            
            # Add metadata to help downstream processing
            att.metadata.update({
                'is_likely_scanned': True,
                'pages_with_text': pages_with_text,
                'total_pages': len(pages_to_process),
                'avg_text_per_page': avg_text_per_page,
                'text_extraction_quality': 'poor' if avg_text_per_page < 20 else 'limited'
            })
        else:
            att.text += f"*Total pages processed: {len(pages_to_process)}*\n\n"
            att.metadata.update({
                'is_likely_scanned': False,
                'pages_with_text': pages_with_text,
                'total_pages': len(pages_to_process),
                'avg_text_per_page': avg_text_per_page,
                'text_extraction_quality': 'good'
            })
            
    except Exception as e:
        att.text += f"*Error extracting PDF text: {e}*\n\n"
    
    return att


@presenter
def markdown(att: Attachment, pres: 'pptx.Presentation') -> Attachment:
    """Convert PowerPoint to markdown with slide content."""
    att.text += f"# Presentation: {att.path}\n\n"
    
    try:
        slide_indices = att.metadata.get('selected_slides', range(len(pres.slides)))
        
        for i, slide_idx in enumerate(slide_indices):
            if 0 <= slide_idx < len(pres.slides):
                slide = pres.slides[slide_idx]
                att.text += f"## Slide {slide_idx + 1}\n\n"
                
                for shape in slide.shapes:
                    if hasattr(shape, 'text') and shape.text.strip():
                        att.text += f"{shape.text}\n\n"
        
        att.text += f"*Slides processed: {len(slide_indices)}*\n\n"
    except Exception as e:
        att.text += f"*Error extracting slides: {e}*\n\n"
    
    return att


@presenter
def markdown(att: Attachment, img: 'PIL.Image.Image') -> Attachment:
    """Convert image to markdown with metadata."""
    att.text += f"# Image: {att.path}\n\n"
    try:
        att.text += f"- **Format**: {getattr(img, 'format', 'Unknown')}\n"
        att.text += f"- **Size**: {getattr(img, 'size', 'Unknown')}\n"
        att.text += f"- **Mode**: {getattr(img, 'mode', 'Unknown')}\n\n"
        att.text += "*Image converted to base64 and available in images list*\n\n"
    except:
        att.text += "*Image metadata not available*\n\n"
    return att


@presenter
def markdown(att: Attachment, doc: 'docx.Document') -> Attachment:
    """Convert DOCX document to markdown with basic formatting."""
    att.text += f"# Document: {att.path}\n\n"
    
    try:
        # Extract text from all paragraphs with basic formatting
        for paragraph in doc.paragraphs:
            if paragraph.text.strip():
                # Check if paragraph has heading style
                if paragraph.style.name.startswith('Heading'):
                    # Extract heading level from style name
                    try:
                        level = int(paragraph.style.name.split()[-1])
                        heading_prefix = "#" * min(level + 1, 6)  # Limit to h6
                        att.text += f"{heading_prefix} {paragraph.text}\n\n"
                    except:
                        # If we can't parse the heading level, treat as h2
                        att.text += f"## {paragraph.text}\n\n"
                else:
                    # Regular paragraph
                    att.text += f"{paragraph.text}\n\n"
        
        # Add document metadata
        att.text += f"*Document processed: {len(doc.paragraphs)} paragraphs*\n\n"
        
    except Exception as e:
        att.text += f"*Error extracting DOCX content: {e}*\n\n"
    
    return att


@presenter
def markdown(att: Attachment, workbook: 'openpyxl.Workbook') -> Attachment:
    """Convert Excel workbook to markdown with sheet summaries and basic table previews."""
    att.text += f"# Workbook: {att.path}\n\n"
    
    try:
        # Get selected sheets (respects pages DSL command for sheet selection)
        sheet_indices = att.metadata.get('selected_sheets', range(len(workbook.worksheets)))
        
        for i, sheet_idx in enumerate(sheet_indices):
            if 0 <= sheet_idx < len(workbook.worksheets):
                sheet = workbook.worksheets[sheet_idx]
                att.text += f"## Sheet {sheet_idx + 1}: {sheet.title}\n\n"
                
                # Get sheet dimensions
                max_row = sheet.max_row
                max_col = sheet.max_column
                att.text += f"**Dimensions**: {max_row} rows × {max_col} columns\n\n"
                
                # Create a markdown table with all data
                if max_row > 0 and max_col > 0:
                    att.text += "**Data**:\n\n"
                    
                    # Build markdown table with all data
                    table_rows = []
                    for row_idx in range(1, max_row + 1):
                        row_data = []
                        for col_idx in range(1, max_col + 1):
                            cell = sheet.cell(row=row_idx, column=col_idx)
                            # Format cell value for markdown table
                            value = str(cell.value) if cell.value is not None else ""
                            value = value.replace("|", "\\|").replace("\n", " ")
                            row_data.append(value)
                        table_rows.append(row_data)
                    
                    if table_rows:
                        # Create markdown table
                        header = table_rows[0] if table_rows else [f"Col{i+1}" for i in range(max_col)]
                        att.text += "| " + " | ".join(header) + " |\n"
                        att.text += "|" + "---|" * max_col + "\n"
                        
                        for row in table_rows[1:]:
                            att.text += "| " + " | ".join(row) + " |\n"
                    
                    att.text += "\n"
                else:
                    att.text += "*Empty sheet*\n\n"
        
        att.text += f"*Workbook processed: {len(sheet_indices)} sheets*\n\n"
        
    except Exception as e:
        att.text += f"*Error extracting Excel content: {e}*\n\n"
    
    return att


@presenter  
def markdown(att: Attachment, soup: 'bs4.BeautifulSoup') -> Attachment:
    """Convert BeautifulSoup HTML to markdown format."""
    try:
        # Try to use markdownify if available for better HTML->markdown conversion
        try:
            import markdownify
            # Convert HTML to markdown with reasonable settings
            markdown_text = markdownify.markdownify(
                str(soup), 
                heading_style="ATX",  # Use # style headings
                bullets="-",          # Use - for bullets
                strip=['script', 'style']  # Remove script and style tags
            )
            att.text += markdown_text
        except ImportError:
            # Fallback: basic markdown conversion
            # Extract title
            title = soup.find('title')
            if title and title.get_text().strip():
                att.text += f"# {title.get_text().strip()}\n\n"
            
            # Extract headings and paragraphs in order
            for element in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'li', 'blockquote']):
                tag_name = element.name
                text = element.get_text().strip()
                
                if text:
                    if tag_name == 'h1':
                        att.text += f"# {text}\n\n"
                    elif tag_name == 'h2':
                        att.text += f"## {text}\n\n"
                    elif tag_name == 'h3':
                        att.text += f"### {text}\n\n"
                    elif tag_name == 'h4':
                        att.text += f"#### {text}\n\n"
                    elif tag_name == 'h5':
                        att.text += f"##### {text}\n\n"
                    elif tag_name == 'h6':
                        att.text += f"###### {text}\n\n"
                    elif tag_name == 'p':
                        att.text += f"{text}\n\n"
                    elif tag_name == 'li':
                        att.text += f"- {text}\n"
                    elif tag_name == 'blockquote':
                        att.text += f"> {text}\n\n"
            
            # Extract links
            links = soup.find_all('a', href=True)
            if links:
                att.text += "\n## Links\n\n"
                for link in links:  # Show all links
                    link_text = link.get_text().strip()
                    href = link.get('href')
                    if link_text and href:
                        att.text += f"- [{link_text}]({href})\n"
                att.text += "\n"
                
    except Exception as e:
        # Ultimate fallback
        att.text += f"# {att.path}\n\n"
        att.text += soup.get_text() + "\n\n"
        att.text += f"*Error converting to markdown: {e}*\n"
    
    return att


@presenter
def markdown(att: Attachment) -> Attachment:
    """Fallback markdown presenter for unknown types."""
    att.text += f"# {att.path}\n\n*Object type: {type(att._obj)}*\n\n"
    att.text += f"```\n{str(att._obj)}\n```\n\n"
    return att 