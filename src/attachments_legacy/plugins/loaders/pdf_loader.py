from __future__ import annotations
from attachments.plugin_api import register_plugin, requires
from attachments.core import Loader
from attachments.testing import PluginContract

@register_plugin("loader", priority=100)
@requires("pypdf")
class PyPDFLoader(Loader, PluginContract):
    _sample_path = "pdf"

    @classmethod
    def match(cls, path: str) -> bool:
        return path.lower().endswith(".pdf")

    def load(self, path: str):
        from pypdf import PdfReader    # type: ignore
        return PdfReader(path)                 # returns PdfReader obj
