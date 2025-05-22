"""OpenAI API adapters for different API endpoints."""

from typing import List, Dict, Any, Optional, Union
from ..core.attachment import Attachment
from ..core.decorators import adapter
from ..core.namespaces import present


@adapter
def openai_chat(att: Attachment, prompt: str = "") -> List[Dict[str, Any]]:
    """
    Format attachment for OpenAI Chat Completions API.
    
    Returns message format ready for client.chat.completions.create()
    
    Example:
        messages = adapt.openai_chat(attachment, "What's in this image?")
        response = client.chat.completions.create(model="gpt-4o", messages=messages)
    
    Args:
        att: Single attachment to format
        prompt: User prompt to include
        
    Returns:
        List with one user message containing content from attachment
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
    
    # Extract images from the attachment  
    try:
        image_att = present.images(att)
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
def openai_responses(att: Attachment, prompt: str = "") -> List[Dict[str, Any]]:
    """
    Format attachment for OpenAI Responses API (structured format).
    
    Returns input format ready for client.responses.create()
    
    Example:
        input_data = adapt.openai_responses(attachment, "what is in this image?")
        response = client.responses.create(model="gpt-4o", input=input_data)
    
    Args:
        att: Single attachment to format
        prompt: User prompt to include
        
    Returns:
        List with one user input containing content from attachment
    """
    content = []
    
    if prompt:
        content.append({"type": "input_text", "text": prompt})
    
    # Extract text as input_text
    try:
        text_att = present.text(att)
        if text_att and text_att.content.strip():
            content.append({"type": "input_text", "text": text_att.content})
    except:
        pass
    
    # Extract images as input_image
    try:
        image_att = present.images(att)
        if image_att and image_att.content:
            for img_data_url in image_att.content:
                # For responses API, we use image_url directly without nesting
                content.append({
                    "type": "input_image",
                    "image_url": img_data_url
                })
    except:
        pass
        
    return [{"role": "user", "content": content}]


@adapter  
def openai_structured(att: Attachment, prompt: str = "", response_format: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Format attachment for OpenAI Structured Outputs API.
    
    This adapter formats content for the newer OpenAI API features including:
    - Structured outputs with JSON schema
    - o1 reasoning models with structured responses
    - Function calling with structured responses
    
    Args:
        att: Attachment to format
        prompt: User prompt to include
        response_format: JSON schema for structured output (optional)
        
    Returns:
        Complete API payload ready for client.chat.completions.create()
    """
    messages = []
    
    # System message if using structured outputs
    if response_format:
        system_msg = "You are a helpful assistant that provides responses in the exact JSON format specified."
        messages.append({"role": "system", "content": system_msg})
    
    # User message with content
    user_content = []
    if prompt:
        user_content.append({"type": "text", "text": prompt})
    
    # Add text content from attachment
    try:
        text_att = present.text(att)
        if text_att and text_att.content.strip():
            user_content.append({"type": "text", "text": f"\n\nDocument content:\n{text_att.content}"})
    except:
        pass
    
    # Add images from attachment
    try:
        image_att = present.images(att)
        if image_att and image_att.content:
            for img_data_url in image_att.content:
                user_content.append({"type": "image_url", "image_url": {"url": img_data_url}})
    except:
        pass
    
    messages.append({"role": "user", "content": user_content})
    
    # Build complete API payload
    payload = {
        "model": "gpt-4o",  # Default model for structured outputs
        "messages": messages
    }
    
    if response_format:
        payload["response_format"] = response_format
        
    return payload


# Legacy adapter for backward compatibility
@adapter
def openai(att: Attachment, prompt: str = "") -> List[Dict[str, Any]]:
    """
    Legacy OpenAI adapter for backward compatibility.
    
    Returns just the content list, not the full message format.
    """
    # Get the chat format
    messages = openai_chat(att, prompt)
    
    # Extract just the content for backward compatibility
    if messages and len(messages) > 0 and "content" in messages[0]:
        return messages[0]["content"]
    
    return [] 