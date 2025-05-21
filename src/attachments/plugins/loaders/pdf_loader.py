# plugins/loaders/pdf_loader.py
from attachments.plugin_api import register_plugin, requires
from attachments.core import Loader
from attachments.testing import PluginContract

@register_plugin("loader", priority=100)
@requires("fitz")
class PDFLoader(Loader, PluginContract):
    _sample_path = "tests/test_data/sample.pdf"

    def match(self, path):
        return path.lower().endswith(".pdf")

    def load(self, path):
        import fitz  # type: ignore import-not-found
        return fitz.open(path)

__all__ = ["PDFLoader"]
