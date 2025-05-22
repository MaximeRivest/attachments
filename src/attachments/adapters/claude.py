"""Claude/Anthropic API adapter."""

from typing import List, Dict, Any
from ..core.attachment import Attachment
from ..core.decorators import adapter
from ..core.namespaces import present


@adapter
def claude(att: Attachment, prompt: str = "") -> List[Dict[str, Any]]:
    """
    Format attachment for Claude/Anthropic Messages API.
    
    This is the EXIT POINT from attachment world - returns Claude message format.
    
    Args:
        att: Single attachment to format
        prompt: User prompt to include
        
    Returns:
        List with one user message in Claude format
    """
    content = []
    
    if prompt:
        content.append({"type": "text", "text": prompt})
    
    # Extract text from the attachment
    try:
        text_att = present.text(att)
        if text_att and text_att.content.strip():
            content.append({"type": "text", "text": text_att.content})
    except:
        pass
    
    # Extract images - Claude uses different format than OpenAI
    try:
        image_att = present.images(att)
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