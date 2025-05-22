"""DSPy framework adapter."""

from typing import Dict, Any, Union, TYPE_CHECKING
from ..core.attachment import Attachment
from ..core.decorators import adapter
from ..core.namespaces import present

if TYPE_CHECKING:
    from .. import Attachments


@adapter
def dspy(source: Union[Attachment, "Attachments"], prompt: str = "") -> Dict[str, Any]:
    """
    Format attachment(s) for DSPy framework.
    
    Returns a dictionary with context and question ready for DSPy modules.
    Handles both single Attachment and Attachments objects automatically.
    
    Examples:
        # Single attachment
        att = load.pdf("doc.pdf")
        data = adapt.dspy(att, "What are the key points?")
        
        # Multiple attachments
        ctx = Attachments("doc.pdf", "data.csv")
        data = adapt.dspy(ctx, "Analyze these files")
        
        # Use with dspy.Predict or other DSPy modules
        predictor = dspy.Predict("context, question -> answer")
        result = predictor(**data)
    
    Args:
        source: Single Attachment or Attachments collection
        prompt: Question or prompt
        
    Returns:
        Dict with 'context' and 'question' keys for DSPy
    """
    context_parts = []
    
    # Check if it's Attachments (multiple) or single Attachment
    if hasattr(source, 'attachments'):  # It's an Attachments instance
        # Combine all text as context
        text_content = source.text
        if text_content.strip():
            context_parts.append(text_content)
        
        # Note about images (DSPy typically works with text)
        if source.images:
            context_parts.append(f"[Document contains {len(source.images)} images]")
    else:  # Single Attachment
        # Extract text as context
        try:
            text_att = present.text(source)
            if text_att and text_att.content.strip():
                context_parts.append(text_att.content)
        except:
            pass
        
        # Note about images (DSPy typically works with text)
        try:
            image_att = present.images(source)
            if image_att and image_att.content:
                context_parts.append(f"[Document contains {len(image_att.content)} images]")
        except:
            pass
    
    # Combine context
    context = "\n\n".join(context_parts) if context_parts else ""
    
    return {
        "context": context,
        "question": prompt
    } 