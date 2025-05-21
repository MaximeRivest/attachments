from attachmentsv2.plugin_api import register_plugin, requires
from attachmentsv2.core import Loader

@register_plugin("loader", priority=100)
@requires("PIL")
class ImageLoader(Loader):
    def match(self, path):
        return path.lower().endswith((
            '.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'
        ))

    def load(self, path):
        from PIL import Image  # type: ignore import-not-found
        return Image.open(path)
