"""Tests for the audio transcription processor (faster-whisper backend).

ALL tests are mocked: a fake ``faster_whisper`` module is injected via
``sys.modules`` so no model weights are ever downloaded and no network is
touched (verified by running under ``HF_HUB_OFFLINE=1``). The fake
``WhisperModel`` returns deterministic segments with ``.start``/``.end``/
``.text`` and an info object with ``.duration``/``.language``.
"""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass

import pytest

import attachments._processors.audio as audio_mod
from attachments.deps import clear_cache
from attachments.types import (
    ERROR_MISSING_DEPENDENCY,
    ERROR_PROCESSING,
    is_missing_dependency,
)


@dataclass
class FakeSegment:
    start: float
    end: float
    text: str


@dataclass
class FakeInfo:
    duration: float = 9.5
    language: str = "en"


DEFAULT_SEGMENTS = [
    FakeSegment(0.0, 4.2, " Hello world. "),
    FakeSegment(4.2, 75.0, "Second segment."),
]


def install_fake_whisper(
    monkeypatch, segments=None, info=None, raise_on_transcribe=None
):
    """Inject a fake faster_whisper module; return the fake WhisperModel class."""
    calls = {"init": 0, "transcribe": []}

    class FakeWhisperModel:
        def __init__(self, model, device=None, compute_type=None):
            calls["init"] += 1
            self.model = model
            self.device = device
            self.compute_type = compute_type

        def transcribe(self, audio, language=None, **kw):
            calls["transcribe"].append({"audio": audio, "language": language})
            if raise_on_transcribe is not None:
                raise raise_on_transcribe
            return iter(segments or DEFAULT_SEGMENTS), info or FakeInfo()

    fake = types.ModuleType("faster_whisper")
    fake.WhisperModel = FakeWhisperModel
    monkeypatch.setitem(sys.modules, "faster_whisper", fake)
    clear_cache()
    return FakeWhisperModel, calls


@pytest.fixture(autouse=True)
def fresh_engine_cache(monkeypatch):
    """Isolate the module-level engine cache per test."""
    monkeypatch.setattr(audio_mod, "_ENGINES", {})
    yield
    clear_cache()


@pytest.fixture(autouse=True)
def ensure_audio_registered():
    """Re-register the audio processor and options for each test.

    The suite-wide autouse ``reset_processors()`` fixture (conftest.py)
    restores the built-in snapshot after every test; until audio.py is
    wired into ``_processors/__init__.py`` that snapshot predates this
    module's import-time registration, so it is replayed here. The
    conftest fixture cleans up afterwards.
    """
    from attachments._options import register_options
    from attachments._processors import register_processor

    for ext in audio_mod._AUDIO_EXTENSIONS:
        register_processor(ext, audio_mod.audio_processor)
        register_options(ext, audio_mod._AUDIO_OPTIONS)


class TestAudioProcessor:
    def test_registered_for_all_extensions(self):
        from attachments._processors import processors

        for ext in (".mp3", ".wav", ".m4a", ".flac", ".ogg", ".opus"):
            assert processors[ext] is audio_mod.audio_processor

    def test_transcript_text_and_segments(self, monkeypatch):
        install_fake_whisper(monkeypatch)

        result = audio_mod.audio_processor(b"fake-audio", filename="talk.mp3")

        assert result["text"] == "Hello world.\nSecond segment."
        segs = result["meta"]["segments"]
        assert len(segs) == 2
        assert all(s["kind"] == "section" for s in segs)
        assert segs[0]["label"] == "00:00–00:04"
        assert segs[1]["label"] == "00:04–01:15"
        # Exact offsets into text
        for seg, expected in zip(
            segs, ["Hello world.", "Second segment."], strict=True
        ):
            assert result["text"][seg["start"] : seg["end"]] == expected

    def test_meta_kind_extras_and_reserved_audio_empty(self, monkeypatch):
        install_fake_whisper(monkeypatch, info=FakeInfo(duration=12.3, language="fr"))

        result = audio_mod.audio_processor(b"x", filename="a.wav", model="small")

        assert result["meta"]["kind"] == "audio"
        extra = result["meta"]["extra"]
        assert extra == {"duration": 12.3, "language": "fr", "model": "small"}
        assert result["audio"] == []  # reserved for future audio OUTPUT payloads
        assert result["images"] == []

    def test_language_option_forwarded(self, monkeypatch):
        _, calls = install_fake_whisper(monkeypatch)

        audio_mod.audio_processor(b"x", filename="a.ogg", language="de")

        assert calls["transcribe"][0]["language"] == "de"

    def test_engine_cached_across_calls(self, monkeypatch):
        _, calls = install_fake_whisper(monkeypatch)

        audio_mod.audio_processor(b"one", filename="a.mp3")
        audio_mod.audio_processor(b"two", filename="b.mp3")

        assert calls["init"] == 1
        assert len(calls["transcribe"]) == 2

    def test_distinct_models_get_distinct_engines(self, monkeypatch):
        _, calls = install_fake_whisper(monkeypatch)

        audio_mod.audio_processor(b"one", filename="a.mp3", model="tiny")
        audio_mod.audio_processor(b"two", filename="b.mp3", model="base")

        assert calls["init"] == 2

    def test_audio_passed_as_file_like_no_temp_files(self, monkeypatch, tmp_path):
        """Bytes go to transcribe as an in-memory file-like — no temp files."""
        import io
        import tempfile

        _, calls = install_fake_whisper(monkeypatch)
        monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))

        audio_mod.audio_processor(b"raw-bytes", filename="a.flac")

        audio_arg = calls["transcribe"][0]["audio"]
        assert isinstance(audio_arg, io.BytesIO)
        assert audio_arg.getvalue() == b"raw-bytes"
        assert list(tmp_path.iterdir()) == []  # nothing leaked to disk

    def test_missing_dep_returns_typed_artifact(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "faster_whisper", None)
        clear_cache()

        result = audio_mod.audio_processor(b"x", filename="a.mp3")

        assert result["meta"]["error"]["code"] == ERROR_MISSING_DEPENDENCY
        assert "pip install" in result["meta"]["error"]["message"]
        assert is_missing_dependency(result)
        assert result["text"] == ""

    def test_transcription_failure_returns_processing_error(self, monkeypatch):
        install_fake_whisper(
            monkeypatch, raise_on_transcribe=RuntimeError("decode failed")
        )

        result = audio_mod.audio_processor(b"corrupt", filename="bad.m4a")

        assert result["meta"]["error"]["code"] == ERROR_PROCESSING
        assert "decode failed" in result["meta"]["error"]["message"]

    def test_options_registered(self):
        from attachments._options import get_options

        opts = {o.name: o for o in get_options(".mp3")}
        assert opts["model"].default == "base"
        assert "tiny" in opts["model"].help and "large-v3" in opts["model"].help
        assert opts["language"].default is None
        for o in opts.values():
            assert o.help and o.example
