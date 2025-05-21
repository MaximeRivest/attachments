from attachments.plugin_api import register_plugin, requires
from attachments.core import Loader
from attachments.testing import PluginContract

@register_plugin("loader", priority=100)
@requires("PIL", pip_names={"PIL": "Pillow"})
class ImageLoader(Loader, PluginContract):
    _sample_path = "jpg"

    @classmethod
    def match(cls, path):
        return path.lower().endswith((
            '.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'
        ))

    def load(self, path):
        try:
            from PIL import Image  # type: ignore import-not-found
            return Image.open(path)
        except ImportError:
            # When PIL is not available, return a placeholder or error message
            # This allows tests like test_rotate_transform_no_pillow to work
            return f"[ImageLoader: PIL/Pillow not available to load '{path}']"

__all__ = ["ImageLoader"]
