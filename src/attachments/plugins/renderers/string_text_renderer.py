from attachments.plugin_api import register_plugin
from attachments.core import Renderer
from attachments.testing import PluginContract

@register_plugin("renderer_text", priority=10) # Low-ish priority, but should handle bare strings
class StringTextRenderer(Renderer, PluginContract):
    content_type = "text"
    _sample_obj = "This is a sample string."

    def match(self, obj: any) -> bool:
        return isinstance(obj, str)

    def render(self, obj: str, meta: dict) -> str:
        return obj

__all__ = ["StringTextRenderer"] 