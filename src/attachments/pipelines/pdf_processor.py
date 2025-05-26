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
    [tile:2x2|3x1|4] - Tile multiple PDF pages into grid layout
    [ocr:auto|true|false] - OCR for scanned PDFs (auto=detect and apply if needed)

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
    
    # Enhanced pipeline with both text and images
    # Smart filtering will choose based on DSL commands
    # Note: Using only present.markdown (not both text + markdown) to avoid redundancy
    # The smart presenter system will automatically choose the right format based on DSL
    
    # Get OCR setting from DSL commands
    ocr_setting = att.commands.get('ocr', 'auto').lower()
    
    if ocr_setting == 'true':
        # Force OCR regardless of text extraction quality
        return (att 
               | load.pdf_to_pdfplumber 
               | modify.pages  # Optional - only acts if [pages:...] present
               | present.markdown + present.images + present.ocr  # Include OCR
               | refine.tile_images | refine.resize_images )
    elif ocr_setting == 'false':
        # Never use OCR
        return (att 
               | load.pdf_to_pdfplumber 
               | modify.pages  # Optional - only acts if [pages:...] present
               | present.markdown + present.images  # No OCR
               | refine.tile_images | refine.resize_images )
    else:
        # Auto mode (default): First extract text, then conditionally add OCR
        # Process with standard pipeline first
        processed = (att 
                    | load.pdf_to_pdfplumber 
                    | modify.pages  # Optional - only acts if [pages:...] present
                    | present.markdown + present.images  # Standard extraction
                    | refine.tile_images | refine.resize_images )
        
        # Check if OCR is needed based on text extraction quality
        if (processed.metadata.get('is_likely_scanned', False) and 
            processed.metadata.get('text_extraction_quality') in ['poor', 'limited']):
            # Add OCR for scanned documents
            processed = processed | present.ocr
        
        return processed
