"""
DOCX to LLM Pipeline Processor
==============================

Complete pipeline for processing Word documents optimized for LLM consumption.
Supports clean DSL commands for the Attachments() simple API.

DSL Commands:
    [images:true|false] - Include images (default: true)
    [format:plain|markdown|xml] - Text formatting (default: markdown)
        Aliases: text=plain, txt=plain, md=markdown, code=xml
    [pages:1-5,10] - Specific pages (inherits from existing modify.pages)
    [resize_images:50%|800x600] - Image resize specification (consistent naming)
    [tile:2x2|3x1|4] - Tile multiple pages into grid layout

Usage:
    # Explicit processor access
    result = processors.docx_to_llm(attach("document.docx"))
    
    # With DSL commands
    result = processors.docx_to_llm(attach("document.docx[format:xml][images:false]"))
    
    # Simple API (auto-detected)
    ctx = Attachments("document.docx[pages:1-3][tile:2x2]")
    text = str(ctx)
    images = ctx.images
"""

from ..core import Attachment
from ..matchers import docx_match
from . import processor

@processor(
    match=docx_match,
    description="Primary DOCX processor with multiple text formats and image options"
)
def docx_to_llm(att: Attachment) -> Attachment:
    """
    Process DOCX files for LLM consumption.
    
    Supports DSL commands:
    - format: plain, markdown (default), xml/code for different text representations
    - images: true (default), false to control image extraction
    - pages: 1-5,10 for specific page selection
    - resize_images: 50%, 800x600 for image resizing
    - tile: 2x2, 3x1 for page tiling
    
    Text formats:
    - plain: Clean text extraction from all paragraphs
    - markdown: Structured markdown with heading detection (default)
    - xml: Raw DOCX XML content for detailed analysis
    """
    
    # Import namespaces properly to get VerbFunction wrappers
    from .. import load, modify, present, refine
    
    # Determine text format from DSL commands
    format_cmd = att.commands.get('format', 'markdown')
    
    # Handle format aliases
    format_aliases = {
        'text': 'plain',
        'txt': 'plain', 
        'md': 'markdown',
        'code': 'xml'
    }
    format_cmd = format_aliases.get(format_cmd, format_cmd)
    
    # Determine if images should be included
    include_images = att.commands.get('images', 'true').lower() == 'true'
    
    # Build the pipeline based on format and image preferences
    if format_cmd == 'plain':
        # Plain text format
        text_presenter = present.text
    elif format_cmd == 'xml':
        # XML/code format - extract raw DOCX XML
        text_presenter = present.xml
    else:
        # Default to markdown
        text_presenter = present.markdown
    
    # Build image pipeline if requested
    if include_images:
        image_pipeline = present.images
    else:
        # Empty pipeline that does nothing
        image_pipeline = lambda att: att
    
    # Enhanced pipeline with format and image control
    return (att 
           | load.docx_to_python_docx
           | modify.pages  # Handles pages:1-5,10 DSL command
           | text_presenter + image_pipeline + present.metadata
           | refine.tile_images | refine.resize_images | refine.add_headers) 