# plugins/loaders/pdf_loader.py
from attachmentsv2.plugin_api import register_plugin, requires
from attachmentsv2.core import Loader

@register_plugin("loader", priority=100)
@requires("fitz")
class PDFLoader(Loader):
    def match(self, path):
        return path.lower().endswith(".pdf")

    def load(self, path):
        import fitz  # type: ignore import-not-found
        return fitz.open(path)
