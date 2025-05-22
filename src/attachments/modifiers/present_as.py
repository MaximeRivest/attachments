"""Presentation modifier that preserves Attachment wrapper for pipeline flow."""

from typing import Any
from ..core.decorators import modifier
from ..core.attachment import Attachment
from ..core.namespaces import present


@modifier
def present_as(att: Attachment, format: str = 'text') -> Attachment:
    """
    Apply presentation format while preserving Attachment wrapper.
    
    This allows presentation to be part of the pipeline flow without
    breaking the chain. The presented content becomes the new content
    of the Attachment.
    
    Args:
        att: Attachment to present
        format: Presentation format ('text', 'markdown', 'xml', 'images')
        
    Returns:
        New Attachment with presented content
        
    Examples:
        # In a pipeline
        pipeline = load.pdf | modify.pages | modify.present_as('markdown')
        
        # Or via DSL
        "document.pdf[pages:1-3,present_as:markdown]"
    """
    # Apply the appropriate presenter
    if format == 'markdown' and hasattr(present, 'markdown'):
        presenter_func = getattr(present, 'markdown')
        presented = presenter_func(att)
    elif format == 'xml' and hasattr(present, 'xml'):
        presenter_func = getattr(present, 'xml')
        presented = presenter_func(att)
    elif format == 'images' and hasattr(present, 'images'):
        presenter_func = getattr(present, 'images')
        presented = presenter_func(att)
    else:
        # Default to text presentation
        presenter_func = getattr(present, 'text', lambda x: str(x))
        presented = presenter_func(att)
    
    # Extract the actual content from the presenter result
    if isinstance(presented, Attachment):
        content = presented.content
    else:
        content = presented
    
    # Return new Attachment with presented content
    # Preserve source and commands, add presentation info
    return Attachment(
        content=content,
        source=att.source,
        commands={**att.commands, 'presented_as': format}
    ) 