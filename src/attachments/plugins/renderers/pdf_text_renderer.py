from __future__ import annotations
from attachments.plugin_api import register_plugin, requires
from attachments.core import Renderer
from attachments.testing import PluginContract

@register_plugin("renderer_text", priority=180)
@requires("pypdf")
class PyPDFText(Renderer, PluginContract):
    content_type = "text"

    try:
        from pypdf import PdfReader # type: ignore
        _sample_obj = PdfReader.__new__(PdfReader)   # dummy
    except Exception:
        _sample_obj = None

    def match(self, obj):
        from pypdf import PdfReader # type: ignore
        return isinstance(obj, PdfReader)

    def render(self, reader, meta):
        out = []
        for i, page in enumerate(reader.pages, 1):
            txt = page.extract_text() or ""
            out.append(f"--- page {i} ---\n{txt.strip()}")
        return "\n\n".join(out) or "[no extractable text]"
