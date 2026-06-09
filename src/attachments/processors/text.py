from __future__ import annotations

from typing import Any

from ..types import make_artifact
from ..utils import guess_decode
from . import register_processor


def text_processor(data: bytes, **options: Any) -> dict[str, Any]:
    enc, text = guess_decode(data)
    filename = options.get("filename")
    return make_artifact(
        text=text,
        meta={
            "kind": "text",
            "extra": {
                "encoding": enc,
                "chars": len(text),
                "filename": filename,
            },
        },
    )


# Register the text catch-all and common text extensions
register_processor("__text__", text_processor)
for ext in (
    ".txt",
    ".md",
    ".markdown",
    ".rst",
    ".csv",
    ".tsv",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".log",
    ".py",
    ".java",
    ".js",
    ".ts",
    ".css",
    ".html",
    ".xml",
    ".tex",
):
    register_processor(ext, text_processor)
