"""
Transform: keep only a subset of pages in a fitz.Document.

Usage examples
--------------
Attachment("report.pdf[pages:1,3-5,-1]")
Attachment("slides.pdf[:3,N]")                     # handled by DSL → pages token
"""
from __future__ import annotations
from attachments.plugin_api import register_plugin, requires
from attachments.core import Transform
from attachments.testing import PluginContract

@register_plugin("transform", priority=200)
@requires("fitz", pip_names={"fitz": "PyMuPDF"})
class PDFPageSelector(Transform, PluginContract):
    name = "pages"

    # dummy object for self-test
    try:
        import fitz
        _sample_obj = fitz.open()
    except ImportError:
        _sample_obj = None

    # ---------------------------------------
    def apply(self, doc, arg):
        import fitz
        if not isinstance(doc, fitz.Document) or not arg:
            return doc      # nothing to do

        total = doc.page_count
        wanted: list[int] = []

        # Accept “:3” (first 3 pages) and “N” (last page) like the README
        arg = arg.replace(" ", "")
        specs = arg.split(",")
        for spec in specs:
            if spec == "":            # ignore stray commas
                continue
            if spec.startswith(":"):  # leading range  :3  == 0-2
                end = int(spec[1:]) if spec[1:] else total
                wanted.extend(range(0, min(end, total)))
                continue
            if spec.upper() == "N" or spec == "-1":
                wanted.append(total - 1)
                continue
            if "-" in spec:           # 3-5
                start, end = spec.split("-")
                start_i = int(start) - 1
                end_i   = int(end) - 1
                wanted.extend(range(start_i, min(end_i + 1, total)))
                continue
            # single page “4”
            wanted.append(int(spec) - 1)

        wanted = sorted(set(i for i in wanted if 0 <= i < total))
        if not wanted:
            return doc        # avoid producing an empty document

        new_doc = fitz.open()
        for i in wanted:
            new_doc.insert_pdf(doc, from_page=i, to_page=i)
        return new_doc
