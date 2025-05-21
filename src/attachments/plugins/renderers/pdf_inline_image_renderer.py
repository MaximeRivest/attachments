from __future__ import annotations
import base64, io
from attachments.plugin_api import register_plugin, requires
from attachments.core import Renderer
from attachments.testing import PluginContract

@register_plugin("renderer_image", priority=140)
@requires("pypdf", "PIL", pip_names={"PIL": "Pillow"})
class PyPDFInlineImages(Renderer, PluginContract):
    content_type = "image"

    try:
        from pypdf import PdfReader # type: ignore
        _sample_obj = PdfReader.__new__(PdfReader)
    except Exception:
        _sample_obj = None

    def match(self, obj):
        from pypdf import PdfReader # type: ignore
        return isinstance(obj, PdfReader)

    def render(self, reader, meta):
        from PIL import Image
        out = []
        for pno, page in enumerate(reader.pages, 1):
            for ino, img in enumerate(page.images, 1):
                data = img.data
                mode = "RGB" if img.color_space != "/DeviceCMYK" else "CMYK"
                im = Image.open(io.BytesIO(data)).convert("RGB" if mode != "CMYK" else "CMYK")
                buf = io.BytesIO()
                im.save(buf, format="PNG")
                b64 = base64.b64encode(buf.getvalue()).decode()
                out.append(f"data:image/png;page={pno};img={ino};base64,{b64}")
        return out or None
