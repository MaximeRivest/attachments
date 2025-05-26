"""Image loaders using PIL/Pillow."""

from ...core import Attachment, loader
from ... import matchers


@loader(match=matchers.image_match)
def image_to_pil(att: Attachment) -> Attachment:
    """Load image using PIL."""
    try:
        # Try to import pillow-heif for HEIC support if needed
        if att.path.lower().endswith(('.heic', '.heif')):
            try:
                from pillow_heif import register_heif_opener
                register_heif_opener()
            except ImportError:
                pass  # Fall back to PIL's built-in support if available
        
        from PIL import Image
        att._obj = Image.open(att.path)
        
        # Store metadata
        att.metadata.update({
            'format': getattr(att._obj, 'format', 'Unknown'),
            'size': getattr(att._obj, 'size', (0, 0)),
            'mode': getattr(att._obj, 'mode', 'Unknown')
        })
        
    except ImportError:
        if att.path.lower().endswith(('.heic', '.heif')):
            raise ImportError("pillow-heif is required for HEIC loading. Install with: pip install pillow-heif")
        else:
            raise ImportError("Pillow is required for image loading. Install with: pip install Pillow")
    return att 