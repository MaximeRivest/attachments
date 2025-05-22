from __future__ import annotations
import math, io, base64
from attachments.plugin_api import register_plugin, requires
from attachments.core import Transform
from attachments.testing import PluginContract

@register_plugin("transform", priority=50)
@requires("PIL", pip_names={"PIL": "Pillow"})
class TileTransform(Transform, PluginContract):
    """
    `Attachments(..., "x.jpg", "https://…[tile:true]")`
    or chain on any Attachment object ending with [tile:true].
    """
    name = "tile"

    # sample object: list of data-URI images
    _sample_obj = [
        "data:image/png;base64,iVBORw0KGgoAAA...",
        "data:image/png;base64,iVBORw0KGgoAAA..."
    ]

    def apply(self, obj, arg):
        from PIL import Image
        if not isinstance(obj, list) or not all(isinstance(x, str) for x in obj):
            return obj
        images = [Image.open(io.BytesIO(base64.b64decode(s.split(",")[1])))
                  for s in obj]
        n      = len(images)
        if n == 0:
            return obj
        grid   = math.ceil(math.sqrt(n))
        w, h   = images[0].size
        canvas = Image.new("RGB", (w * grid, h * grid), "white")
        for idx, im in enumerate(images):
            r, c = divmod(idx, grid)
            canvas.paste(im, (c * w, r * h))
        buf = io.BytesIO()
        canvas.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        return [f"data:image/png;base64,{b64}"]       # single tiled image
