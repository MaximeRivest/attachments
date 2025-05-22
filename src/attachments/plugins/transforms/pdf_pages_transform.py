"""
Transform: keep only a subset of pages in a pypdf.PdfReader object.

Usage examples
--------------
Attachment("report.pdf[pages:1,3-5,-1]")
Attachment("slides.pdf[:3,N]")                     # handled by DSL → pages token
"""
from __future__ import annotations
import io
from attachments.plugin_api import register_plugin, requires
from attachments.core import Transform
from attachments.testing import PluginContract

@register_plugin("transform", priority=200)
@requires("pypdf")
class PDFPageSelector(Transform, PluginContract):
    name = "pages"

    # dummy object for self-test
    try:
        from pypdf import PdfReader # type: ignore
        # Use a blank PdfReader instance for the sample object
        _sample_obj = PdfReader.__new__(PdfReader)
    except ImportError:
        _sample_obj = None

    # ---------------------------------------
    def apply(self, doc, arg):
        from pypdf import PdfReader, PdfWriter # type: ignore

        if not isinstance(doc, PdfReader) or not arg:
            return doc      # nothing to do

        total = len(doc.pages)
        wanted: list[int] = []

        # Accept ":3" (first 3 pages) and "N" (last page) like the README
        arg = arg.replace(" ", "")
        specs = arg.split(",")
        for spec in specs:
            if spec == "":            # ignore stray commas
                continue
            if spec.startswith(":"):  # leading range  :3  == 0-2
                # For pypdf, pages are 0-indexed. ":3" means pages 0, 1, 2 (first 3 pages)
                # User input is 1-indexed for end, e.g. ":3" means up to and including page 3.
                # If spec[1:] is empty, it means all pages from the start.
                end_user_indexed = int(spec[1:]) if spec[1:] else total
                # Convert to 0-indexed end for range, exclusive: range(0, end_0_indexed)
                end_0_indexed = min(end_user_indexed, total)
                wanted.extend(range(0, end_0_indexed))
                continue
            if spec.upper() == "N" or spec == "-1": # Last page
                if total > 0:
                    wanted.append(total - 1)
                continue
            if "-" in spec:           # Range e.g., "3-5" (pages 3, 4, 5)
                start_str, end_str = spec.split("-")
                # User input is 1-indexed. Convert to 0-indexed.
                start_0_indexed = int(start_str) - 1
                end_0_indexed = int(end_str) -1 # end_0_indexed is inclusive here
                # Ensure valid range and within bounds
                if 0 <= start_0_indexed < total and start_0_indexed <= end_0_indexed:
                     wanted.extend(range(start_0_indexed, min(end_0_indexed + 1, total)))
                continue
            # single page "4" (page 4, which is index 3)
            page_0_indexed = int(spec) - 1
            if 0 <= page_0_indexed < total:
                wanted.append(page_0_indexed)

        # Remove duplicates and sort, ensure all are valid 0-indexed pages
        wanted = sorted(list(set(i for i in wanted if 0 <= i < total)))

        if not wanted or len(wanted) == total: # If no pages selected, or all pages selected, return original
            return doc        # avoid producing an empty document or identical document

        writer = PdfWriter()
        for page_index in wanted:
            writer.add_page(doc.pages[page_index])

        # Write to an in-memory stream and return a new PdfReader
        output_stream = io.BytesIO()
        writer.write(output_stream)
        output_stream.seek(0) # Rewind the stream to the beginning
        return PdfReader(output_stream)
