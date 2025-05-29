"""
PDF to LLM Pipeline Processor
============================

Complete pipeline for processing PDF files optimized for LLM consumption.
Supports clean DSL commands for the Attachments() simple API.

DSL Commands:
    [images:true|false] - Include images (default: true)
    [format:plain|markdown|code] - Text formatting (default: markdown)
        Aliases: text=plain, txt=plain, md=markdown
    [pages:1-5,10] - Specific pages (inherits from existing modify.pages)
    [resize_images:50%|800x600] - Image resize specification (consistent naming)
    [tile:2x2|3x1|4] - Tile multiple PDF pages into grid layout (default: 2x2 for multi-page PDFs)
    [ocr:auto|true|false] - OCR for scanned PDFs (auto=detect and apply if needed)

Note: Multi-page PDFs are automatically tiled in a 2x2 grid by default for better LLM consumption.
Use [tile:false] to disable tiling or [tile:3x1] for custom layouts.

Usage:
    # Explicit processor access
    result = processors.pdf_to_llm(attach("doc.pdf"))
    
    # With DSL commands
    result = processors.pdf_to_llm(attach("doc.pdf[format:plain][images:false]"))
    result = processors.pdf_to_llm(attach("doc.pdf[format:md]"))  # markdown alias
    result = processors.pdf_to_llm(attach("doc.pdf[images:false]"))  # text only
    result = processors.pdf_to_llm(attach("doc.pdf[tile:2x3][resize_images:400]"))  # tile + resize
    result = processors.pdf_to_llm(attach("doc.pdf[ocr:auto]"))  # auto-OCR for scanned PDFs
    result = processors.pdf_to_llm(attach("doc.pdf[ocr:true]"))  # force OCR
    
    # Mixing with verbs (power users)
    result = processors.pdf_to_llm(attach("doc.pdf")) | refine.custom_step

    # Like any pipeline and attachment it's ready with adapters
    claude_message_format = result.claude()
"""

from ..core import Attachment
from ..matchers import pdf_match
from . import processor

@processor(
    match=pdf_match,
    description="Primary PDF processor with clean DSL commands"
)
def pdf_to_llm(att: Attachment) -> Attachment:
    """
    Process PDF files for LLM consumption.
    
    Supports DSL commands (for Attachments() simple API):
    - images: true, false (default: true)
    - format: plain, markdown, code (default: markdown)
      Aliases: text=plain, txt=plain, md=markdown
    - resize_images: 50%, 800x600 (for images)
    - tile: 2x2, 3x1, 4 (for tiling multiple pages)
    - pages: 1-5,10 (for page selection)
    - ocr: auto, true, false (OCR for scanned PDFs, auto=detect and apply if needed)
    """
    
    # Import namespaces properly to get VerbFunction wrappers
    from .. import load, modify, present, refine
    
    # Determine text format from DSL commands
    format_cmd = att.commands.get('format', 'markdown')
    
    # Handle format aliases
    format_aliases = {
        'text': 'plain',
        'txt': 'plain', 
        'md': 'markdown'
    }
    format_cmd = format_aliases.get(format_cmd, format_cmd)
    
    # Build the pipeline based on format
    if format_cmd == 'plain':
        text_presenter = present.text
    else:
        # Default to markdown
        text_presenter = present.markdown
    
    # Determine if images should be included
    include_images = att.commands.get('images', 'true').lower() == 'true'
    
    # Build image pipeline if requested
    if include_images:
        image_pipeline = present.images
    else:
        # Empty pipeline that does nothing
        image_pipeline = lambda att: att
    
    # Get OCR setting from DSL commands
    ocr_setting = att.commands.get('ocr', 'auto').lower()
    
    if ocr_setting == 'true':
        # Force OCR regardless of text extraction quality
        return (att 
               | load.url_to_response      # Handle URLs with new morphing architecture
               | modify.morph_to_detected_type  # Smart detection replaces hardcoded url_to_file
               | load.pdf_to_pdfplumber 
               | modify.pages  # Optional - only acts if [pages:...] present
               | text_presenter + image_pipeline + present.ocr + present.metadata  # Include OCR
               | refine.tile_images | refine.resize_images )
    elif ocr_setting == 'false':
        # Never use OCR
        return (att 
               | load.url_to_response      # Handle URLs with new morphing architecture
               | modify.morph_to_detected_type  # Smart detection replaces hardcoded url_to_file
               | load.pdf_to_pdfplumber 
               | modify.pages  # Optional - only acts if [pages:...] present
               | text_presenter + image_pipeline + present.metadata  # No OCR
               | refine.tile_images | refine.resize_images )
    else:
        # Auto mode (default): First extract text, then conditionally add OCR
        # Process with standard pipeline first
        processed = (att 
                    | load.url_to_response      # Handle URLs with new morphing architecture
                    | modify.morph_to_detected_type  # Smart detection replaces hardcoded url_to_file
                    | load.pdf_to_pdfplumber 
                    | modify.pages  # Optional - only acts if [pages:...] present
                    | text_presenter + image_pipeline + present.metadata  # Standard extraction
                    | refine.tile_images | refine.resize_images )
        
        # Check if OCR is needed based on text extraction quality
        if (processed.metadata.get('is_likely_scanned', False) and 
            processed.metadata.get('text_extraction_quality') in ['poor', 'limited']):
            # Add OCR for scanned documents
            processed = processed | present.ocr
        
        return processed
