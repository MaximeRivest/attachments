"""
CSV to LLM Pipeline Processor
=============================

Complete pipeline for processing CSV files optimized for LLM consumption.
Supports clean DSL commands for the Attachments() simple API.

DSL Commands:
    [summary:true|false] - Include summary statistics (default: false)
    [head:true|false] - Include data preview (default: false)
    [format:plain|markdown|csv] - Text formatting (default: markdown)
        Aliases: text=plain, txt=plain, md=markdown
    [limit:N] - Limit number of rows (inherits from existing modify.limit)

Usage:
    # Explicit processor access
    result = processors.csv_to_llm(attach("data.csv"))
    
    # With DSL commands
    result = processors.csv_to_llm(attach("data.csv[summary:true][head:true]"))
    result = processors.csv_to_llm(attach("data.csv[format:plain][limit:100]"))
    
    # Simple API (auto-detected)
    ctx = Attachments("data.csv[summary:true][head:true]")
    text = str(ctx)
"""

from ..core import Attachment
from ..matchers import csv_match
from . import processor

@processor(
    match=csv_match,
    description="Primary CSV processor with summary and preview capabilities"
)
def csv_to_llm(att: Attachment) -> Attachment:
    """
    Process CSV files for LLM consumption.
    
    Supports DSL commands:
    - summary: true, false (default: false) - Include summary statistics
    - head: true, false (default: false) - Include data preview
    - format: plain, markdown (default), csv for different text representations
    - limit: N for row limiting
    
    Text formats:
    - plain: Clean text representation
    - markdown: Structured markdown with tables (default)
    - csv: Raw CSV format
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
    
    # Build the pipeline based on format and DSL commands
    if format_cmd == 'plain':
        text_presenter = present.text
    elif format_cmd == 'csv':
        text_presenter = present.csv
    else:
        # Default to markdown
        text_presenter = present.markdown
    
    # Start with base pipeline
    pipeline_presenters = [text_presenter]
    
    # Check for summary command
    if att.commands.get('summary', 'false').lower() == 'true':
        pipeline_presenters.append(present.summary)
    
    # Check for head command
    if att.commands.get('head', 'false').lower() == 'true':
        pipeline_presenters.append(present.head)
    
    # Always include metadata
    pipeline_presenters.append(present.metadata)
    
    # Combine all presenters
    combined_presenter = pipeline_presenters[0]
    for presenter in pipeline_presenters[1:]:
        combined_presenter = combined_presenter + presenter
    
    # Build the complete pipeline
    return (att 
           | load.url_to_response      # Handle URLs with new morphing architecture
           | modify.morph_to_detected_type  # Smart detection replaces hardcoded url_to_file
           | load.csv_to_pandas        # Then load as pandas DataFrame
           | modify.limit              # Apply row limiting if specified
           | combined_presenter        # Apply all selected presenters
           | refine.add_headers)       # Add headers for context 