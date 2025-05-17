"""
Attachments library __init__ file.
"""

from .core import Attachments
from .parsers import BaseParser, ParserRegistry, PDFParser, PPTXParser, HTMLParser, AudioParser, DOCXParser, ODTParser, ImageParser # Added ImageParser
from .renderers import BaseRenderer, RendererRegistry, DefaultXMLRenderer, PlainTextRenderer # Added PlainTextRenderer
from .detectors import Detector
from .exceptions import AttachmentError, DetectionError, ParsingError, RenderingError, ConfigurationError
from .office_contact_sheet import pdf_to_contact_sheet, office_file_to_contact_sheet

__version__ = "0.1.1" # Updated version

__all__ = [
    "Attachments",
    "BaseParser",
    "ParserRegistry",
    "PDFParser",
    "PPTXParser",
    "HTMLParser",
    "AudioParser", # Added AudioParser to __all__ if it wasn't (it was)
    "DOCXParser", # Added DOCXParser to __all__ if it wasn't (it was)
    "ODTParser",  # Added ODTParser to __all__ if it wasn't (it was)
    "ImageParser", # Added ImageParser to __all__
    "BaseRenderer",
    "RendererRegistry",
    "DefaultXMLRenderer",
    "PlainTextRenderer", # Added PlainTextRenderer to __all__
    "Detector",
    "AttachmentError",
    "DetectionError",
    "ParsingError",
    "RenderingError",
    "ConfigurationError",
    "pdf_to_contact_sheet",
    "office_file_to_contact_sheet",
]

# This file will expose the core components of the library. 