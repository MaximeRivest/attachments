import inspect, base64
import pytest
from attachments.core import Loader, Renderer, Transform, Deliverer

class PluginContract:
    """Mixin providing a default `selftest()` for any plugin."""
    def selftest(self, tmp_path):
        if getattr(self, "_attachments_disabled", False):
            pytest.skip("Plugin dependencies not met; skipping selftest.") # type: ignore
        # Loader contract: must have match() and load()
        if hasattr(self, "match") and hasattr(self, "load"):
            sample = getattr(self, "_sample_path", None)
            if sample:
                assert self.match(sample)
                obj = self.load(sample)
                assert obj is not None
        # Transform contract: must have apply()
        if hasattr(self, "apply"):
            dummy = getattr(self, "_sample_obj", None)
            if dummy is not None:
                out = self.apply(dummy, None)
                assert out is not None
        # Renderer contract: must have render() and content_type
        if hasattr(self, "render") and hasattr(self, "content_type"):
            dummy = getattr(self, "_sample_obj", None)
            # Only call match if dummy is not a path (i.e. is an object)
            if dummy is not None:
                # Some renderers expect objects, not paths
                try:
                    match_result = self.match(dummy)
                except Exception:
                    match_result = False
                if match_result:
                    res = self.render(dummy, {})
                    if self.content_type == "text":
                        assert isinstance(res, str) and res
                    else:
                        assert isinstance(res, list) and res and all(
                            isinstance(x, str) for x in res
                        )
        # Deliverer contract: must have package()
        if hasattr(self, "package"):
            # Try with text only
            pkt = self.package("txt", None, None)
            assert pkt  # non-empty structure
            # Try with images only
            pkt2 = self.package(None, ["im"], None)
            assert pkt2
            # Try with audio only
            pkt3 = self.package(None, None, ["aud"])
            assert pkt3 