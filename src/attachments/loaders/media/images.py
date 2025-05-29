"""Image loaders using PIL/Pillow."""

from ...core import Attachment, loader
from ... import matchers


@loader(match=matchers.image_match)
def image_to_pil(att: Attachment) -> Attachment:
    """Load image using PIL with automatic input source handling."""
    try:
        # Use the new input_source property - no more repetitive patterns!
        image_source = att.input_source
        
        # Try to import pillow-heif for HEIC support if needed
        if (isinstance(image_source, str) and image_source.lower().endswith(('.heic', '.heif'))) or \
           ('image/heic' in att.content_type or 'image/heif' in att.content_type):
            try:
                from pillow_heif import register_heif_opener
                register_heif_opener()
            except ImportError:
                pass  # Fall back to PIL's built-in support if available
        
        from PIL import Image
        
        # Load the image from the appropriate source
        if isinstance(image_source, str):
            # File path
            att._obj = Image.open(image_source)
        else:
            # BytesIO or file-like object
            image_source.seek(0)
            att._obj = Image.open(image_source)
        
        # Store metadata
        if att._obj:
            att.metadata.update({
                'format': getattr(att._obj, 'format', 'Unknown'),
                'size': getattr(att._obj, 'size', (0, 0)),
                'mode': getattr(att._obj, 'mode', 'Unknown')
            })
        
    except ImportError:
        raise ImportError("Pillow is required for image loading. Install with: pip install Pillow")
    return att 