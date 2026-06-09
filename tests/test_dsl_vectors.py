"""Run the normative DSL test vectors (spec/dsl-test-vectors.json).

Every implementation of the DSL parser, in any language, must pass all
vectors byte-for-byte. Ranges are two-element integer arrays in JSON;
the Python parser maps them to tuples.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from attachments.dsl import parse_dsl

_VECTORS_PATH = (
    Path(__file__).resolve().parent.parent / "spec" / "dsl-test-vectors.json"
)
_SPEC = json.loads(_VECTORS_PATH.read_text(encoding="utf-8"))


def _expected_options(options: dict[str, Any]) -> dict[str, Any]:
    """Map JSON two-element arrays (ranges) to Python tuples."""
    return {
        key: tuple(value) if isinstance(value, list) else value
        for key, value in options.items()
    }


def test_vector_file_version():
    assert _SPEC["version"] == 1
    assert len(_SPEC["vectors"]) >= 30


@pytest.mark.parametrize(
    "vector", _SPEC["vectors"], ids=[v["name"] for v in _SPEC["vectors"]]
)
def test_vector(vector: dict[str, Any]):
    source, options = parse_dsl(vector["input"])
    assert source == vector["source"], f"source mismatch for {vector['input']!r}"
    assert options == _expected_options(vector["options"]), (
        f"options mismatch for {vector['input']!r}"
    )
