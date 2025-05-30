"""Media loaders - images, audio, video, vector graphics, etc."""

from .images import image_to_pil
from .archives import zip_to_images
from .vector_graphics import svg_to_svgdocument, eps_to_epsdocument

__all__ = [
    'image_to_pil',
    'zip_to_images',
    'svg_to_svgdocument',
    'eps_to_epsdocument'
] 