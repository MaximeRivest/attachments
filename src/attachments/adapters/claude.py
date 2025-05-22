"""Claude/Anthropic API adapter."""

from typing import List, Dict, Any, Union, TYPE_CHECKING
from ..core.attachment import Attachment
from ..core.decorators import adapter
from ..core.namespaces import present

if TYPE_CHECKING:
    from .. import Attachments


@adapter
def claude(source: Union[Attachment, "Attachments"], prompt: str = "") -> List[Dict[str, Any]]:
    """
    Format attachment(s) for Claude/Anthropic Messages API.
    
    Handles both single Attachment and Attachments objects automatically.
    This is the EXIT POINT from attachment world - returns Claude message format.
    
    Examples:
        # Single attachment
        att = load.pdf("doc.pdf")
        messages = adapt.claude(att, "Summarize this")
        
        # Multiple attachments
        ctx = Attachments("doc.pdf", "image.png")
        messages = adapt.claude(ctx, "Analyze these files")
        
        # Use with Anthropic
        response = client.messages.create(model="claude-3-5-sonnet-20241022", messages=messages)
    
    Args:
        source: Single Attachment or Attachments collection
        prompt: User prompt to include
        
    Returns:
        List with one user message in Claude format
    """
    content = []
    
    if prompt:
        content.append({"type": "text", "text": prompt})
    
    # Check if it's Attachments (multiple) or single Attachment
    if hasattr(source, 'attachments'):  # It's an Attachments instance
        # Combine text from all attachments
        text_content = source.text
        if text_content.strip():
            content.append({"type": "text", "text": text_content})
        
        # Add all images in Claude format
        for img_data_url in source.images:
            if img_data_url.startswith("data:image/"):
                base64_data = img_data_url.split(",", 1)[1]
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": base64_data
                    }
                })
    else:  # Single Attachment
        # Extract text from the attachment
        try:
            text_att = present.text(source)
            if text_att and text_att.content.strip():
                content.append({"type": "text", "text": text_att.content})
        except:
            pass
        
        # Extract images - Claude uses different format than OpenAI
        try:
            image_att = present.images(source)
            if image_att and image_att.content:
                for img_data_url in image_att.content:
                    # Convert data URL to Claude format
                    if img_data_url.startswith("data:image/"):
                        base64_data = img_data_url.split(",", 1)[1]
                        content.append({
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": base64_data
                            }
                        })
        except:
            pass
        
    return [{"role": "user", "content": content}] 