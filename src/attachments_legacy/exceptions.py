"""Custom exceptions for the attachments library."""

class AttachmentError(Exception):
    """Base class for exceptions in this module."""
    pass

class DetectionError(AttachmentError):
    """Raised when file type detection fails."""
    pass

class ParsingError(AttachmentError):
    """Raised when file parsing fails.

    Parameters
    ----------
    message : str
        Human-readable description of the error.
    file_path : str | None, optional
        The file that triggered the error, if known.
    parser_name : str | None, optional
        Name of the parser raising the error.  Useful when multiple parsers are in play.
    underlying_exception : Exception | None, optional
        The original exception that led to this ``ParsingError``. When provided, it will
        also be set as ``__cause__`` so Python traces display the full chain.
    """

    def __init__(self,
                 message: str,
                 *,
                 file_path: str | None = None,
                 parser_name: str | None = None,
                 underlying_exception: Exception | None = None):
        super().__init__(message)
        self.message = message
        self.file_path = file_path
        self.parser_name = parser_name

        # Preserve exception cause for nicer tracebacks when re-raising via ``from e``
        if underlying_exception is not None:
            self.__cause__ = underlying_exception

    def __str__(self) -> str:  # pragma: no cover – simple helper
        base = self.message
        extras: list[str] = []
        if self.file_path:
            extras.append(f"file_path={self.file_path}")
        if self.parser_name:
            extras.append(f"parser_name={self.parser_name}")
        if extras:
            base = f"{base} ({', '.join(extras)})"
        return base

class RenderingError(AttachmentError):
    """Raised when content rendering fails."""
    pass 

class ConfigurationError(AttachmentError):
    """Custom exception for configuration-related errors."""
    pass 

class ImageProcessingError(AttachmentError):
    """Raised when an error occurs during image processing operations."""
    pass

class AudioProcessingError(AttachmentError):
    """Raised when an error occurs during audio processing operations."""
    pass

# You can add more specific error types as needed. 