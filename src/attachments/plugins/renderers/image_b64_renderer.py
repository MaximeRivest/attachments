import base64, io
from attachments.plugin_api import register_plugin, requires
from attachments.core import Renderer
from attachments.testing import PluginContract

@register_plugin("renderer_image", priority=100)
@requires("PIL", pip_names={"PIL": "Pillow"})
class ImageB64Renderer(Renderer, PluginContract):
    content_type = 'image'

    try:
        from PIL import Image
        _sample_obj = Image.new("RGB", (10, 10))
    except ImportError:
        _sample_obj = None

    def match(self, obj):
        try:
            from PIL import Image  # type: ignore import-not-found
            return isinstance(obj, Image.Image)
        except ImportError:
            # When PIL is not available, we can't match Image objects
            # Also need to handle strings that might be error messages from ImageLoader
            return False

    def render(self, obj, meta):
        try:
            from PIL import Image  # to ensure same namespace; lint ignore
            buf = io.BytesIO()
            obj.save(buf, format='PNG')
            return [f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"]
        except ImportError:
            # This should not be reached if match returns False when PIL is not available
            return ["data:image/png;base64,"]  # Return an empty base64 image

__all__ = ["ImageB64Renderer"]
