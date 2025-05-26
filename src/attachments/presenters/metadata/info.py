"""Metadata and file information presenters."""

from ...core import Attachment, presenter


@presenter
def metadata(att: Attachment) -> Attachment:
    """Fallback metadata presenter."""
    return att 