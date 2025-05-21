import base64, io
from attachments.plugin_api import register_plugin, requires
from attachments.core import Renderer
from attachments.testing import PluginContract

@register_plugin("renderer_image", priority=100)
@requires("PIL")
class ImageB64Renderer(Renderer, PluginContract):
    content_type = 'image'

    try:
        from PIL import Image
        _sample_obj = Image.new("RGB", (10, 10))
    except ImportError:
        _sample_obj = None

    def match(self, obj):
        from PIL import Image  # type: ignore import-not-found
        return isinstance(obj, Image.Image)

    def render(self, obj, meta):
        from PIL import Image  # to ensure same namespace; lint ignore
        buf = io.BytesIO()
        obj.save(buf, format='PNG')
        return [f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"]

__all__ = ["ImageB64Renderer"]
