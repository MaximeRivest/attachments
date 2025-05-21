from attachments.plugin_api import register_plugin, requires
from attachments.core import Transform
from attachments.testing import PluginContract

@register_plugin("transform", priority=100)
@requires("PIL")
class Rotate(Transform, PluginContract):
    name = 'rotate'  # token in DSL

    try:
        from PIL import Image
        _sample_obj = Image.new("RGB", (10, 10))
    except ImportError:
        _sample_obj = None

    def apply(self, obj, args):
        deg = int(args or 0)
        try:
            from PIL import Image  # type: ignore import-not-found
        except ImportError:
            return obj
        if isinstance(obj, Image.Image):
            return obj.rotate(deg, expand=True)
        return obj

__all__ = ["Rotate"]
