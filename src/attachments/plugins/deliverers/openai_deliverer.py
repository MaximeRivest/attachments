from attachments.plugin_api import register_plugin
from attachments.core import Deliverer
from attachments.testing import PluginContract

# No external dependencies, so PLUGIN_REQUIRES is not needed.

@register_plugin("deliverer", priority=100)
class OpenAIDeliverer(Deliverer, PluginContract):
    name = "openai"

    def package(self, text, images, audio, prompt=""):
        # Match the output structure of Attachments.to_openai_content
        # See: src/attachments_legacy/core.py:711
        content = []
        if images:
            for image_data_uri in images:
                content.append({"type": "input_image", "image_url": image_data_uri})
        # Always append the text block last, as in to_openai_content
        if prompt or text:
            # The prompt comes first, then the text (if any), separated by two newlines
            combined_text = (prompt or "") + ("\n\n" + text if text else "")
            content.append({"type": "input_text", "text": combined_text})
        return content

__all__ = ["OpenAIDeliverer"]
