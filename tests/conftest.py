"""Test configuration for the new modular attachments architecture."""

import pathlib
import tempfile
import pandas as pd
import pytest
from typing import Optional, Any

try:
    import fitz
except ImportError:
    fitz = None
    
try:
    from PIL import Image
except ImportError:
    Image = None


def get_sample_path(ext: str, tmp_path: Optional[pathlib.Path] = None) -> str:
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
            pytest.skip("Pillow (PIL) not available", allow_module_level=True)
        if tmp_path is None:
            tmp_path = pathlib.Path(tempfile.gettempdir())
        p = tmp_path / "s.png"
        Image.new("RGB", (10, 10), (123, 222, 42)).save(p)
        return str(p)
        
    if ext == "pdf":
        if fitz is None:
            pytest.skip("PyMuPDF (fitz) not available", allow_module_level=True)
        if tmp_path is None:
            tmp_path = pathlib.Path(tempfile.gettempdir())
        p = tmp_path / "s.pdf"
        doc = fitz.open()
        doc.new_page().insert_text((72, 72), "Hello PDF!")
        doc.save(p)
        doc.close()
        return str(p)
        
    raise ValueError(f"Unknown ext: {ext}")


@pytest.fixture
def sample_txt(tmp_path: pathlib.Path) -> str:
    """Create a sample text file."""
    p = tmp_path / "sample.txt"
    p.write_text("This is a sample text file for testing.")
    return str(p)


@pytest.fixture
def sample_csv(tmp_path: pathlib.Path) -> str:
    return get_sample_path("csv", tmp_path)


@pytest.fixture
def sample_img(tmp_path: pathlib.Path) -> str:
    if Image is None:
        pytest.skip("Pillow (PIL) not available", allow_module_level=True)
    return get_sample_path("img", tmp_path)


@pytest.fixture
def sample_pdf(tmp_path: pathlib.Path) -> str:
    if fitz is None:
        pytest.skip("PyMuPDF (fitz) not available", allow_module_level=True)
    return get_sample_path("pdf", tmp_path)


@pytest.fixture
def sample_audio(tmp_path: pathlib.Path) -> str:
    """Create a minimal, silent WAV file."""
    import wave
    import struct
    
    p = tmp_path / "s.wav"
    sample_rate = 44100
    duration_ms = 100
    n_frames = int(sample_rate * (duration_ms / 1000.0))
    n_channels = 1
    sampwidth = 2  # bytes per sample
    data = struct.pack('<h', 0) * n_frames  # silent audio

    with wave.open(str(p), 'wb') as wf:
        wf.setnchannels(n_channels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(sample_rate)
        wf.writeframes(data)
    return str(p) 