"""Attachment container classes."""

from typing import Any, Dict, Optional


class Attachment:
    """Lightweight container that flows through pipelines."""
    
    def __init__(self, content: Any, source: str, commands: Optional[Dict[str, Any]] = None):
        self.content = content
        self.source = source
        self.commands = commands or {}
        self._pipeline_ready = True  # Can continue in pipeline
        
    def __or__(self, other):
        """Pipeline with | operator."""
        return other(self)
    
    def __add__(self, other):
        """Merge results with + operator."""
        # Creates MultiAttachment with both results
        pass


class MultiAttachment(Attachment):
    """Container for multiple attachment results."""
    def __init__(self, attachments: list):
        self.attachments = attachments 