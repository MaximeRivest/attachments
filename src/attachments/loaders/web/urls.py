"""URL loaders for web content and downloadable files."""

from ...core import Attachment, loader
from ... import matchers


# Standard headers for web requests to avoid 403 errors
DEFAULT_HEADERS = {
    'User-Agent': 'Attachments-Library/1.0 (https://github.com/MaximeRivest/attachments) Python-requests'
}


@loader(match=matchers.webpage_match)
def url_to_bs4(att: Attachment) -> Attachment:
    """Load webpage URL content and parse with BeautifulSoup."""
    import requests
    from bs4 import BeautifulSoup
    
    response = requests.get(att.path, headers=DEFAULT_HEADERS, timeout=10)
    response.raise_for_status()
    
    # Parse with BeautifulSoup
    soup = BeautifulSoup(response.content, 'html.parser')
    
    # Store the soup object
    att._obj = soup
    # Store some metadata
    att.metadata.update({
        'content_type': response.headers.get('content-type', ''),
        'status_code': response.status_code,
        'original_url': att.path
    })
    
    return att


@loader(match=lambda att: att.path.startswith(('http://', 'https://')))
def url_to_response(att: Attachment) -> Attachment:
    """
    Download URL content and store as response object for smart morphing.
    
    This is the new approach that avoids hardcoded file extension lists
    and enables the morph_to_detected_type modifier to handle dispatch.
    """
    import requests
    
    response = requests.get(att.path, headers=DEFAULT_HEADERS, timeout=30)
    response.raise_for_status()
    
    # Store the response object for morphing
    att._obj = response
    att.metadata.update({
        'original_url': att.path,
        'content_type': response.headers.get('content-type', ''),
        'content_length': len(response.content),
        'status_code': response.status_code,
        'is_downloaded_url': True
    })
    
    return att


@loader(match=lambda att: att.path.startswith(('http://', 'https://')) and any(att.path.lower().endswith(ext) for ext in ['.pdf', '.pptx', '.ppt', '.docx', '.doc', '.xlsx', '.xls', '.csv', '.jpg', '.jpeg', '.png', '.gif', '.bmp']))
def url_to_file(att: Attachment) -> Attachment:
    """
    Download file from URL and delegate to appropriate loader based on file extension.
    
    DEPRECATED: This is the old hardcoded approach. Use url_to_response + morph_to_detected_type instead.
    Keeping for backward compatibility during transition.
    """
    import requests
    import tempfile
    import os
    from urllib.parse import urlparse
    from pathlib import Path
    
    # Import the specific loaders we need
    from ..documents.pdf import pdf_to_pdfplumber
    from ..documents.office import pptx_to_python_pptx, docx_to_python_docx, excel_to_openpyxl
    from ..data.csv import csv_to_pandas
    from ..media.images import image_to_pil
    
    # Parse URL to get file extension
    parsed_url = urlparse(att.path)
    url_path = parsed_url.path
    
    # Get file extension from URL
    file_ext = Path(url_path).suffix.lower()
    
    # Download the file
    response = requests.get(att.path, headers=DEFAULT_HEADERS, timeout=30)
    response.raise_for_status()
    
    # Create temporary file with correct extension
    with tempfile.NamedTemporaryFile(suffix=file_ext, delete=False) as temp_file:
        temp_file.write(response.content)
        temp_path = temp_file.name
    
    # Store original URL and temp path
    original_url = att.path
    att.path = temp_path
    att.metadata.update({
        'original_url': original_url,
        'temp_file_path': temp_path,
        'downloaded_from_url': True,
        'content_length': len(response.content),
        'content_type': response.headers.get('content-type', ''),
    })
    
    # Now delegate to the appropriate loader based on file extension
    if file_ext in ('.pdf',):
        return pdf_to_pdfplumber(att)
    elif file_ext in ('.pptx', '.ppt'):
        return pptx_to_python_pptx(att)
    elif file_ext in ('.docx', '.doc'):
        return docx_to_python_docx(att)
    elif file_ext in ('.xlsx', '.xls'):
        return excel_to_openpyxl(att)
    elif file_ext in ('.csv',):
        return csv_to_pandas(att)
    elif file_ext.lower() in ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.heic', '.heif'):
        return image_to_pil(att)
    else:
        # If we don't recognize the extension, try to guess from content-type
        content_type = response.headers.get('content-type', '').lower()
        if 'pdf' in content_type:
            return pdf_to_pdfplumber(att)
        elif 'powerpoint' in content_type or 'presentation' in content_type:
            return pptx_to_python_pptx(att)
        elif 'word' in content_type or 'document' in content_type:
            return docx_to_python_docx(att)
        elif 'excel' in content_type or 'spreadsheet' in content_type:
            return excel_to_openpyxl(att)
        else:
            # Fallback: treat as text
            att._obj = response.text
            att.text = response.text
            return att 