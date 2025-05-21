from attachmentsv2.plugin_api import register_plugin, requires
from attachmentsv2.core import Renderer

@register_plugin("renderer_text", priority=50)
@requires("pytesseract", "PIL")
class ImageOCRText(Renderer):
    content_type = "text"

    def match(self, obj):
        from PIL import Image  # Local import to avoid hard dependency at import time
        return isinstance(obj, Image.Image)

    def render(self, obj, meta):
        import pytesseract  # type: ignore import-not-found  # Local import after dependency check
        return pytesseract.image_to_string(obj)
