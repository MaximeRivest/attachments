from attachments.plugin_api import register_plugin
from attachments.core import Deliverer
from attachments.testing import PluginContract

# No external dependencies, so PLUGIN_REQUIRES is not needed.

@register_plugin("deliverer", priority=100)
class OpenAIDeliverer(Deliverer, PluginContract):
    name = "openai"

    def package(self, text, images, audio, prompt=""):
        blocks = []
        if prompt or text:
            blocks.append({"type": "input_text", "text": f"{prompt}\n\n{text or ''}".strip()})
        if images:
            for img in images:
                blocks.append({"type": "input_image", "image_url": img})
        if audio:
            for a in audio:
                blocks.append({"type": "input_audio", "audio_url": a})
        return blocks

__all__ = ["OpenAIDeliverer"]
