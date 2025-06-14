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
from .config import verbose_log
from .dsl_suggestion import find_closest_command, suggest_format_command

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

        # After all processing, check for unused commands
        from .config import verbose_log
        from .core import CommandDict, AttachmentCollection
        from . import refine

        try:
            # Group attachments that came from the same split operation
            command_groups = {} # id(CommandDict) -> list[Attachment]
            standalone_attachments = []

            for att in self.attachments:
                if hasattr(att, 'commands') and isinstance(att.commands, CommandDict):
                    # Check if it looks like a chunk from a split
                    if 'original_path' in att.metadata:
                        cmd_id = id(att.commands)
                        if cmd_id not in command_groups:
                            command_groups[cmd_id] = []
                        command_groups[cmd_id].append(att)
                    else:
                        standalone_attachments.append(att)
                else:
                    # Keep non-command attachments as standalone
                    standalone_attachments.append(att)
            
            # Report for standalone attachments
            for att in standalone_attachments:
                refine.report_unused_commands(att)
            
            # Report for grouped chunks
            for group in command_groups.values():
                collection = AttachmentCollection(group)
                refine.report_unused_commands(collection)

        except Exception as e:
            verbose_log(f"Error during final command check: {e}")
    
    def _apply_splitter_and_add_to_list(self, item: Union[Attachment, AttachmentCollection], 
                                       splitter_func: callable, target_list: List[Attachment], 
                                       original_path: str) -> None:
        """Apply splitter function to item and add results to target list."""
        if splitter_func is None:
            # No splitting requested
            if isinstance(item, Attachment):
                target_list.append(item)
            elif isinstance(item, AttachmentCollection):
                target_list.extend(item.attachments)
            return
        
        try:
            if isinstance(item, Attachment):
                # Apply splitter to single attachment
                split_result = splitter_func(item)
                if isinstance(split_result, AttachmentCollection):
                    target_list.extend(split_result.attachments)
                else:
                    # Fallback: if splitter doesn't return collection, add original
                    target_list.append(item)
            elif isinstance(item, AttachmentCollection):
                # Apply splitter to each attachment in collection
                for sub_att in item.attachments:
                    self._apply_splitter_and_add_to_list(sub_att, splitter_func, target_list, original_path)
        except Exception as e:
            # Create error attachment for failed splitting
            error_att = Attachment(original_path)
            error_att.text = f"⚠️ Error applying split operation: {str(e)}"
            error_att.metadata = {'split_error': str(e), 'original_path': original_path}
            target_list.append(error_att)
    
    def _get_splitter_function(self, splitter_name: str):
        """Get splitter function from split namespace."""
        if not splitter_name:
            return None
        
        try:
            load, present, refine, split, modify = _get_cached_namespaces()
            splitter_func = getattr(split, splitter_name, None)
            if splitter_func is None:
                # Command was invalid. Let's try to find a suggestion.
                valid_splitters = [s for s in dir(split) if not s.startswith('_')]
                suggestion = find_closest_command(splitter_name, valid_splitters)
                if suggestion:
                    verbose_log(f"⚠️ Warning: Unknown splitter '{splitter_name}'. Did you mean '{suggestion}'?")
                else:
                    verbose_log(f"⚠️ Warning: Unknown splitter '{splitter_name}'. Valid options are: {valid_splitters}")
                return None # Return None to indicate failure
                
            return splitter_func
        except Exception as e:
            raise ValueError(f"Error getting splitter '{splitter_name}': {e}")
    
    def _process_files(self, paths: tuple) -> None:
        """Process all input files through universal pipeline with split support."""
        # Get the proper namespaces
        load, present, refine, split, modify = _get_cached_namespaces()
        
        for path in paths:
            try:
                # Extract split command from the original path DSL
                initial_att = attach(path)
                splitter_name = initial_att.commands.get('split')
                splitter_func = self._get_splitter_function(splitter_name) if splitter_name else None
                
                # If splitter was invalid, splitter_func will be None. We should not proceed with a split.
                # The warning has already been logged.
                
                # Create attachment and apply universal auto-pipeline
                result = self._auto_process(initial_att)
                
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
                        
                        # Add directory summary as first attachment (NO SPLIT on summary)
                        self.attachments.append(result)
                        
                        # Process individual files and apply splitter to each
                        for file_path in files:
                            try:
                                file_result = self._auto_process(attach(file_path))
                                # Apply splitter to individual file (inherit from directory DSL)
                                self._apply_splitter_and_add_to_list(file_result, splitter_func, self.attachments, path)
                            except Exception as e:
                                # Create error attachment for failed files
                                error_att = attach(file_path)
                                error_att.text = f"Error processing {file_path}: {e}"
                                self.attachments.append(error_att)
                        
                        continue  # Don't add the directory attachment again
                    else:
                        # This is structure+metadata only mode - add the summary (NO SPLIT on summary)
                        self.attachments.append(result)
                        continue
                
                # Check if the processor already applied splitting (returns AttachmentCollection)
                elif isinstance(result, AttachmentCollection):
                    # Processor already handled splitting, add all results
                    self.attachments.extend(result.attachments)
                    continue
                
                # Handle regular single files - apply splitter if requested and not already applied
                # Apply splitter to the result only if processor didn't already split
                self._apply_splitter_and_add_to_list(result, splitter_func, self.attachments, path)
                    
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
    
    # Check for typos and suggest corrections
    suggestion = suggest_format_command(format_cmd)
    if suggestion:
        verbose_log(f"⚠️ Warning: Unknown format '{format_cmd}'. Did you mean '{suggestion}'? Defaulting to markdown.")
        format_cmd = 'markdown' # Fallback to default if there was a typo

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

def auto_attach(prompt: str, root_dir: Union[str, List[str]] = None) -> Attachments:
    """
    Automatically detect and attach files mentioned in a prompt.
    
    This is the magical function that:
    1. Parses your prompt to find file references (with DSL support!)
    2. Automatically attaches those files from multiple root directories/URLs
    3. Combines the original prompt with extracted content
    4. Returns an Attachments object ready for any adapter
    
    Args:
        prompt: The prompt text that may contain file references
        root_dir: Directory/URL or list of directories/URLs to search for files
    
    Returns:
        Attachments object with the original prompt + detected files content
    
    Usage:
        att = auto_attach("describe sample.pdf[pages:1-3] and data.csv", 
                         root_dir=["/path/to/files", "https://example.com"])
        result = att.openai_responses()
    """
    import os
    import re
    from pathlib import Path
    from typing import Union, List
    
    # Normalize root_dir to a list
    if root_dir is None:
        root_dirs = [os.getcwd()]
    elif isinstance(root_dir, str):
        root_dirs = [root_dir]
    else:
        root_dirs = list(root_dir)
    
    # Enhanced pattern to detect files with optional DSL commands
    # Matches: filename.ext[dsl:commands] or just filename.ext
    file_patterns = [
        r'\b([a-zA-Z0-9_.-]+\.[a-zA-Z0-9]+(?:\[[^\]]*\])?)\b',  # filename.ext[dsl] or filename.ext
        r'"([^"]+\.[a-zA-Z0-9]+(?:\[[^\]]*\])?)"',               # "filename.ext[dsl]"
        r"'([^']+\.[a-zA-Z0-9]+(?:\[[^\]]*\])?)'",               # 'filename.ext[dsl]'
        r'`([^`]+\.[a-zA-Z0-9]+(?:\[[^\]]*\])?)`',               # `filename.ext[dsl]`
        # Also detect full URLs with optional DSL - handle spaces in brackets
        r'(https?://[^\s\[\]]+(?:\[[^\]]*\])?)',                 # https://example.com/path[dsl with spaces]
    ]
    
    detected_references = set()
    
    for pattern in file_patterns:
        matches = re.findall(pattern, prompt)
        for match in matches:
            detected_references.add(match)
    
    # Process each detected reference
    valid_attachments = []
    
    for reference in detected_references:
        # Check if it's a URL
        if reference.startswith(('http://', 'https://')):
            # For URLs, try to process directly
            try:
                test_att = Attachment(reference)
                valid_attachments.append(reference)
                continue
            except Exception:
                # If direct URL fails, try with root URLs
                for root in root_dirs:
                    if root.startswith(('http://', 'https://')):
                        # Try combining URL roots
                        try:
                            # Extract base filename/path from reference
                            base_ref = reference.split('[')[0]  # Remove DSL for URL construction
                            if not base_ref.startswith(('http://', 'https://')):
                                continue
                            
                            # Try the reference as-is first
                            test_att = Attachment(reference)
                            valid_attachments.append(reference)
                            break
                        except Exception:
                            continue
        else:
            # It's a file reference - try with each root directory
            found = False
            for root in root_dirs:
                if root.startswith(('http://', 'https://')):
                    # Skip URL roots for non-URL references - they don't make sense to combine
                    continue
                else:
                    # Try with file system root
                    file_path = os.path.join(root, reference)
                    if os.path.exists(file_path.split('[')[0]):  # Check if base file exists
                        try:
                            test_att = Attachment(reference if os.path.isabs(reference) else file_path)
                            valid_attachments.append(reference if os.path.isabs(reference) else file_path)
                            found = True
                            break
                        except Exception:
                            continue
    
    # Create Attachments object with found files
    if valid_attachments:
        attachments_obj = Attachments(*valid_attachments)
        
        # Now the magic: prepend the original prompt to the combined text
        original_text = str(attachments_obj)
        
        # Create a new Attachments object that combines everything
        class MagicalAttachments(Attachments):
            def __init__(self, original_prompt, base_attachments):
                # Don't call super().__init__ to avoid reprocessing files
                self.attachments = base_attachments.attachments.copy()
                self._original_prompt = original_prompt
                self._base_text = str(base_attachments)
            
            def __str__(self) -> str:
                """Return the magical combined text: prompt + file content."""
                return f"{self._original_prompt.strip()}\n\n{self._base_text}"
            
            @property
            def text(self) -> str:
                """Return the magical combined text."""
                return str(self)
            
            # Override adapter methods to include the prompt
            def __getattr__(self, name: str):
                """Automatically expose all adapters with the magical prompt included."""
                from .core import _adapters
                
                if name in _adapters:
                    def magical_adapter_method(*args, **kwargs):
                        """Dynamically created adapter method with magical prompt."""
                        adapter_fn = _adapters[name]
                        combined_att = self._to_single_attachment()
                        return adapter_fn(combined_att, *args, **kwargs)
                    return magical_adapter_method
                
                # Fall back to parent behavior
                return super().__getattr__(name)
            
            def _to_single_attachment(self) -> Attachment:
                """Convert to single attachment with magical combined text."""
                if not self.attachments:
                    combined = Attachment("")
                    combined.text = self._original_prompt
                    return combined
                
                combined = Attachment("")
                combined.text = str(self)  # Use our magical __str__ method
                combined.images = self.images
                combined.metadata = self.metadata
                
                return combined
        
        return MagicalAttachments(prompt, attachments_obj)
    else:
        # No files found, return an Attachments object with just the prompt
        class PromptOnlyAttachments(Attachments):
            def __init__(self, prompt_text):
                # Don't call super().__init__ to avoid file processing
                self.attachments = []
                self._prompt_text = prompt_text
            
            def __str__(self) -> str:
                return self._prompt_text
            
            @property
            def text(self) -> str:
                return self._prompt_text
            
            @property
            def images(self) -> List[str]:
                return []
            
            @property
            def metadata(self) -> dict:
                return {'prompt_only': True, 'original_prompt': self._prompt_text}
            
            def __getattr__(self, name: str):
                """Automatically expose all adapters for prompt-only usage."""
                from .core import _adapters
                
                if name in _adapters:
                    def prompt_adapter_method(*args, **kwargs):
                        """Adapter method for prompt-only usage."""
                        adapter_fn = _adapters[name]
                        # Create a simple attachment with just the prompt
                        att = Attachment("")
                        att.text = self._prompt_text
                        return adapter_fn(att, *args, **kwargs)
                    return prompt_adapter_method
                
                raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")
        
        return PromptOnlyAttachments(prompt) 