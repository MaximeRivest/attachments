from attachments.plugin_api import register_plugin
from attachments.core import Deliverer
from attachments.testing import PluginContract

# No external dependencies, so PLUGIN_REQUIRES is not needed.

@register_plugin("deliverer", priority=100)
class ClaudeDeliverer(Deliverer, PluginContract):
    name = "claude"

    def package(self, text, images, audio, prompt=""):
        parts = []
        if text or prompt:
            parts.append({"type": "text", "text": f"{prompt}\n\n{text or ''}".strip()})
        if images:
            parts.extend({"type": "image", "source": img} for img in images)
        # Anthropic doesn't yet have direct audio ingest; skip for now
        return parts

__all__ = ["ClaudeDeliverer"]