from attachmentsv2.plugin_api import register_plugin, requires
from attachmentsv2.core import Transform

@register_plugin("transform", priority=100)
@requires("PIL")
class Rotate(Transform):
    name = 'rotate'  # token in DSL

    def apply(self, obj, args):
        deg = int(args or 0)
        from PIL import Image  # type: ignore import-not-found
        if isinstance(obj, Image.Image):
            return obj.rotate(deg, expand=True)
        return obj
