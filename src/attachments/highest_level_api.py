#!/usr/bin/env python3
"""
Simple API for Attachments - One-line file to LLM context
=========================================================

High-level interface that abstracts the grammar complexity:
- Attachments(*paths) - automatic processing of any file types
- str(ctx) - combined, prompt-engineered text
- ctx.images - all base64 images ready for LLMs
"""

from typing import List, Union, Dict, Any
import os
from .core import Attachment, AttachmentCollection, attach, _loaders, _modifiers, _presenters, _adapters, _refiners, SmartVerbNamespace

# Import the namespace objects, not the raw modules
# We can't use relative imports for the namespaces since they're created in __init__.py
def _get_namespaces():
    """Get the namespace objects after they're created."""
    from attachments import load, present, refine, split, modify
    return load, present, refine, split, modify

# Global cache for namespaces to avoid repeated imports
_cached_namespaces = None

def _get_cached_namespaces():
    """Get cached namespace instances for better performance."""
    global _cached_namespaces
    if _cached_namespaces is None:
        _cached_namespaces = _get_namespaces()
    return _cached_namespaces

class Attachments:
    """
    High-level interface for converting files to LLM-ready context.
    
    Usage:
        ctx = Attachments("report.pdf", "photo.jpg[rotate:90]", "data.csv")
        text = str(ctx)          # All extracted text, prompt-engineered
        images = ctx.images      # List of base64 PNG strings
    """
    
    def __init__(self, *paths):
        """Initialize with one or more file paths (with optional DSL commands).
        
        Accepts:
        - Individual strings: Attachments('file1.pdf', 'file2.txt')
        - A single list: Attachments(['file1.pdf', 'file2.txt'])
        - Mixed: Attachments(['file1.pdf'], 'file2.txt')
        """
        self.attachments: List[Attachment] = []
        
        # Flatten arguments to handle both individual strings and lists
        flattened_paths = []
        for path in paths:
            if isinstance(path, (list, tuple)):
                flattened_paths.extend(path)
            else:
                flattened_paths.append(path)
        
        self._process_files(tuple(flattened_paths))
    
    def _process_files(self, paths: tuple) -> None:
        """Process all input files through universal pipeline."""
        # Get the proper namespaces
        load, present, refine, split, modify = _get_cached_namespaces()
        
        for path in paths:
            try:
                # Create attachment and apply universal auto-pipeline
                result = self._auto_process(attach(path))
                
                # Apply repository/directory presenters based on structure type
                if (isinstance(result, Attachment) and 
                    hasattr(result, '_obj') and 
                    isinstance(result._obj, dict) and 
                    result._obj.get('type') in ('git_repository', 'directory', 'size_warning')):
                    
                    # Always apply structure_and_metadata presenter
                    result = result | present.structure_and_metadata
                    
                    # Check if we should expand files (files:true mode)
                    if result._obj.get('process_files', False):
                        # This is files mode - expand individual files
                        files = result._obj['files']
                        
                        # Add directory summary as first attachment
                        self.attachments.append(result)
                        
                        # Process individual files
                        for file_path in files:
                            try:
                                file_result = self._auto_process(attach(file_path))
                                self.attachments.append(file_result)
                            except Exception as e:
                                # Create error attachment for failed files
                                error_att = attach(file_path)
                                error_att.text = f"Error processing {file_path}: {e}"
                                self.attachments.append(error_att)
                        
                        return  # Don't add the directory attachment again
                    else:
                        # This is structure+metadata only mode - just add the summary
                        self.attachments.append(result)
                        return
                
                # Handle regular collections (like ZIP files)
                elif isinstance(result, AttachmentCollection):
                    self.attachments.extend(result.attachments)
                elif isinstance(result, Attachment):
                    # Regular attachment (including structure/metadata modes)
                    # For structure/metadata modes, just add the single attachment with the formatted structure
                    self.attachments.append(result)
                    
            except Exception as e:
                # Create a fallback attachment with error info
                error_att = Attachment(path)
                error_att.text = f"⚠️ Could not process {path}: {str(e)}"
                error_att.metadata = {'error': str(e), 'path': path}
                self.attachments.append(error_att)
    
    def _auto_process(self, att: Attachment) -> Union[Attachment, AttachmentCollection]:
        """Enhanced auto-processing with processor discovery."""
        
        # 1. Try specialized processors first
        from .pipelines import find_primary_processor
        processor_fn = find_primary_processor(att)
        
        if processor_fn:
            try:
                return processor_fn(att)
            except Exception as e:
                # If processor fails, fall back to universal pipeline
                print(f"Processor failed for {att.path}: {e}, falling back to universal pipeline")
        
        # 2. Fallback to universal pipeline
        return self._universal_pipeline(att)
    
    def _universal_pipeline(self, att: Attachment) -> Union[Attachment, AttachmentCollection]:
        """Universal fallback pipeline for files without specialized processors."""
        
        # Get the proper namespaces
        load, present, refine, split, modify = _get_cached_namespaces()
        
        # NEW: Smart URL processing with morphing (replaces hardcoded url_to_file)
        # Order matters for proper fallback - URL processing comes first
        try:
            loaded = (att 
                     | load.url_to_response         # URLs → response object (new architecture)
                     | modify.morph_to_detected_type # response → morphed path (triggers matchers)
                     | load.url_to_bs4              # Non-file URLs → BeautifulSoup (fallback)
                     | load.git_repo_to_structure   # Git repos → structure object
                     | load.directory_to_structure  # Directories/globs → structure object
                     | load.svg_to_svgdocument      # SVG → SVGDocument object
                     | load.eps_to_epsdocument      # EPS → EPSDocument object
                     | load.pdf_to_pdfplumber       # PDF → pdfplumber object
                     | load.csv_to_pandas           # CSV → pandas DataFrame  
                     | load.image_to_pil            # Images → PIL Image
                     | load.html_to_bs4             # HTML → BeautifulSoup
                     | load.text_to_string          # Text → string
                     | load.zip_to_images)          # ZIP → AttachmentCollection (last)
        except Exception as e:
            # If loading fails, create a basic attachment with the file content
            loaded = att
            try:
                # Try basic text loading as last resort
                if os.path.exists(att.path):
                    with open(att.path, 'r', encoding='utf-8', errors='ignore') as f:
                        loaded.text = f.read()
                        loaded._obj = loaded.text
            except:
                loaded.text = f"Could not read file: {att.path}"
        
        # Handle collections differently
        if isinstance(loaded, AttachmentCollection):
            # Vectorized processing for collections
            processed = (loaded 
                        | (present.images + present.metadata)
                        | refine.tile_images | refine.add_headers)
            return processed
        else:
            # Check if this is a repository/directory structure
            if hasattr(loaded, '_obj') and isinstance(loaded._obj, dict) and loaded._obj.get('type') in ('git_repository', 'directory', 'size_warning'):
                # Repository/directory structure - always use structure_and_metadata presenter
                processed = loaded | present.structure_and_metadata
                return processed
            else:
                # Single file processing with smart presenter selection
                # Use smart presenter selection that respects DSL format commands
                text_presenter = _get_smart_text_presenter(loaded)
                
                processed = (loaded
                            | modify.pages  # Apply page selection commands like [3-5]
                            | (text_presenter + present.images + present.metadata)
                            | refine.tile_images | refine.add_headers)
                
                return processed
    
    def __str__(self) -> str:
        """Return all extracted text in a prompt-engineered format."""
        if not self.attachments:
            return ""
        
        text_sections = []
        
        for i, att in enumerate(self.attachments):
            if att.text:
                # Add file header if multiple files AND text doesn't already have a header
                if len(self.attachments) > 1:
                    filename = att.path or f"File {i+1}"
                    
                    # Check if text already starts with a header for this file
                    # Common patterns from presenters
                    basename = os.path.basename(filename)
                    
                    header_patterns = [
                        f"# {filename}",
                        f"# {basename}",  
                        f"# PDF Document: {filename}",
                        f"# PDF Document: {basename}",
                        f"# Image: {filename}",
                        f"# Image: {basename}",
                        f"# Presentation: {filename}",
                        f"# Presentation: {basename}",
                        f"## Data from {filename}",
                        f"## Data from {basename}",
                        f"Data from {filename}",
                        f"Data from {basename}",
                        f"PDF Document: {filename}",
                        f"PDF Document: {basename}",
                    ]
                    
                    # Check if text already has a header
                    has_header = any(att.text.strip().startswith(pattern) for pattern in header_patterns)
                    
                    if has_header:
                        section = att.text
                    else:
                        section = f"## {filename}\n\n{att.text}"
                else:
                    section = att.text
                
                text_sections.append(section)
        
        combined_text = "\n\n---\n\n".join(text_sections)
        
        # Add metadata summary if useful
        if len(self.attachments) > 1:
            file_count = len(self.attachments)
            image_count = len(self.images)
            summary = f"📄 Processing Summary: {file_count} files processed"
            if image_count > 0:
                summary += f", {image_count} images extracted"
            combined_text = f"{summary}\n\n{combined_text}"
        
        return combined_text
    
    @property
    def images(self) -> List[str]:
        """Return all base64-encoded images ready for LLM APIs."""
        all_images = []
        for att in self.attachments:
            # Filter out placeholder images
            real_images = [img for img in att.images 
                          if img and not img.endswith('_placeholder')]
            all_images.extend(real_images)
        return all_images
    
    @property
    def text(self) -> str:
        """Return concatenated text from all attachments."""
        return str(self)  # Use our formatted __str__ method which already does this properly
    
    @property 
    def metadata(self) -> dict:
        """Return combined metadata from all processed files."""
        combined_meta = {
            'file_count': len(self.attachments),
            'image_count': len(self.images),
            'files': []
        }
        
        for att in self.attachments:
            file_meta = {
                'path': att.path,
                'text_length': len(att.text) if att.text else 0,
                'image_count': len([img for img in att.images 
                                  if not img.endswith('_placeholder')]),
                'metadata': att.metadata
            }
            combined_meta['files'].append(file_meta)
        
        return combined_meta
    
    def __len__(self) -> int:
        """Return number of processed files/attachments."""
        return len(self.attachments)
    
    def __getitem__(self, index: int) -> Attachment:
        """Make Attachments indexable like a list."""
        return self.attachments[index]
    
    def __iter__(self):
        """Make Attachments iterable."""
        return iter(self.attachments)
    
    def __repr__(self) -> str:
        """Detailed representation for debugging."""
        if not self.attachments:
            return "Attachments(empty)"
            
        file_info = []
        for att in self.attachments:
            # Get file extension or type
            if att.path:
                ext = att.path.split('.')[-1].lower() if '.' in att.path else 'unknown'
            else:
                ext = 'unknown'
            
            # Summarize content
            text_len = len(att.text) if att.text else 0
            img_count = len([img for img in att.images if img and not img.endswith('_placeholder')])
            
            # Show shortened base64 for images
            img_preview = ""
            if img_count > 0:
                first_img = next((img for img in att.images if img and not img.endswith('_placeholder')), "")
                if first_img:
                    if first_img.startswith('data:image/'):
                        img_preview = f", img: {first_img[:30]}...{first_img[-10:]}"
                    else:
                        img_preview = f", img: {first_img[:20]}...{first_img[-10:]}"
            
            file_info.append(f"{ext}({text_len}chars, {img_count}imgs{img_preview})")
        
        return f"Attachments([{', '.join(file_info)}])"
    
    def __getattr__(self, name: str):
        """Automatically expose all adapters as methods on Attachments objects."""
        # Import here to avoid circular imports
        from .core import _adapters
        
        if name in _adapters:
            def adapter_method(*args, **kwargs):
                """Dynamically created adapter method."""
                adapter_fn = _adapters[name]
                combined_att = self._to_single_attachment()
                return adapter_fn(combined_att, *args, **kwargs)
            return adapter_method
        
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")
    
    def _to_single_attachment(self) -> Attachment:
        """Convert to single attachment for API adapters."""
        if not self.attachments:
            return Attachment("")
        
        combined = Attachment("")
        combined.text = str(self)  # Use our formatted text
        combined.images = self.images
        combined.metadata = self.metadata
        
        return combined


# Convenience function for even simpler usage
def process(*paths: str) -> Attachments:
    """
    Process files and return Attachments object.
    
    Usage:
        ctx = process("report.pdf", "image.jpg")
        text = str(ctx)
        images = ctx.images
    """
    return Attachments(*paths)

def _get_smart_text_presenter(att: Attachment):
    """Select the appropriate text presenter based on DSL format commands."""
    load, present, refine, split, modify = _get_cached_namespaces()
    
    # Get format command (default to markdown)
    format_cmd = att.commands.get('format', 'markdown')
    
    # Map format commands to presenters
    if format_cmd in ('plain', 'text', 'txt'):
        return present.text
    elif format_cmd in ('code', 'html', 'structured'):
        return present.html
    elif format_cmd in ('markdown', 'md'):
        return present.markdown
    elif format_cmd in ('xml',):
        return present.xml
    elif format_cmd in ('csv',):
        return present.csv
    else:
        # Default to markdown for unknown formats
        return present.markdown 