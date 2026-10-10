"""Helpers shared by the graders of evals/bench (imported by path).

Graders run with the WORKSPACE's Python (so they see what the agent built and
installed); this module therefore imports only what every workspace has:
the standard library, Pillow, lm15 and attachments.
"""

from __future__ import annotations

import base64
import binascii
import importlib.util
import io
import json
import re
import sys
from pathlib import Path

#: Bar colour per page of the charts deck (same as evals/skill/run.py).
CHART_COLORS = {
    1: (0.85, 0.1, 0.1),
    2: (0.1, 0.65, 0.1),
    3: (0.1, 0.2, 0.9),
    4: (1.0, 0.55, 0.0),
    5: (0.55, 0.1, 0.7),
    6: (0.4, 0.4, 0.4),
}


def load(path: str):
    """Import the agent's script as a module (without running __main__)."""
    spec = importlib.util.spec_from_file_location(Path(path).stem, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def emit(checks: dict) -> None:
    print(json.dumps(checks, default=str))


def _decode_image(value: str):
    from PIL import Image

    data = value.split(",", 1)[1] if value.startswith("data:") else value
    if len(data) < 64:
        return None
    try:
        raw = base64.b64decode(data, validate=True)
        img = Image.open(io.BytesIO(raw))
        img.load()
        return img
    except (binascii.Error, ValueError, OSError):
        return None


def images_in(obj) -> list:
    """Every picture carried as base64 or a data URL anywhere in a JSON value."""
    found = []
    if isinstance(obj, dict):
        for value in obj.values():
            found += images_in(value)
    elif isinstance(obj, list):
        for value in obj:
            found += images_in(value)
    elif isinstance(obj, str) and (obj.startswith("data:image") or len(obj) > 200):
        img = _decode_image(obj)
        if img is not None:
            found.append(img)
    return found


def text_of(obj) -> str:
    """All strings of a JSON value that are not pictures, joined."""
    if isinstance(obj, dict):
        return "\n".join(text_of(v) for v in obj.values())
    if isinstance(obj, list):
        return "\n".join(text_of(v) for v in obj)
    if isinstance(obj, str) and not (
        obj.startswith("data:") or len(obj) > 5000 and " " not in obj
    ):
        return obj
    return ""


def chart_page(img) -> int:
    """The page of the charts deck a picture shows, by its bar colour."""
    img = img.convert("RGB")
    colors = img.getcolors(maxcolors=img.size[0] * img.size[1])
    best = None
    for _count, rgb in sorted(colors, reverse=True):
        if max(rgb) - min(rgb) > 60:
            best = rgb
            break
    if best is None:
        best = sorted(colors, reverse=True)[1][1]
    return min(
        CHART_COLORS,
        key=lambda n: sum(
            (a - b * 255) ** 2 for a, b in zip(best, CHART_COLORS[n], strict=False)
        ),
    )


def provider_bodies(request) -> dict:
    """The JSON bodies lm15 would send to Anthropic, OpenAI and Gemini."""
    from lm15 import AnthropicLM, GeminiLM, OpenAILM

    out = {}
    for name, cls in (
        ("anthropic", AnthropicLM),
        ("openai", OpenAILM),
        ("gemini", GeminiLM),
    ):
        out[name] = json.loads(cls(api_key="x").build_request(request, False).body)
    return out


def ocr_text(img) -> str:
    from attachments._processors._ocr import recognize

    return recognize(img.convert("RGB")).text


def uses(path: str, *words: str) -> bool:
    try:
        source = Path(path).read_text()
    except OSError:
        return False
    return all(re.search(rf"\b{re.escape(w)}\b", source) for w in words)


def number(value) -> float | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        cleaned = re.sub(r"[^0-9.\-]", "", value.replace(",", ""))
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None
