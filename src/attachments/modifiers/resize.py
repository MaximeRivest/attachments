"""Image resizing modifier."""

from PIL import Image as PILImage
from ..core.decorators import modifier


@modifier
def resize(img: PILImage.Image, size: str) -> PILImage.Image:
    """Resize image."""
    if 'x' in size:
        w, h = map(int, size.split('x'))
        return img.resize((w, h))
    elif size.endswith('%'):
        scale = int(size[:-1]) / 100
        return img.resize((int(img.width * scale), int(img.height * scale)))
    else:
        # Return original image if size format not recognized
        return img 