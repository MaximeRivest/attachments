"""
Attachments - the Python funnel for LLM context

Turn any file into model-ready text + images, in one line.
"""

from pathlib import Path
from typing import List, Dict, Any, Union, Optional
import re

# Version information
__version__ = "0.4.0"

# Import core components 
from .core import Attachment, load, modify, present, adapt

# Import all components to auto-register them
from . import loaders
from . import modifiers  
from . import presenters
from . import adapters
from .utils.parsing import parse_path_expression

# Register adapter methods on Attachments class after adapters are loaded
from .core.decorators import _register_adapter_methods_on_attachments

class Attachments:
    """
    High-level interface for processing multiple files into LLM-ready context.
    
    Usage:
        ctx = Attachments("report.pdf", "photo.jpg[rotate:90]", "data.csv[summary:true]")
        print(ctx)            # formatted text view
        len(ctx.images)       # base64 images count
        ctx.to_openai("...")  # OpenAI API format
        ctx.to_claude("...")  # Claude API format
    """
    
    def __init__(self, *sources: str):
        """
        Initialize with multiple file sources.
        
        Args:
            *sources: File paths or URLs, optionally with DSL commands like:
                     "file.pdf[pages:1-3]", "image.jpg[rotate:90]", "data.csv[summary:true]"
        """
        self.sources = list(sources)
        self.attachments: List[Attachment] = []
        self._text_cache: Optional[str] = None
        self._images_cache: Optional[List[str]] = None
        
        # Process each source
        for source in sources:
            try:
                attachment = self._process_source(source)
                if attachment:
                    self.attachments.append(attachment)
            except Exception as e:
                print(f"Warning: Failed to process {source}: {e}")
    
    def _process_source(self, source: str) -> Optional[Attachment]:
        """
        Process a single source using idiomatic low-level API.
        
        Follows the clean pipeline approach from README:
        load -> modify -> present -> adapt
        """
        try:
            # Parse DSL commands from source
            actual_path, commands = parse_path_expression(source)
            
            # Step 0: Check if path exists (for local files, not URLs)
            if not self._is_url(actual_path):
                path_obj = Path(actual_path)
                if not path_obj.exists():
                    print(f"Warning: File not found: {actual_path}")
                    return None
                if not path_obj.is_file():
                    print(f"Warning: Path is not a file: {actual_path}")
                    return None
            
            # Step 1: Load using idiomatic composed universal loader
            # Create universal loader by composing all available loaders
            universal_loader = load.pdf | load.pptx | load.csv | load.image
            
            try:
                att = universal_loader(source)
                # Check if loading succeeded
                if att is None or att.content is None:
                    # This means no loader was found for this file type
                    file_ext = Path(actual_path).suffix.lower()
                    if file_ext:
                        print(f"Warning: No loader available for file type '{file_ext}': {actual_path}")
                    else:
                        print(f"Warning: No file extension detected, cannot determine loader: {actual_path}")
                    return None
            except FileNotFoundError:
                print(f"Warning: File not found: {actual_path}")
                return None
            except PermissionError:
                print(f"Warning: Permission denied accessing file: {actual_path}")
                return None
            except Exception as e:
                # This could be a loader-specific error (corrupted file, etc.)
                error_msg = str(e)
                if "No such file" in error_msg or "does not exist" in error_msg.lower():
                    print(f"Warning: File not found: {actual_path}")
                elif "permission" in error_msg.lower():
                    print(f"Warning: Permission denied accessing file: {actual_path}")
                else:
                    print(f"Warning: Failed to load {actual_path}: {e}")
                return None
            
            # Step 2: Apply modifiers based on DSL commands
            # Use the clean modify.* interface
            if 'pages' in commands:
                # The pages command is embedded in the source path
                # The modify.pages function will extract it from the attachment
                att = modify.pages(att)
            
            if 'sample' in commands:
                # For sampling operations like data.csv[sample:100]
                if hasattr(modify, 'sample'):
                    sample_size = commands.get('sample', 100)
                    att = modify.sample(att, sample_size)
            
            if 'resize' in commands:
                # For image transformations like image.jpg[resize:50%]  
                if hasattr(modify, 'resize'):
                    resize_factor = commands.get('resize', '100%')
                    att = modify.resize(att, resize_factor)
                    
            return att
            
        except Exception as e:
            print(f"Warning: Unexpected error processing {source}: {e}")
            return None
    
    def _is_url(self, path: str) -> bool:
        """Check if the path is a URL."""
        return path.startswith(('http://', 'https://', 'ftp://', 'ftps://'))
    
    @property
    def text(self) -> str:
        """
        All extracted text joined with blank lines.
        """
        if self._text_cache is None:
            texts = []
            for att in self.attachments:
                try:
                    text_att = present.text(att)
                    if text_att and text_att.content.strip():
                        texts.append(text_att.content.strip())
                except:
                    pass  # Text extraction not available for this type
            self._text_cache = "\n\n".join(texts)
        return self._text_cache
    
    @property
    def images(self) -> List[str]:
        """
        Flat list of base64 PNG images.
        """
        if self._images_cache is None:
            images = []
            for att in self.attachments:
                try:
                    image_att = present.images(att)
                    if image_att and image_att.content:
                        images.extend(image_att.content)
                except:
                    pass  # Image extraction not available for this type
            self._images_cache = images
        return self._images_cache
    

    
    def __str__(self) -> str:
        """
        Pretty text view of all attachments.
        """
        if not self.attachments:
            return "Attachments(empty)"
        
        parts = []
        parts.append(f"Attachments({len(self.attachments)} files)")
        parts.append("=" * 40)
        
        for i, att in enumerate(self.attachments, 1):
            parts.append(f"\n{i}. {att.source}")
            
            # Show content summary
            try:
                text_att = present.text(att)
                if text_att:
                    text_preview = text_att.content[:100].replace('\n', ' ')
                    if len(text_att.content) > 100:
                        text_preview += "..."
                    parts.append(f"   Text: {text_preview}")
            except:
                pass
            
            try:
                image_att = present.images(att)
                if image_att:
                    parts.append(f"   Images: {len(image_att.content)} generated")
            except:
                pass
        
        # Summary
        total_text = len(self.text)
        total_images = len(self.images)
        parts.append(f"\nSummary: {total_text} chars text, {total_images} images")
        
        return "\n".join(parts)
    
    def __len__(self) -> int:
        """Number of successfully loaded attachments."""
        return len(self.attachments)
    
    def __getitem__(self, index: int):
        """Get a specific attachment by index."""
        return self.attachments[index]


# Register adapter methods automatically
_register_adapter_methods_on_attachments()

# Convenience exports
__all__ = ['Attachments'] 