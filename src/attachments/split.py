"""Splitting/chunking functions that convert single attachments into collections.

Split functions are "expanders" - they take one attachment and return an AttachmentCollection.
This follows the pattern of zip_to_images but works on already-loaded content.
"""

from .core import Attachment, AttachmentCollection, splitter
import re
from typing import List


# --- TEXT SPLITTING (works on attachments with text content) ---

@splitter
def paragraphs(att: Attachment, text: str) -> AttachmentCollection:
    """Split text content into paragraphs."""
    # Use the text from att.text if available, otherwise use passed text parameter
    content = att.text if att.text else text
    if not content:
        return AttachmentCollection([att])
    
    # Split on double newlines (paragraph breaks)
    paragraphs = re.split(r'\n\s*\n', content.strip())
    paragraphs = [p.strip() for p in paragraphs if p.strip()]
    
    if not paragraphs:
        return AttachmentCollection([att])
    
    chunks = []
    for i, paragraph in enumerate(paragraphs):
        chunk = Attachment(f"{att.path}#paragraph-{i+1}")
        chunk.text = paragraph
        chunk.commands = att.commands.copy()
        chunk.metadata = {
            **att.metadata,
            'chunk_type': 'paragraph',
            'chunk_index': i,
            'total_chunks': len(paragraphs),
            'original_path': att.path
        }
        chunks.append(chunk)
    
    return AttachmentCollection(chunks)


@splitter
def sentences(att: Attachment, text: str) -> AttachmentCollection:
    """Split text content into sentences."""
    # Use the text from att.text if available, otherwise use passed text parameter
    content = att.text if att.text else text
    if not content:
        return AttachmentCollection([att])
    
    # Simple sentence splitting (could be enhanced with NLTK for better accuracy)
    sentences = re.split(r'[.!?]+\s+', content.strip())
    sentences = [s.strip() for s in sentences if s.strip()]
    
    if not sentences:
        return AttachmentCollection([att])
    
    chunks = []
    for i, sentence in enumerate(sentences):
        chunk = Attachment(f"{att.path}#sentence-{i+1}")
        chunk.text = sentence
        chunk.commands = att.commands.copy()
        chunk.metadata = {
            **att.metadata,
            'chunk_type': 'sentence',
            'chunk_index': i,
            'total_chunks': len(sentences),
            'original_path': att.path
        }
        chunks.append(chunk)
    
    return AttachmentCollection(chunks)


@splitter
def characters(att: Attachment, text: str) -> AttachmentCollection:
    """Split text content by character count."""
    # Use the text from att.text if available, otherwise use passed text parameter
    content = att.text if att.text else text
    if not content:
        return AttachmentCollection([att])
    
    # Get char limit from DSL commands or default
    char_limit = int(att.commands.get('characters', 1000))
    
    chunks = []
    
    for i in range(0, len(content), char_limit):
        chunk_text = content[i:i + char_limit]
        
        chunk = Attachment(f"{att.path}#chars-{i+1}-{min(i+char_limit, len(content))}")
        chunk.text = chunk_text
        chunk.commands = att.commands.copy()
        chunk.metadata = {
            **att.metadata,
            'chunk_type': 'characters',
            'chunk_index': i // char_limit,
            'char_start': i,
            'char_end': min(i + char_limit, len(content)),
            'char_limit': char_limit,
            'original_path': att.path
        }
        chunks.append(chunk)
    
    return AttachmentCollection(chunks)


@splitter
def tokens(att: Attachment, text: str) -> AttachmentCollection:
    """Split text content by approximate token count (for LLM contexts)."""
    # Use the text from att.text if available, otherwise use passed text parameter
    content = att.text if att.text else text
    if not content:
        return AttachmentCollection([att])
    
    # Get token limit from DSL commands or default
    token_limit = int(att.commands.get('tokens', 500))
    
    # Simple token approximation: ~4 characters per token on average
    char_limit = token_limit * 4
    
    # Use character splitting as base, but try to break on word boundaries
    chunks = []
    current_pos = 0
    chunk_index = 0
    
    while current_pos < len(content):
        end_pos = min(current_pos + char_limit, len(content))
        
        # Try to break on word boundary if not at end of text
        if end_pos < len(content):
            # Look backwards for a space or punctuation
            while end_pos > current_pos and content[end_pos] not in ' \n\t.,!?;:':
                end_pos -= 1
            
            # If we couldn't find a good break point, use char limit
            if end_pos == current_pos:
                end_pos = min(current_pos + char_limit, len(content))
        
        chunk_text = content[current_pos:end_pos].strip()
        
        if chunk_text:
            chunk = Attachment(f"{att.path}#tokens-{chunk_index+1}")
            chunk.text = chunk_text
            chunk.commands = att.commands.copy()
            chunk.metadata = {
                **att.metadata,
                'chunk_type': 'tokens',
                'chunk_index': chunk_index,
                'token_limit': token_limit,
                'estimated_tokens': len(chunk_text) // 4,
                'char_start': current_pos,
                'char_end': end_pos,
                'original_path': att.path
            }
            chunks.append(chunk)
            chunk_index += 1
        
        current_pos = end_pos
    
    return AttachmentCollection(chunks)


@splitter
def lines(att: Attachment, text: str) -> AttachmentCollection:
    """Split text content by line count."""
    # Use the text from att.text if available, otherwise use passed text parameter
    content = att.text if att.text else text
    if not content:
        return AttachmentCollection([att])
    
    # Get lines per chunk from DSL commands or default
    lines_per_chunk = int(att.commands.get('lines', 50))
    
    text_lines = content.split('\n')
    chunks = []
    
    for i in range(0, len(text_lines), lines_per_chunk):
        chunk_lines = text_lines[i:i + lines_per_chunk]
        chunk_text = '\n'.join(chunk_lines)
        
        chunk = Attachment(f"{att.path}#lines-{i+1}-{min(i+lines_per_chunk, len(text_lines))}")
        chunk.text = chunk_text
        chunk.commands = att.commands.copy()
        chunk.metadata = {
            **att.metadata,
            'chunk_type': 'lines',
            'chunk_index': i // lines_per_chunk,
            'line_start': i + 1,
            'line_end': min(i + lines_per_chunk, len(text_lines)),
            'lines_per_chunk': lines_per_chunk,
            'original_path': att.path
        }
        chunks.append(chunk)
    
    return AttachmentCollection(chunks)


# --- OBJECT-BASED SPLITTING (works on specific object types) ---

@splitter  
def pages(att: Attachment, pdf: 'pdfplumber.PDF') -> AttachmentCollection:
    """Split PDF into individual page attachments."""
    chunks = []
    
    for page_num, page in enumerate(pdf.pages, 1):
        chunk = Attachment(f"{att.path}#page-{page_num}")
        chunk._obj = pdf  # Store original PDF object for compatibility with presenters
        chunk.commands = att.commands.copy()
        chunk.metadata = {
            **att.metadata,
            'chunk_type': 'page',
            'page_number': page_num,
            'total_pages': len(pdf.pages),
            'original_path': att.path,
            'selected_pages': [page_num]  # For compatibility with existing presenters
        }
        chunks.append(chunk)
    
    return AttachmentCollection(chunks)


@splitter
def slides(att: Attachment, pres: 'pptx.Presentation') -> AttachmentCollection:
    """Split PowerPoint into individual slide attachments."""
    chunks = []
    
    for slide_num, slide in enumerate(pres.slides, 1):
        chunk = Attachment(f"{att.path}#slide-{slide_num}")
        chunk._obj = pres  # Keep original presentation but mark specific slide
        chunk.commands = att.commands.copy()
        chunk.metadata = {
            **att.metadata,
            'chunk_type': 'slide',
            'slide_number': slide_num,
            'total_slides': len(pres.slides),
            'original_path': att.path,
            'selected_slides': [slide_num - 1]  # 0-based for compatibility
        }
        chunks.append(chunk)
    
    return AttachmentCollection(chunks)


@splitter
def rows(att: Attachment, df: 'pandas.DataFrame') -> AttachmentCollection:
    """Split DataFrame into row-based chunks."""
    # Get rows per chunk from DSL commands or default
    rows_per_chunk = int(att.commands.get('rows', 100))
    
    chunks = []
    
    for i in range(0, len(df), rows_per_chunk):
        chunk_df = df.iloc[i:i + rows_per_chunk].copy()
        
        chunk = Attachment(f"{att.path}#rows-{i+1}-{min(i+rows_per_chunk, len(df))}")
        chunk._obj = chunk_df
        chunk.commands = att.commands.copy()
        chunk.metadata = {
            **att.metadata,
            'chunk_type': 'rows',
            'chunk_index': i // rows_per_chunk,
            'row_start': i,
            'row_end': min(i + rows_per_chunk, len(df)),
            'rows_per_chunk': rows_per_chunk,
            'chunk_shape': chunk_df.shape,
            'original_path': att.path
        }
        chunks.append(chunk)
    
    return AttachmentCollection(chunks)


@splitter
def columns(att: Attachment, df: 'pandas.DataFrame') -> AttachmentCollection:
    """Split DataFrame into column-based chunks."""
    # Get columns per chunk from DSL commands or default
    cols_per_chunk = int(att.commands.get('columns', 10))
    
    chunks = []
    columns = df.columns.tolist()
    
    for i in range(0, len(columns), cols_per_chunk):
        chunk_cols = columns[i:i + cols_per_chunk]
        chunk_df = df[chunk_cols].copy()
        
        chunk = Attachment(f"{att.path}#cols-{i+1}-{min(i+cols_per_chunk, len(columns))}")
        chunk._obj = chunk_df
        chunk.commands = att.commands.copy()
        chunk.metadata = {
            **att.metadata,
            'chunk_type': 'columns',
            'chunk_index': i // cols_per_chunk,
            'column_start': i,
            'column_end': min(i + cols_per_chunk, len(columns)),
            'cols_per_chunk': cols_per_chunk,
            'chunk_columns': chunk_cols,
            'chunk_shape': chunk_df.shape,
            'original_path': att.path
        }
        chunks.append(chunk)
    
    return AttachmentCollection(chunks)


@splitter
def sections(att: Attachment, soup: 'bs4.BeautifulSoup') -> AttachmentCollection:
    """Split HTML content by sections (h1, h2, etc. headings)."""
    try:
        from bs4 import BeautifulSoup
        
        # Find all heading elements
        headings = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
        
        if not headings:
            # No headings found, return original
            return AttachmentCollection([att])
        
        chunks = []
        
        for i, heading in enumerate(headings):
            # Find all content between this heading and the next
            section_content = [heading]
            
            # Get next sibling elements until we hit another heading
            current = heading.next_sibling
            while current:
                if current.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                    break
                if hasattr(current, 'name'):  # It's a tag
                    section_content.append(current)
                current = current.next_sibling
            
            # Create new soup with just this section
            section_html = ''.join(str(elem) for elem in section_content)
            section_soup = BeautifulSoup(section_html, 'html.parser')
            
            chunk = Attachment(f"{att.path}#section-{i+1}")
            chunk._obj = section_soup
            chunk.commands = att.commands.copy()
            chunk.metadata = {
                **att.metadata,
                'chunk_type': 'section',
                'section_index': i,
                'section_heading': heading.get_text().strip(),
                'heading_level': heading.name,
                'total_sections': len(headings),
                'original_path': att.path
            }
            chunks.append(chunk)
        
        return AttachmentCollection(chunks)
        
    except ImportError:
        raise ImportError("BeautifulSoup4 is required for HTML section splitting")


# --- CUSTOM SPLITTING ---

@splitter
def custom(att: Attachment, text: str) -> AttachmentCollection:
    """Split text content by custom separator."""
    # Use the text from att.text if available, otherwise use passed text parameter
    content = att.text if att.text else text
    if not content:
        return AttachmentCollection([att])
    
    # Get separator from DSL commands or default
    separator = att.commands.get('custom', '\n---\n')
    
    parts = content.split(separator)
    parts = [p.strip() for p in parts if p.strip()]
    
    if not parts:
        return AttachmentCollection([att])
    
    chunks = []
    for i, part in enumerate(parts):
        chunk = Attachment(f"{att.path}#custom-{i+1}")
        chunk.text = part
        chunk.commands = att.commands.copy()
        chunk.metadata = {
            **att.metadata,
            'chunk_type': 'custom',
            'chunk_index': i,
            'separator': separator,
            'total_chunks': len(parts),
            'original_path': att.path
        }
        chunks.append(chunk)
    
    return AttachmentCollection(chunks) 