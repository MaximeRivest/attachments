"""Metadata and file information presenters."""

from ...core import Attachment, presenter


@presenter
def metadata(att: Attachment) -> Attachment:
    """Add attachment metadata to text (user-friendly version)."""
    try:
        # Filter metadata to show only user-relevant information
        user_friendly_keys = {
            'format', 'size', 'mode', 'content_type', 'status_code', 
            'file_size', 'pdf_pages_rendered', 'pdf_total_pages',
            'collection_size', 'from_zip', 'zip_filename',
            'docx_pages_rendered', 'docx_total_pages',
            'pptx_slides_rendered', 'pptx_total_slides',
            'excel_sheets_rendered', 'excel_total_sheets'
        }
        
        # Collect user-friendly metadata
        relevant_meta = {}
        for key, value in att.metadata.items():
            if key in user_friendly_keys:
                relevant_meta[key] = value
            elif key.endswith('_error'):
                # Show errors as they're important for users
                relevant_meta[key] = value
        
        if relevant_meta:
            meta_text = f"\n## File Info\n\n"
            for key, value in relevant_meta.items():
                # Format key names to be more readable
                display_key = key.replace('_', ' ').title()
                if key == 'size' and isinstance(value, tuple):
                    meta_text += f"- **{display_key}**: {value[0]} × {value[1]} pixels\n"
                elif key == 'pdf_pages_rendered':
                    meta_text += f"- **Pages Rendered**: {value}\n"
                elif key == 'pdf_total_pages':
                    meta_text += f"- **Total Pages**: {value}\n"
                elif key == 'docx_pages_rendered':
                    meta_text += f"- **Pages Rendered**: {value}\n"
                elif key == 'docx_total_pages':
                    meta_text += f"- **Total Pages**: {value}\n"
                elif key == 'pptx_slides_rendered':
                    meta_text += f"- **Slides Rendered**: {value}\n"
                elif key == 'pptx_total_slides':
                    meta_text += f"- **Total Slides**: {value}\n"
                elif key == 'excel_sheets_rendered':
                    meta_text += f"- **Sheets Rendered**: {value}\n"
                elif key == 'excel_total_sheets':
                    meta_text += f"- **Total Sheets**: {value}\n"
                else:
                    meta_text += f"- **{display_key}**: {value}\n"
            att.text += meta_text + "\n"
        # If no relevant metadata, don't add anything (cleaner output)
        
    except Exception as e:
        att.text += f"\n*Error displaying file info: {e}*\n\n"
    return att


@presenter
def metadata(att: Attachment, pdf: 'pdfplumber.PDF') -> Attachment:
    """Extract PDF metadata to text."""
    try:
        meta_text = f"\n## Document Metadata\n\n"
        if hasattr(pdf, 'metadata') and pdf.metadata:
            for key, value in pdf.metadata.items():
                meta_text += f"- **{key}**: {value}\n"
        else:
            meta_text += "*No metadata available*\n"
        
        att.text += meta_text + "\n"
    except Exception as e:
        att.text += f"\n*Error extracting metadata: {e}*\n\n"
    
    return att 