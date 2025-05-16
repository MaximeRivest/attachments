"""
Attachments library __init__ file.
"""

from .core import Attachments
from .parsers import BaseParser, ParserRegistry, PDFParser, PPTXParser, HTMLParser
from .renderers import BaseRenderer, RendererRegistry, DefaultXMLRenderer
from .detectors import Detector
from .exceptions import AttachmentError, DetectionError, ParsingError, RenderingError, ConfigurationError

__version__ = "0.1.0"

__all__ = [
    "Attachments",
    "BaseParser",
    "ParserRegistry",
    "PDFParser",
    "PPTXParser",
    "HTMLParser",
    "BaseRenderer",
    "RendererRegistry",
    "DefaultXMLRenderer",
    "Detector",
    "AttachmentError",
    "DetectionError",
    "ParsingError",
    "RenderingError",
    "ConfigurationError",
]

# This file will expose the core components of the library. 