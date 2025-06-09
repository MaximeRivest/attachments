"""
Webpage to LLM Pipeline Processor
=================================

Complete pipeline for processing web pages optimized for LLM consumption.
Combines text extraction with screenshot capabilities using Playwright.

DSL Commands:
    [images:true|false] - Include page screenshots (default: true)
    [format:plain|markdown|code] - Text formatting (default: markdown)
        Aliases: text=plain, txt=plain, md=markdown, code=html
    [select:css-selector] - CSS selector to extract specific elements (e.g., h1, .class, #id)
    [viewport:1280x720] - Browser viewport size (default: 1280x720)
    [fullpage:true|false] - Full page screenshot vs viewport only (default: true)
    [wait:2000] - Wait time in milliseconds for page to settle (default: 200)
    [split:paragraphs, sentences, tokens, lines, custom] - Content splitting strategy

Usage:
    # Explicit processor access
    result = processors.webpage_to_llm(attach("https://example.com"))
    
    # With CSS selector
    result = processors.webpage_to_llm(attach("https://example.com[select:h1]"))
    
    # With multiple DSL commands
    result = processors.webpage_to_llm(attach("https://example.com[select:.content][viewport:1920x1080][wait:1000]"))
    
    # Simple API (auto-detected)
    ctx = Attachments("https://example.com[select:title][format:plain][images:false]")
    text = str(ctx)
    images = ctx.images

CSS Selector Examples:
    [select:title] - Extract page title
    [select:h1] - Extract all h1 headings
    [select:.content] - Extract elements with class "content"
    [select:#main] - Extract element with id "main"
    [select:p] - Extract all paragraphs
    [select:article h2] - Extract h2 elements inside article tags
    [select:.post-content, .article-body] - Multiple selectors (comma-separated)

Future improvements:
- Element-specific screenshots (CSS selectors)
- Mobile viewport simulation
- PDF generation from web pages
- Interactive element detection
- Performance metrics capture
"""

from ..core import Attachment, AttachmentCollection
from ..matchers import webpage_match
from . import processor
from typing import Union
from ..config import verbose_log
from ..dsl_suggestion import suggest_format_command

@processor(
    match=webpage_match,
    description="Primary webpage processor with text extraction, CSS selection, and screenshot capabilities"
)
def webpage_to_llm(att: Attachment) -> Union[Attachment, AttachmentCollection]:
    """
    Process web pages for LLM consumption.
    
    Supports DSL commands:
    - format: plain, markdown (default), code for different text representations
    - select: CSS selector to extract specific elements (e.g., h1, .class, #id)
    - images: true (default), false to control screenshot capture
    - viewport: 1280x720 for browser viewport size
    - fullpage: true (default), false for viewport-only screenshots
    - wait: 2000 for page settling time in milliseconds
    - split: paragraphs, sentences, tokens, lines, custom for content splitting
    
    Text formats:
    - plain: Clean text extraction from page content
    - markdown: Structured markdown preserving some formatting (default)
    - code: Raw HTML structure for detailed analysis
    
    CSS Selection:
    - Supports any valid CSS selector
    - Examples: title, h1, .content, #main, p, article h2
    - Multiple selectors: .post-content, .article-body
    
    Screenshot capabilities:
    - Full page screenshots with JavaScript rendering
    - Customizable viewport sizes
    - Configurable wait times for dynamic content
    
    Split capabilities:
    - Split extracted content into chunks using various strategies
    - Works with all text formats and CSS selection
    """
    
    # Import namespaces properly to get VerbFunction wrappers
    from .. import load, present, refine, modify, split
    from ..core import AttachmentCollection
    
    # Determine text format from DSL commands
    format_cmd = att.commands.get('format', 'markdown')
    
    # Check for typos and suggest corrections
    suggestion = suggest_format_command(format_cmd)
    if suggestion:
        verbose_log(f"⚠️ Warning: Unknown format '{format_cmd}'. Did you mean '{suggestion}'? Defaulting to markdown.")
        format_cmd = 'markdown'
    
    # Handle format aliases
    format_aliases = {
        'text': 'plain',
        'txt': 'plain', 
        'md': 'markdown',
        'code': 'html'  # For webpages, code format shows HTML structure
    }
    format_cmd = format_aliases.get(format_cmd, format_cmd)
    
    # Determine if images should be included
    include_images = att.commands.get('images', 'true').lower() == 'true'
    
    # Determine if CSS selection should be applied
    has_selector = 'select' in att.commands
    
    # Build the pipeline based on format and image preferences
    if format_cmd == 'plain':
        # Plain text format
        text_presenter = present.text
    elif format_cmd == 'html':
        # HTML/code format - show raw HTML structure
        text_presenter = present.html
    else:
        # Default to markdown
        text_presenter = present.markdown
    
    # Build image pipeline if requested
    if include_images:
        image_pipeline = present.images
    else:
        # Empty pipeline that does nothing, but is now descriptive
        image_pipeline = refine.no_op
    
    # Build selection pipeline if CSS selector is provided
    if has_selector:
        selection_pipeline = modify.select
    else:
        # Empty pipeline that does nothing, but is now descriptive
        selection_pipeline = refine.no_op
    
    # First, process the content normally through the pipeline
    processed = (att 
                | load.url_to_bs4          # Load webpage content
                | selection_pipeline       # Apply CSS selector if specified
                | text_presenter + image_pipeline + present.metadata
                | refine.add_headers)
    
    # Check if split operation was requested
    splitter_name = att.commands.get('split')
    if splitter_name:
        try:
            # Get the splitter function from the split namespace
            splitter_func = getattr(split, splitter_name, None)
            if splitter_func is None:
                # Invalid splitter name - add error to metadata and return original
                processed.metadata['split_error'] = f"Unknown splitter: {splitter_name}"
                processed.text += f"\n\n⚠️ Warning: Unknown splitter '{splitter_name}'. Available splitters: paragraphs, sentences, tokens, lines, custom\n"
                return processed
            
            # Apply the splitter to the processed content
            split_result = splitter_func(processed)
            
            # Splitters return AttachmentCollection
            if isinstance(split_result, AttachmentCollection):
                return split_result
            else:
                # Fallback if splitter doesn't return collection
                return processed
                
        except Exception as e:
            # Handle splitter errors gracefully
            processed.metadata['split_error'] = f"Error applying splitter '{splitter_name}': {str(e)}"
            processed.text += f"\n\n⚠️ Error applying splitter '{splitter_name}': {str(e)}\n"
            return processed
    else:
        # No split requested, return single processed attachment
        return processed