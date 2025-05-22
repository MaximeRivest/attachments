"""OpenAI API adapters for different API endpoints."""

from typing import List, Dict, Any, Optional, Union, TYPE_CHECKING
from ..core.attachment import Attachment
from ..core.decorators import adapter
from ..core.namespaces import present

if TYPE_CHECKING:
    from .. import Attachments


@adapter
def openai_chat(source: Union[Attachment, "Attachments"], prompt: str = "") -> List[Dict[str, Any]]:
    """
    Format attachment(s) for OpenAI Chat Completions API.
    
    Handles both single Attachment and Attachments objects automatically.
    
    Examples:
        # Single attachment
        att = load.pdf("doc.pdf")
        messages = adapt.openai_chat(att, "Summarize this")
        
        # Multiple attachments  
        ctx = Attachments("doc.pdf", "image.png")
        messages = adapt.openai_chat(ctx, "Analyze these files")
        
        # Use with OpenAI
        response = client.chat.completions.create(model="gpt-4o", messages=messages)
    
    Args:
        source: Single Attachment or Attachments collection
        prompt: User prompt to include
        
    Returns:
        List with one user message containing content from attachment(s)
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
        
        # Add all images
        for img_data_url in source.images:
            content.append({
                "type": "image_url",
                "image_url": {"url": img_data_url}
            })
    else:  # Single Attachment
        # Extract text from the attachment
        try:
            text_att = present.text(source)
            if text_att and text_att.content.strip():
                content.append({"type": "text", "text": text_att.content})
        except:
            pass
        
        # Extract images from the attachment  
        try:
            image_att = present.images(source)
            if image_att and image_att.content:
                for img_data_url in image_att.content:
                    content.append({
                        "type": "image_url", 
                        "image_url": {"url": img_data_url}
                    })
        except:
            pass
        
    return [{"role": "user", "content": content}]


@adapter
def openai_responses(source: Union[Attachment, "Attachments"], prompt: str = "") -> List[Dict[str, Any]]:
    """
    Format attachment(s) for OpenAI Responses API (structured format).
    
    Handles both single Attachment and Attachments objects automatically.
    
    Examples:
        # Single attachment
        att = load.pdf("doc.pdf")
        input_data = adapt.openai_responses(att, "what is this?")
        
        # Multiple attachments
        ctx = Attachments("doc.pdf", "image.png")
        input_data = adapt.openai_responses(ctx, "analyze these")
        
        # Use with OpenAI
        response = client.responses.create(model="gpt-4o", input=input_data)
    
    Args:
        source: Single Attachment or Attachments collection
        prompt: User prompt to include
        
    Returns:
        List with one user input containing content from attachment(s)
    """
    content = []
    
    if prompt:
        content.append({"type": "input_text", "text": prompt})
    
    # Check if it's Attachments (multiple) or single Attachment
    if hasattr(source, 'attachments'):  # It's an Attachments instance
        # Combine text from all attachments
        text_content = source.text
        if text_content.strip():
            content.append({"type": "input_text", "text": text_content})
        
        # Add all images
        for img_data_url in source.images:
            content.append({
                "type": "input_image",
                "image_url": img_data_url
            })
    else:  # Single Attachment
        # Extract text as input_text
        try:
            text_att = present.text(source)
            if text_att and text_att.content.strip():
                content.append({"type": "input_text", "text": text_att.content})
        except:
            pass
        
        # Extract images as input_image
        try:
            image_att = present.images(source)
            if image_att and image_att.content:
                for img_data_url in image_att.content:
                    content.append({
                        "type": "input_image",
                        "image_url": img_data_url
                    })
        except:
            pass
        
    return [{"role": "user", "content": content}]

