"""Text and HTML document loaders."""

from ...core import Attachment, loader
from ... import matchers


@loader(match=matchers.text_match)
def text_to_string(att: Attachment) -> Attachment:
    """Load text files as strings with automatic input source handling."""
    # Use the new text_content property - no more repetitive patterns!
    content = att.text_content
    
    att._obj = content
    att.text = content
    return att


@loader(match=lambda att: att.path.lower().endswith(('.html', '.htm')))
def html_to_bs4(att: Attachment) -> Attachment:
    """Load HTML files and parse with BeautifulSoup with automatic input source handling."""
    try:
        from bs4 import BeautifulSoup
        
        # Use the new text_content property - no more repetitive patterns!
        content = att.text_content
        
        # Parse with BeautifulSoup
        soup = BeautifulSoup(content, 'html.parser')
        
        # Store the soup object
        att._obj = soup
        # Store some metadata
        att.metadata.update({
            'content_type': 'text/html',
            'file_size': len(content),
        })
        
        return att
    except ImportError:
        raise ImportError("beautifulsoup4 is required for HTML loading. Install with: pip install beautifulsoup4") 