"""
PPTX to LLM Pipeline Processor
=============================

Complete pipeline for processing PowerPoint files optimized for LLM consumption.
Supports clean DSL commands for the Attachments() simple API.

DSL Commands:
    [images:true|false] - Include images (default: true)
    [format:plain|markdown|xml] - Text formatting (default: markdown)
        Aliases: text=plain, txt=plain, md=markdown, code=xml
    [pages:1-5,10] - Specific slides (inherits from existing modify.pages)
    [resize_images:50%|800x600] - Image resize specification (consistent naming)
    [tile:2x2|3x1|4] - Tile multiple slides into grid layout (default: 2x2 for multi-slide presentations)

Note: Multi-slide PPTX files are automatically tiled in a 2x2 grid by default for better LLM consumption.
Use [tile:false] to disable tiling or [tile:3x1] for custom layouts.

Usage:
    # Explicit processor access
    result = processors.pptx_to_llm(attach("presentation.pptx"))
    
    # With DSL commands
    result = processors.pptx_to_llm(attach("presentation.pptx[format:xml][images:false]"))
    
    # Simple API (auto-detected)
    ctx = Attachments("presentation.pptx[pages:1-3][tile:2x2]")
    text = str(ctx)
    images = ctx.images
"""

from ..core import Attachment
from ..matchers import pptx_match
from . import processor

@processor(
    match=pptx_match,
    description="Primary PPTX processor with multiple text formats and image options"
)
def pptx_to_llm(att: Attachment) -> Attachment:
    """
    Process PPTX files for LLM consumption.
    
    Supports DSL commands:
    - format: plain, markdown (default), xml/code for different text representations
    - images: true (default), false to control image extraction
    - pages: 1-5,10 for specific slide selection
    - resize_images: 50%, 800x600 for image resizing
    - tile: 2x2, 3x1 for slide tiling
    
    Text formats:
    - plain: Clean text extraction from all slides
    - markdown: Structured markdown with slide headers (default)
    - xml: Raw PPTX XML content for detailed analysis
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
        # XML/code format - extract raw PPTX XML
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
    
    # Build the complete pipeline based on format
    if format_cmd == 'plain':
        return (att 
               | load.url_to_response      # Handle URLs with new morphing architecture
               | modify.morph_to_detected_type  # Smart detection replaces hardcoded url_to_file
               | load.pptx_to_python_pptx 
               | modify.pages  # Optional - only acts if [pages:...] present
               | text_presenter + image_pipeline + present.metadata
               | refine.tile_images | refine.resize_images )
    else:
        # Default to markdown
        return (att 
               | load.url_to_response      # Handle URLs with new morphing architecture
               | modify.morph_to_detected_type  # Smart detection replaces hardcoded url_to_file
               | load.pptx_to_python_pptx 
               | modify.pages  # Optional - only acts if [pages:...] present
               | text_presenter + image_pipeline + present.metadata
               | refine.tile_images | refine.resize_images ) 