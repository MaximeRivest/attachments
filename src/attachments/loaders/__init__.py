"""Loaders package - transforms files into attachment objects."""

# Import all loader modules to register them
from . import documents
from . import media  
from . import data
from . import web
from . import repositories

# Re-export commonly used functions if needed
__all__ = [
    'documents',
    'media', 
    'data',
    'web',
    'repositories'
] 