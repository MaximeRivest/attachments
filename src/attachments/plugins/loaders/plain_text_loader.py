from attachments.plugin_api import register_plugin
from attachments.core import Loader
from attachments.testing import PluginContract
import os

@register_plugin("loader", priority=1) # Very low priority to act as a fallback
class PlainTextLoader(Loader, PluginContract):
    _sample_path = "txt" # For its own selftest via PluginContract

    @classmethod
    def match(cls, path: str) -> bool:
        # As a low-priority fallback, if this loader is considered,
        # it means no higher-priority loader matched.
        # We can make it match any file that wasn't caught by others.
        # For simplicity and to ensure it's a true fallback, always return True.
        # The registry's priority system will ensure it's tried last.
        return True

    def load(self, path: str) -> str:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        except FileNotFoundError:
            # This should ideally be caught before calling load, but as a safeguard:
            return f"[PlainTextLoader: File not found at '{path}']"
        except Exception as e:
            # For a fallback, returning an error message within the content
            # might be more robust than raising an exception that stops processing.
            return f"[PlainTextLoader: Failed to read '{os.path.basename(path)}' as text: {e}]"

__all__ = ["PlainTextLoader"] 