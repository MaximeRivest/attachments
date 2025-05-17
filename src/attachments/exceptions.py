"""Custom exceptions for the attachments library."""

class AttachmentError(Exception):
    """Base class for exceptions in this module."""
    pass

class DetectionError(AttachmentError):
    """Raised when file type detection fails."""
    pass

class ParsingError(AttachmentError):
    """Raised when file parsing fails."""
    pass

class RenderingError(AttachmentError):
    """Raised when content rendering fails."""
    pass 

class ConfigurationError(AttachmentError):
    """Custom exception for configuration-related errors."""
    pass 

class ImageProcessingError(AttachmentError):
    """Raised when an error occurs during image processing operations."""
    pass 