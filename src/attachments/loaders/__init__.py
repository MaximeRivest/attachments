"""File loaders for various formats."""

# Import all loaders to auto-register them
from . import pdf
from . import csv
from . import image
from . import pptx

__all__ = ['pdf', 'csv', 'image', 'pptx'] 