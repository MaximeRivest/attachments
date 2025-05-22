"""Image file loader using PIL."""

from PIL import Image
from ..core.decorators import loader


def is_image(path: str) -> bool:
    return any(path.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'])


@loader(is_image)
def image(path: str):
    return Image.open(path) 