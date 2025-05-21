import base64, io
from attachmentsv2.plugin_api import register_plugin, requires
from attachmentsv2.core import Renderer

@register_plugin("renderer_image", priority=100)
@requires("PIL")
class ImageB64Renderer(Renderer):
    content_type = 'image'

    def match(self, obj):
        from PIL import Image  # type: ignore import-not-found
        return isinstance(obj, Image.Image)

    def render(self, obj, meta):
        from PIL import Image  # to ensure same namespace; lint ignore
        buf = io.BytesIO()
        obj.save(buf, format='PNG')
        return [f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"]
