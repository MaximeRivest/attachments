import io, pathlib, tempfile, textwrap, pandas as pd
import pytest, base64

try:
    import fitz
except ImportError:
    fitz = None # type: ignore
try:
    from PIL import Image
except ImportError:
    Image = None # type: ignore

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