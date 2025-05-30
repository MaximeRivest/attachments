"""
Vector Graphics to LLM Pipeline Processor
========================================

Complete pipeline for processing vector graphics files (SVG, EPS) optimized for LLM consumption.
Provides both textual analysis and visual rendering for comprehensive understanding.

DSL Commands:
    [resize_images:50%|800x600] - Image resize specification for rendered output
    [format:text|markdown|xml] - Text output format (defaults to text for raw content)

Aliases: text=plain, txt=plain, md=markdown, code=xml

Usage:
    # Explicit processor access
    result = processors.svg_to_llm(attach("chart.svg"))
    result = processors.eps_to_llm(attach("diagram.eps"))
    # Like any pipeline and attachment it's ready with adapters
    claude_message_format = result.claude()
"""

from ..core import Attachment
from ..matchers import svg_match, eps_match
from . import processor

@processor(
    match=svg_match,
    description="Primary SVG processor with text analysis and image rendering"
)
def svg_to_llm(att: Attachment) -> Attachment:
    """
    Process SVG files for LLM consumption.
    
    Provides both:
    - Raw SVG content for textual analysis (structure, data, elements)
    - Rendered PNG image for visual analysis (requires cairosvg)
    
    Supports DSL commands:
    - resize_images: 50%, 800x600 (for rendered image output)
    - format: text, markdown, xml (for text output format)
    
    Aliases: text=plain, txt=plain, md=markdown, code=xml
    
    By default, shows raw SVG content which is perfect for LLM analysis.
    """
    
    # Import namespaces properly to get VerbFunction wrappers
    from .. import load, modify, present, refine
    
    # Handle format aliases
    format_aliases = {
        'text': 'plain',
        'txt': 'plain', 
        'md': 'markdown',
        'code': 'xml'
    }
    format_cmd = att.commands.get('format', 'plain')
    format_cmd = format_aliases.get(format_cmd, format_cmd)
    
    # Select appropriate text presenter based on format
    if format_cmd == 'plain':
        text_presenter = present.text
    elif format_cmd == 'markdown':
        text_presenter = present.markdown
    elif format_cmd == 'xml':
        text_presenter = present.xml
    else:
        text_presenter = present.text  # Default fallback
    
    # Build the pipeline for SVG processing with both text and images
    return (att 
           | load.url_to_response         # Handle URLs with new morphing architecture
           | modify.morph_to_detected_type # Smart detection replaces hardcoded url_to_file
           | load.svg_to_svgdocument      # Load SVG as SVGDocument object
           | text_presenter + present.images + present.metadata  # Get both text and images
           | refine.resize_images)        # Apply final resize if needed

@processor(
    match=eps_match,
    description="Primary EPS processor with text analysis and image rendering"
)
def eps_to_llm(att: Attachment) -> Attachment:
    """
    Process EPS files for LLM consumption.
    
    Provides both:
    - Raw PostScript content for textual analysis (structure, commands, data)
    - Rendered PNG image for visual analysis (requires ImageMagick/Ghostscript)
    
    Supports DSL commands:
    - resize_images: 50%, 800x600 (for rendered image output)
    - format: text, markdown, xml (for text output format)
    
    Aliases: text=plain, txt=plain, md=markdown, code=xml
    
    By default, shows raw PostScript content which is perfect for LLM analysis.
    """
    
    # Import namespaces properly to get VerbFunction wrappers
    from .. import load, modify, present, refine
    
    # Handle format aliases
    format_aliases = {
        'text': 'plain',
        'txt': 'plain', 
        'md': 'markdown',
        'code': 'xml'
    }
    format_cmd = att.commands.get('format', 'plain')
    format_cmd = format_aliases.get(format_cmd, format_cmd)
    
    # Select appropriate text presenter based on format
    if format_cmd == 'plain':
        text_presenter = present.text
    elif format_cmd == 'markdown':
        text_presenter = present.markdown
    elif format_cmd == 'xml':
        text_presenter = present.xml
    else:
        text_presenter = present.text  # Default fallback
    
    # Build the pipeline for EPS processing with both text and images
    return (att 
           | load.url_to_response         # Handle URLs with new morphing architecture
           | modify.morph_to_detected_type # Smart detection replaces hardcoded url_to_file
           | load.eps_to_epsdocument      # Load EPS as EPSDocument object
           | text_presenter + present.images + present.metadata  # Get both text and images
           | refine.resize_images)        # Apply final resize if needed 