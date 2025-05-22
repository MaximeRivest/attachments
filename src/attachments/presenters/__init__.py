"""Content presenters for different output formats."""

# Import all presenters to auto-register them
from . import text
from . import images
from . import markdown
from . import xml

__all__ = ['text', 'images', 'markdown', 'xml'] 