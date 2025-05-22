'''
renderer_image: Render PDF pages to PNG images using pypdfium2.
This is generally faster and more lightweight than browser-based rendering.
'''
from __future__ import annotations

import base64
import io

from attachments.core import Renderer
from attachments.plugin_api import register_plugin, requires
from attachments.testing import PluginContract

try:
    import pypdfium2 as pdfium # type: ignore
except ImportError:
    pdfium = None

try:
    from pypdf import PdfReader # type: ignore
except ImportError:
    PdfReader = None # type: ignore


@register_plugin("renderer_image", priority=150)
@requires("pypdf", "pypdfium2")
class PdfiumSnapshotRenderer(Renderer, PluginContract):
    '''
    Returns one PNG per page (cap via `meta["max_pages"]`, default 10).
    Uses pypdfium2 for rendering.
    '''
    content_type = "image"

    # For PluginContract / testing
    try:
        from pypdf import PdfReader  # type: ignore
        # A *blank* PdfReader instance created without parsing bytes;
        # good enough for `isinstance()` checks, but carries no stream.
        _sample_obj = PdfReader.__new__(PdfReader)
    except Exception:
        _sample_obj = None # type: ignore

    # ---------- match -------------------------------------------------
    def match(self, obj):
        """
        Require a *real* PdfReader (one that has .stream) so that unit
        tests using the stub object above short-circuit and do **not**
        enter the heavy render code path.
        """
        if not PdfReader: # pypdf not installed
            return False
        return isinstance(obj, PdfReader) and getattr(obj, "stream", None)

    # ---------- render ------------------------------------------------
    def render(self, reader: PdfReader, meta: dict | None) -> list[str] | None:
        if not pdfium:
            return None 

        verbose = meta.get("verbose", False) if meta else False
        max_pages = int(meta.get("max_pages", 10)) if meta else 10
        out_images = []
        pdf_bytes = b'' 

        try:
            if hasattr(reader, 'stream') and reader.stream:
                try:
                    original_pos = reader.stream.tell()
                    reader.stream.seek(0)
                    pdf_bytes = reader.stream.read()
                    reader.stream.seek(original_pos)
                except (AttributeError, io.UnsupportedOperation) as e:
                    if verbose:
                        print(f"[PdfiumSnapshotRenderer] Error reading stream: {e}")
                    return None
            else:
                if verbose:
                    print("[PdfiumSnapshotRenderer] Critical: reader.stream not available or is None.")
                return None

            if not pdf_bytes:
                if verbose:
                    print("[PdfiumSnapshotRenderer] PDF bytes are empty after attempting to read stream.")
                return None

            pdf_doc = pdfium.PdfDocument(pdf_bytes)
            num_actual_pages = len(pdf_doc)
            
            if verbose:
                print(f"[PdfiumSnapshotRenderer] PDF has {num_actual_pages} pages. Max pages to render: {max_pages}.")

            for idx in range(min(num_actual_pages, max_pages)):
                if verbose:
                    print(f"[PdfiumSnapshotRenderer] Rendering page {idx + 1}")
                page = pdf_doc[idx]
                pil_image = page.render(scale=2).to_pil()
                
                img_byte_arr = io.BytesIO()
                pil_image.save(img_byte_arr, format='PNG')
                png_bytes = img_byte_arr.getvalue()
                
                b64_string = base64.b64encode(png_bytes).decode('utf-8')
                out_images.append(f"data:image/png;page={idx + 1};base64,{b64_string}")
                page.close()

            pdf_doc.close()
            if verbose:
                print(f"[PdfiumSnapshotRenderer] Successfully rendered {len(out_images)} pages.")
            return out_images

        except Exception as e:
            if verbose:
                print(f"[PdfiumSnapshotRenderer] Error during rendering: {e}")
                # import traceback
                # traceback.print_exc() # Consider if traceback should also be under verbose
            return None 