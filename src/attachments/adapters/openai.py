"""OpenAI API adapter."""

from ..core.attachment import Attachment
from ..core.decorators import adapter
from ..core.namespaces import present


@adapter
def openai(att: Attachment, prompt: str = "") -> list:
    """Format single attachment for OpenAI."""
    content = []
    if prompt:
        content.append({"type": "text", "text": prompt})
    
    # Try to extract text from the attachment
    try:
        text_att = present.text(att)
        if text_att and text_att.content.strip():
            content.append({"type": "text", "text": text_att.content})
    except:
        pass  # Text extraction not available for this type
    
    # Try to extract images from the attachment  
    try:
        image_att = present.images(att)
        if image_att and image_att.content:
            for img_data_url in image_att.content:
                content.append({"type": "image_url", "image_url": {"url": img_data_url}})
    except:
        pass  # Image extraction not available for this type
        
    return content 