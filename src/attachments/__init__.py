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
        """Process a single source using the new modular backend."""
        
        # Parse DSL commands from source
        actual_path, commands = parse_path_expression(source)
        
        # Determine file type and load appropriately
        if actual_path.lower().endswith('.pdf'):
            att = load.pdf(source)
        elif actual_path.lower().endswith('.csv'):
            att = load.csv(source)
        elif any(actual_path.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']):
            att = load.image(source)
        else:
            # Try PDF loader as fallback
            try:
                att = load.pdf(source)
            except:
                print(f"Warning: No loader found for {source}")
                return None
        
        # Apply modifiers based on commands
        if 'pages' in commands and hasattr(modify, 'pages'):
            # The pages modifier will automatically use the command from the attachment
            att = modify.pages(att)
        
        if 'summary' in commands and commands['summary'].lower() == 'true':
            # Apply summary modifier if available
            if hasattr(modify, 'sample'):
                att = modify.sample(att, 100)  # Sample for summary
        
        if 'rotate' in commands and hasattr(modify, 'resize'):
            # Note: We'd need a rotate modifier, using resize as placeholder
            pass
            
        return att
    
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
    
    def to_openai(self, prompt: str = "") -> List[Dict[str, Any]]:
        """
        Convert to OpenAI API message format.
        
        Args:
            prompt: User prompt to include
            
        Returns:
            List of message dictionaries ready for OpenAI API
        """
        if not self.attachments:
            return [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
        
        # Combine all attachments into one comprehensive content list
        all_content = []
        
        if prompt:
            all_content.append({"type": "text", "text": prompt})
        
        # Add text from all attachments
        text_content = self.text
        if text_content:
            all_content.append({"type": "text", "text": text_content})
        
        # Add images from all attachments
        for image_data_url in self.images:
            all_content.append({
                "type": "image_url",
                "image_url": {"url": image_data_url}
            })
        
        return [{"role": "user", "content": all_content}]
    
    def to_claude(self, prompt: str = "") -> List[Dict[str, Any]]:
        """
        Convert to Claude/Anthropic API message format.
        
        Args:
            prompt: User prompt to include
            
        Returns:
            List of message dictionaries ready for Claude API
        """
        content = []
        
        if prompt:
            content.append({"type": "text", "text": prompt})
        
        # Add text content
        text_content = self.text
        if text_content:
            content.append({"type": "text", "text": text_content})
        
        # Add images (Claude uses base64 format)
        for image_data_url in self.images:
            # Extract base64 data from data URL
            if image_data_url.startswith("data:image/"):
                base64_data = image_data_url.split(",", 1)[1]
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": base64_data
                    }
                })
        
        return [{"role": "user", "content": content}]
    
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
        class AttachmentWrapper:
            """Wrapper to provide individual attachment interface."""
            def __init__(self, att):
                self._att = att
            
            @property
            def text(self):
                try:
                    text_att = present.text(self._att)
                    return text_att.content if text_att else ""
                except:
                    return ""
            
            @property
            def images(self):
                try:
                    image_att = present.images(self._att)
                    return image_att.content if image_att else []
                except:
                    return []
            
            def to_openai_content(self, prompt=""):
                """Individual attachment to OpenAI format."""
                return adapt.openai(self._att, prompt)
        
        return AttachmentWrapper(self.attachments[index])


# Convenience exports
__all__ = ['Attachments'] 