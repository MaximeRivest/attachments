# csv_full_text_renderer.py
import pandas as pd
from attachmentsv2.plugin_api import register_plugin
from attachmentsv2.core import Renderer

# No external dependencies that need gating here (pandas is common)

@register_plugin("renderer_text", priority=80)
class CSVFull(Renderer):
    content_type = 'text'

    def match(self, obj):
        return isinstance(obj, pd.DataFrame)

    def render(self, obj, meta):
        return obj.to_markdown()
