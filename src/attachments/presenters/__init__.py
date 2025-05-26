"""Presenters package - formats attachment objects for output."""

# Import all presenter modules to register them
from . import text
from . import visual
from . import data
from . import metadata

# Re-export commonly used functions if needed
__all__ = [
    'text',
    'visual',
    'data', 
    'metadata'
] 