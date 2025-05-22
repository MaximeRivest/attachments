"""LangChain framework adapter."""

from typing import List, Dict, Any, Union, TYPE_CHECKING
from ..core.attachment import Attachment
from ..core.decorators import adapter
from ..core.namespaces import present

if TYPE_CHECKING:
    from .. import Attachments


@adapter
def langchain_messages(source: Union[Attachment, "Attachments"], prompt: str = "") -> List[Dict[str, Any]]:
    """
    Format attachment(s) for LangChain message format.
    
    Returns messages compatible with LangChain's ChatMessageHistory
    and various LLM integrations. Handles both single Attachment 
    and Attachments objects automatically.
    
    Examples:
        # Single attachment
        att = load.pdf("doc.pdf")
        messages = adapt.langchain_messages(att, "Analyze this")
        
        # Multiple attachments
        ctx = Attachments("doc.pdf", "image.png")
        messages = adapt.langchain_messages(ctx, "Analyze these files")
        
        # Use with LangChain
        from langchain.schema import HumanMessage
        human_msg = HumanMessage(content=messages[0]["content"])
    
    Args:
        source: Single Attachment or Attachments collection
        prompt: User prompt to include
        
    Returns:
        List of message dicts with 'role' and 'content'
    """
    content_parts = []
    
    if prompt:
        content_parts.append({"type": "text", "text": prompt})
    
    # Check if it's Attachments (multiple) or single Attachment
    if hasattr(source, 'attachments'):  # It's an Attachments instance
        # Combine text from all attachments
        text_content = source.text
        if text_content.strip():
            content_parts.append({"type": "text", "text": text_content})
        
        # Add all images
        for img_data_url in source.images:
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": img_data_url}
            })
    else:  # Single Attachment
        # Extract text
        try:
            text_att = present.text(source)
            if text_att and text_att.content.strip():
                content_parts.append({"type": "text", "text": text_att.content})
        except:
            pass
        
        # Extract images as base64
        try:
            image_att = present.images(source)
            if image_att and image_att.content:
                for img_data_url in image_att.content:
                    content_parts.append({
                        "type": "image_url",
                        "image_url": {"url": img_data_url}
                    })
        except:
            pass
    
    return [{
        "role": "human",
        "content": content_parts
    }]


@adapter  
def langchain_document(source: Union[Attachment, "Attachments"]) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Format attachment(s) as LangChain Document(s).
    
    Returns a dictionary (or list of dictionaries) compatible with 
    LangChain's Document class, useful for vector stores, retrievers, and chains.
    
    Examples:
        # Single attachment -> single document
        att = load.pdf("doc.pdf")
        doc_data = adapt.langchain_document(att)
        from langchain.schema import Document
        doc = Document(**doc_data)
        
        # Multiple attachments -> list of documents
        ctx = Attachments("doc1.pdf", "doc2.txt")
        docs_data = adapt.langchain_document(ctx)
        docs = [Document(**d) for d in docs_data]
    
    Args:
        source: Single Attachment or Attachments collection
        
    Returns:
        Dict with 'page_content' and 'metadata' for single attachment,
        or List of such dicts for multiple attachments
    """
    # Check if it's Attachments (multiple) or single Attachment
    if hasattr(source, 'attachments'):  # It's an Attachments instance
        documents = []
        for att in source.attachments:  # type: ignore
            # Process each attachment individually
            doc_data = _attachment_to_document(att)
            if doc_data:
                documents.append(doc_data)
        return documents
    else:  # Single Attachment
        return _attachment_to_document(source)


def _attachment_to_document(att: Attachment) -> Dict[str, Any]:
    """Helper to convert single attachment to document format."""
    # Extract text as page content
    page_content = ""
    try:
        text_att = present.text(att)
        if text_att and text_att.content:
            page_content = text_att.content
    except:
        pass
    
    # Build metadata
    metadata = {
        "source": att.source,
        "commands": att.commands
    }
    
    # Add image count if available
    try:
        image_att = present.images(att)
        if image_att and image_att.content:
            metadata["image_count"] = len(image_att.content)
    except:
        pass
    
    return {
        "page_content": page_content,
        "metadata": metadata
    } 