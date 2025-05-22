from __future__ import annotations
import pathlib, tempfile, mimetypes, shutil, contextlib
import requests                 # optional dep
from attachments.plugin_api import register_plugin, requires
from attachments.core import Loader, Attachment
from attachments.testing import PluginContract
from attachments.utils import is_url
from attachments.registry import REGISTRY

@register_plugin("loader", priority=999)      # run **before** PlainTextLoader
@requires("requests")
class RemoteFileLoader(Loader, PluginContract):
    """
    Fetch any http(s) URL to a temporary file, then delegate
    to the *real* loader chosen by the registry.
    """
    _sample_path = "https"

    # --- class helpers ------------------------------------------
    @classmethod
    def match(cls, path: str) -> bool:
        return path.startswith(("http://", "https://"))

    # --- main logic ---------------------------------------------
    def load(self, url: str):
        headers = {
            "User-Agent": "attachments-library/0.3 (https://github.com/maximecb/attachments)"
        }
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()

        # Heuristic: keep original filename if present, else use MIME.
        filename = pathlib.Path(url.split("?")[0]).name
        if not filename or "." not in filename:
            ext = mimetypes.guess_extension(resp.headers.get("content-type", ""))
            filename = f"remote{ext or '.bin'}"

        tmp = tempfile.NamedTemporaryFile(
            prefix="attachments_", suffix=filename, delete=False
        )
        with contextlib.closing(tmp) as tf:
            tf.write(resp.content)
            tmp_path = tf.name

        # Now pick the *real* loader (skip our own class to avoid recursion).
        real_loader = next(
            L for L in REGISTRY.all("loader")
            if L is not RemoteFileLoader and L.match(tmp_path)
        )
        return real_loader().load(tmp_path)
