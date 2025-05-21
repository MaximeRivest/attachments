# csv_full_text_renderer.py
import pandas as pd
from attachments.plugin_api import register_plugin
from attachments.core import Renderer
from attachments.testing import PluginContract

# No external dependencies that need gating here (pandas is common)

@register_plugin("renderer_text", priority=80)
class CSVFull(Renderer, PluginContract):
    content_type = 'text'
    _sample_obj = pd.DataFrame({"a": [1,2], "b": [3,4]})

    def match(self, obj):
        return isinstance(obj, pd.DataFrame)

    def render(self, obj, meta):
        return obj.to_markdown()

__all__ = ["CSVFull"]
