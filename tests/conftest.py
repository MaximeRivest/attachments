import io, pathlib, tempfile, textwrap, pandas as pd
import pytest, base64
import importlib
import sys
import os
import importlib.util
import pkgutil
from unittest.mock import patch

try:
    import fitz
except ImportError:
    fitz = None # type: ignore
try:
    from PIL import Image
except ImportError:
    Image = None # type: ignore

# Ensure plugins are properly loaded for all tests
@pytest.fixture(autouse=True)
def ensure_plugins_loaded():
    """Ensure all built-in plugins are properly loaded before each test."""
    # First clean up all existing attachments modules from sys.modules
    # to ensure a completely fresh reload
    to_delete = [k for k in sys.modules if k.startswith("src.attachments")]
    for k in to_delete:
        del sys.modules[k]
    
    # Now reimport base modules
    import src.attachments.registry
    import src.attachments.core
    import src.attachments.plugin_api
    
    # Get a fresh registry
    from src.attachments.registry import REGISTRY
    REGISTRY.clear()
    
    # Import core classes to register them
    from src.attachments.core import Loader, Renderer, Transform, Deliverer
    
    # Dynamically discover and import all plugin modules
    import src.attachments.plugins
    
    # Use pkgutil to walk through all subpackages
    plugin_types = ['loaders', 'renderers', 'transforms', 'deliverers']
    
    # For each plugin type, dynamically import all modules
    for plugin_type in plugin_types:
        plugin_path = os.path.join(os.path.dirname(src.attachments.plugins.__file__), plugin_type)
        if os.path.exists(plugin_path):
            # Find all .py files that don't start with _ (skipping __init__.py and others)
            for module_file in os.listdir(plugin_path):
                if module_file.endswith('.py') and not module_file.startswith('_'):
                    module_name = f"src.attachments.plugins.{plugin_type}.{module_file[:-3]}"
                    try:
                        # Import the module to trigger registration
                        if module_name not in sys.modules:
                            importlib.import_module(module_name)
                    except ImportError as e:
                        print(f"Warning: Could not import plugin module {module_name}: {e}")
    
    # Finally import the main package to complete registration
    import src.attachments

def get_sample_path(ext, tmp_path=None):
    """Return a sample file path for a given extension (csv, img, pdf)."""
    if ext == "csv":
        if tmp_path is None:
            tmp_path = pathlib.Path(tempfile.gettempdir())
        df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
        p = tmp_path / "s.csv"
        df.to_csv(p, index=False)
        return str(p)
    if ext == "img":
        if Image is None:
            import pytest
            pytest.skip("Pillow (PIL) not available") # type: ignore
        if tmp_path is None:
            tmp_path = pathlib.Path(tempfile.gettempdir())
        p = tmp_path / "s.png"
        Image.new("RGB", (10, 10), (123, 222, 42)).save(p)
        return str(p)
    if ext == "pdf":
        if fitz is None:
            import pytest
            pytest.skip("PyMuPDF (fitz) not available") # type: ignore
        if tmp_path is None:
            tmp_path = pathlib.Path(tempfile.gettempdir())
        p = tmp_path / "s.pdf"
        doc = fitz.open()
        doc.new_page().insert_text((72, 72), "hi")
        doc.save(p)
        return str(p)
    raise ValueError(f"Unknown ext: {ext}")

@pytest.fixture
def sample_txt(tmp_path):
    """Create a sample text file."""
    p = tmp_path / "sample.txt"
    p.write_text("This is a sample text file for testing.")
    return str(p)

@pytest.fixture
def sample_csv(tmp_path):
    return get_sample_path("csv", tmp_path)

@pytest.fixture
def sample_img(tmp_path):
    if Image is None:
        pytest.skip("Pillow (PIL) not available") # type: ignore
    return get_sample_path("img", tmp_path)

@pytest.fixture
def sample_pdf(tmp_path):
    if fitz is None:
        pytest.skip("PyMuPDF (fitz) not available") # type: ignore
    return get_sample_path("pdf", tmp_path)

@pytest.fixture
def sample_audio(tmp_path):
    """Create a minimal, silent WAV file."""
    import wave, struct
    p = tmp_path / "s.wav"
    sample_rate = 44100
    duration_ms = 100
    n_frames = int(sample_rate * (duration_ms / 1000.0))
    n_channels = 1
    sampwidth = 2 # bytes per sample
    data = struct.pack('<h', 0) * n_frames # silent audio

    with wave.open(str(p), 'wb') as wf:
        wf.setnchannels(n_channels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(sample_rate)
        wf.writeframes(data)
    return str(p) 