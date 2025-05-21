from attachments.plugin_api import register_plugin, requires
from attachments.core import Loader
from attachments.testing import PluginContract

@register_plugin("loader", priority=100)
@requires("PIL")
class ImageLoader(Loader, PluginContract):
    _sample_path = "jpg"

    def match(self, path):
        return path.lower().endswith((
            '.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'
        ))

    def load(self, path):
        from PIL import Image  # type: ignore import-not-found
        return Image.open(path)

__all__ = ["ImageLoader"]
