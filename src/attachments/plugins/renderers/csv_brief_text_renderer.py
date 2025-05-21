# csv_brief_text_renderer.py
import pandas as pd
import io
from attachments.plugin_api import register_plugin
from attachments.core import Renderer
from attachments.testing import PluginContract

# No external dependencies that need gating here (pandas is common)

@register_plugin("renderer_text", priority=120)
class CSVBrief(Renderer, PluginContract):
    content_type = 'text'
    _sample_obj = pd.DataFrame({"a": [1,2], "b": [3,4]})

    def match(self, obj):
        return isinstance(obj, pd.DataFrame)

    def render(self, obj, meta):
        buf = io.StringIO()
        obj.info(buf)
        info = buf.getvalue()
        head = obj.head(5).to_markdown()
        return f"### CSV SUMMARY\n\n{info}\n\n{head}"

__all__ = ["CSVBrief"]
