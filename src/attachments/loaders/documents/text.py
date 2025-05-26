"""Text and HTML document loaders."""

from ...core import Attachment, loader
from ... import matchers


@loader(match=matchers.text_match)
def text_to_string(att: Attachment) -> Attachment:
    """Load text files as strings."""
    with open(att.path, 'r', encoding='utf-8') as f:
        content = f.read()
        att._obj = content
        att.text = content
    return att


@loader(match=lambda att: att.path.lower().endswith(('.html', '.htm')))
def html_to_bs4(att: Attachment) -> Attachment:
    """Load HTML files and parse with BeautifulSoup."""
    try:
        from bs4 import BeautifulSoup
        
        with open(att.path, 'r', encoding='utf-8') as f:
            content = f.read()
        
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