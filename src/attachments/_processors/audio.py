"""Processor for audio files (.mp3 .wav .m4a .flac .ogg .opus).

Transcribes speech to text with `faster-whisper
<https://github.com/SYSTRAN/faster-whisper>`_.
Requires ``faster-whisper``: ``pip install attachments[audio]``

.. warning:: **First use downloads model weights.** The default ``base``
   model is ~150 MB and is fetched from Hugging Face the first time it is
   used (then cached locally). Larger models (``large-v3``) are multiple
   gigabytes. On servers or anywhere a surprise download is unacceptable,
   prefer the attachments service tier, which runs transcription remotely
   and keeps your process dependency- and download-free.

The artifact's reserved ``audio`` list stays EMPTY: per the IR contract it
is reserved for future audio OUTPUT payloads (e.g. extracted/normalized
clips). The transcript is text, so it goes in ``text`` with per-whisper-
segment offsets in ``meta.segments``.
"""

from __future__ import annotations

import io
import logging
from typing import Any

from .._options import Option, register_options
from ..types import (
    ERROR_PROCESSING,
    error_artifact,
    make_artifact,
    missing_dep_artifact,
)
from . import register_processor

log = logging.getLogger("attachments.processors.audio")

_AUDIO_EXTENSIONS = (".mp3", ".wav", ".m4a", ".flac", ".ogg", ".opus")

#: Module-level engine cache keyed by model name. WhisperModel load is
#: expensive (weights are read, possibly downloaded), so each model is
#: constructed once per process and reused across calls.
_ENGINES: dict[str, Any] = {}


def _format_timestamp(seconds: float) -> str:
    """Render seconds as ``MM:SS`` (minutes can exceed 59).

    Examples:
        >>> _format_timestamp(0)
        '00:00'
        >>> _format_timestamp(75.4)
        '01:15'
        >>> _format_timestamp(3725)
        '62:05'
    """
    total = int(seconds)
    return f"{total // 60:02d}:{total % 60:02d}"


def _get_engine(model: str) -> Any:
    """Return a cached ``WhisperModel`` for ``model``, creating it on first use."""
    if model not in _ENGINES:
        from faster_whisper import WhisperModel

        _ENGINES[model] = WhisperModel(model, device="cpu", compute_type="int8")
    return _ENGINES[model]


def audio_processor(data: bytes, **options: Any) -> dict[str, Any]:
    """Transcribe audio bytes to a text artifact.

    Options:
        filename: Original filename (for metadata).
        model: Whisper model size — tiny/base/small/medium/large-v3
            (default ``"base"``).
        language: Spoken language code (e.g. ``"en"``); default ``None``
            autodetects.

    Note: the first call with a given model downloads its weights
    (~150 MB for ``base``) from Hugging Face. See the module docstring.
    """
    filename = options.get("filename", "audio")
    model = options.get("model") or "base"
    language = options.get("language") or None

    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return missing_dep_artifact(filename, "audio")

    try:
        engine = _get_engine(model)
        # faster_whisper.WhisperModel.transcribe accepts a file-like object
        # (Union[str, BinaryIO, np.ndarray]) — no temp file needed.
        whisper_segments, info = engine.transcribe(io.BytesIO(data), language=language)

        parts: list[str] = []
        segments: list[dict[str, Any]] = []
        offset = 0
        for seg in whisper_segments:
            seg_text = seg.text.strip()
            if parts:
                offset += 1  # joining "\n"
            start = offset
            end = start + len(seg_text)
            parts.append(seg_text)
            segments.append(
                {
                    "kind": "section",
                    "label": (
                        f"{_format_timestamp(seg.start)}–{_format_timestamp(seg.end)}"
                    ),
                    "start": start,
                    "end": end,
                }
            )
            offset = end
    except Exception as e:
        # Corrupt/undecodable input and engine failures both surface here as
        # backend-specific exceptions that are not reliably distinguishable,
        # so they map to the catch-all ERROR_PROCESSING rather than
        # ERROR_PARSE.
        log.warning("failed to transcribe %s: %s", filename, e)
        return error_artifact(
            filename, ERROR_PROCESSING, f"Failed to transcribe audio: {e}"
        )

    meta: dict[str, Any] = {
        "kind": "audio",
        "extra": {
            "duration": getattr(info, "duration", None),
            "language": getattr(info, "language", None),
            "model": model,
        },
    }
    if segments:
        meta["segments"] = segments
    # audio=[] (default): reserved for future audio OUTPUT payloads only.
    return make_artifact(text="\n".join(parts), meta=meta)


for _ext in _AUDIO_EXTENSIONS:
    register_processor(_ext, audio_processor)

_AUDIO_OPTIONS = (
    Option(
        "model",
        "str",
        default="base",
        help="Whisper model size: tiny, base, small, medium, or large-v3.",
        example="model: small",
    ),
    Option(
        "language",
        "str",
        default=None,
        help="Spoken language code (e.g. 'en', 'fr'); omit to autodetect.",
        example="language: en",
    ),
)
for _ext in _AUDIO_EXTENSIONS:
    register_options(_ext, _AUDIO_OPTIONS)
