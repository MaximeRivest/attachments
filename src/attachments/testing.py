import inspect, base64, pathlib, tempfile
import pytest
from attachments.core import Loader, Renderer, Transform, Deliverer

# Helper to create sample files for selftest, similar to conftest.py
def _create_sample_file_for_selftest(ext: str, tmp_path: pathlib.Path):
    """Create a sample file of type 'ext' in tmp_path and return its path string."""
    if ext == "csv":
        try:
            import pandas as pd
        except ImportError:
            pytest.skip("pandas not available for creating CSV sample.") # type: ignore
        df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
        p = tmp_path / f"sample.{ext}"
        df.to_csv(p, index=False)
        return str(p)
    if ext in ("jpg", "png"): # Assuming 'jpg' implies creating a png for simplicity or a generic image
        try:
            from PIL import Image
        except ImportError:
            pytest.skip("Pillow (PIL) not available for creating image sample.") # type: ignore
        p = tmp_path / f"sample.{ext if ext == 'png' else 'png'}" # Default to png for 'jpg' for simplicity
        Image.new("RGB", (10, 10), (123, 222, 42)).save(p)
        return str(p)
    if ext == "pdf":
        try:
            import fitz
        except ImportError:
            pytest.skip("PyMuPDF (fitz) not available for creating PDF sample.") # type: ignore
        p = tmp_path / f"sample.{ext}"
        doc = fitz.open()
        doc.new_page().insert_text((72, 72), "hi")
        doc.save(p)
        return str(p)
    if ext == "wav":
        import wave, struct
        p = tmp_path / f"sample.{ext}"
        sample_rate = 16000 # Reduced for smaller file
        duration_ms = 50
        n_frames = int(sample_rate * (duration_ms / 1000.0))
        n_channels = 1
        sampwidth = 2
        data = struct.pack('<h', 0) * n_frames
        with wave.open(str(p), 'wb') as wf:
            wf.setnchannels(n_channels)
            wf.setsampwidth(sampwidth)
            wf.setframerate(sample_rate)
            wf.writeframes(data)
        return str(p)
    if ext == "txt":
        p = tmp_path / f"sample.{ext}"
        p.write_text("This is a sample text file for testing.")
        return str(p)
    if ext in ("http", "https"):
        p = tmp_path / "sample.txt"
        p.write_text("This is a sample text file for http(s) testing.")
        return str(p)

    raise ValueError(f"Unsupported extension for _create_sample_file_for_selftest: {ext}")


class PluginContract:
    """Mixin providing a default `selftest()` for any plugin."""
    def selftest(self, tmp_path):
        if getattr(self, "_attachments_disabled", False):
            pytest.skip("Plugin dependencies not met; skipping selftest.") # type: ignore
        
        # Loader contract: must have match() and load()
        # Check if it's a loader-like plugin by checking for _sample_path attribute (now an extension string)
        # and the presence of match & load methods.
        if hasattr(self, "_sample_path") and hasattr(self, "match") and hasattr(self, "load"):
            sample_ext = getattr(self, "_sample_path", None)
            if sample_ext and isinstance(sample_ext, str):
                # Create the sample file in tmp_path using the extension
                if sample_ext in ("http", "https"):
                    # For URL loaders, match against a dummy URL string, not a file path
                    actual_sample_path_or_url = f"{sample_ext}://example.com/sample.html" 
                else:
                    actual_sample_path_or_url = _create_sample_file_for_selftest(sample_ext, tmp_path)
                
                assert type(self).match(actual_sample_path_or_url) # type: ignore
                obj = self.load(actual_sample_path_or_url) # type: ignore
                assert obj is not None
            elif sample_ext:
                 # If _sample_path is not a string, it might be an object for some loaders?
                 # For now, assume it's an ext string for loaders using _sample_path.
                 pass # Or raise an error if _sample_path for a loader MUST be a string

        # Transform contract: must have apply()
        if hasattr(self, "apply"):
            dummy = getattr(self, "_sample_obj", None)
            if dummy is not None:
                out = self.apply(dummy, None) # type: ignore
                assert out is not None

        # Renderer contract: must have render() and content_type
        if hasattr(self, "render") and hasattr(self, "content_type"):
            dummy = getattr(self, "_sample_obj", None)
            # Only call match if dummy is not a path (i.e. is an object)
            if dummy is not None:
                # Some renderers expect objects, not paths
                match_result = False # Default to False
                try:
                    match_result = self.match(dummy) # type: ignore
                except Exception:
                    pass # Keep match_result as False
                if match_result:
                    res = self.render(dummy, {}) # type: ignore
                    if self.content_type == "text": # type: ignore
                        assert isinstance(res, str) and res
                    else:
                        assert isinstance(res, list) and res and all(
                            isinstance(x, str) for x in res
                        )

        # Deliverer contract: must have package()
        if hasattr(self, "package"):
            # Try with text only
            pkt = self.package("txt", None, None) # type: ignore
            assert pkt  # non-empty structure
            # Try with images only
            pkt2 = self.package(None, ["im"], None) # type: ignore
            assert pkt2
            # Try with audio only
            pkt3 = self.package(None, None, ["aud"]) # type: ignore
            assert pkt3 is not None 