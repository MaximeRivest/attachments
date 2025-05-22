from attachments.plugin_api import register_plugin, requires
from attachments.core import Renderer
from attachments.testing import PluginContract

@register_plugin("renderer_text", priority=50)
@requires("pytesseract", "PIL", pip_names={"pytesseract": "pytesseract", "PIL": "Pillow"})
class ImageOCRText(Renderer, PluginContract):
    content_type = "text"

    try:
        from PIL import Image
        _sample_obj = Image.new("RGB", (10, 10))
    except ImportError:
        _sample_obj = None

    def match(self, obj):
        try:
            from PIL import Image  # Local import to avoid hard dependency at import time
            return isinstance(obj, Image.Image)
        except ImportError:
            # When PIL is not available, we can't match Image objects
            return False

    def render(self, obj, meta):
        try:
            import pytesseract  # type: ignore import-not-found  # Local import after dependency check
            return pytesseract.image_to_string(obj)
        except ImportError:
            # This should not be reached if match returns False when dependencies are missing
            return "[OCR not available: pytesseract or PIL missing]"

__all__ = ["ImageOCRText"]
