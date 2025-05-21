# csv_brief_text_renderer.py
import pandas as pd
import io
from attachmentsv2.plugin_api import register_plugin
from attachmentsv2.core import Renderer

# No external dependencies that need gating here (pandas is common)

@register_plugin("renderer_text", priority=120)
class CSVBrief(Renderer):
    content_type = 'text'

    def match(self, obj):
        return isinstance(obj, pd.DataFrame)

    def render(self, obj, meta):
        buf = io.StringIO()
        obj.info(buf)
        info = buf.getvalue()
        head = obj.head(5).to_markdown()
        return f"### CSV SUMMARY\n\n{info}\n\n{head}"
