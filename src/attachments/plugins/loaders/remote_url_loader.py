from attachments.plugin_api import register_plugin
from attachments.core import Loader
from attachments.testing import PluginContract
from urllib.parse import urlparse

@register_plugin("loader", priority=1000)
class RemoteURLLoader(Loader, PluginContract):
    """
    Match http(s) URLs where the path has *no* usual file extension.
    Returns the URL string unchanged - the renderer will do the work.
    """
    _sample_path = "https"          # self-test skips network

    @classmethod
    def match(cls, path: str) -> bool:
        if not path.startswith(("http://", "https://")):
            return False
        ext = urlparse(path).path.lower().rsplit(".", 1)[-1]
        return ext not in {
            "pdf", "png", "jpg", "jpeg", "gif", "bmp", "webp",
            "csv", "docx", "pptx", "xlsx", "txt"
        }

    def load(self, path: str):
        return path     # keep it simple – just pass the URL forward
