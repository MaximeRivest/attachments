"""Content presenters for different output formats."""

# Import all presenters to auto-register them
from . import text
from . import images
from . import markdown

__all__ = ['text', 'images', 'markdown'] 