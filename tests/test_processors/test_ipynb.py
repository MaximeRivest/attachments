"""Tests for the Jupyter notebook processor (stdlib-only, zero deps)."""

from __future__ import annotations

import base64
import json

import pytest

from attachments._options import get_options
from attachments._processors import ipynb as ipynb_module
from attachments._processors import processors
from attachments._processors.ipynb import ipynb_processor

# A real 1x1 transparent PNG.
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
    "YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)
TINY_PNG_B64 = base64.b64encode(TINY_PNG).decode()


@pytest.fixture(autouse=True)
def _ensure_registered():
    """Re-register after the conftest's processor-table reset."""
    ipynb_module.register()


def nb_bytes(cells, language="python", nbformat=4):
    """Build a minimal nbformat-4 notebook as JSON bytes."""
    return json.dumps(
        {
            "nbformat": nbformat,
            "nbformat_minor": 5,
            "metadata": {"language_info": {"name": language}},
            "cells": cells,
        }
    ).encode()


def code_cell(source, outputs=None):
    return {
        "cell_type": "code",
        "source": source,
        "metadata": {},
        "execution_count": 1,
        "outputs": outputs or [],
    }


class TestRegistration:
    def test_extension_registered_with_options(self):
        assert processors[".ipynb"] is ipynb_processor
        opts = get_options(".ipynb")
        assert [o.name for o in opts] == ["outputs"]
        assert opts[0].default is False


class TestRendering:
    def test_markdown_code_raw_cells(self):
        data = nb_bytes(
            [
                {"cell_type": "markdown", "source": "# Title\n\nhello"},
                code_cell(["x = 1\n", "print(x)"]),
                {"cell_type": "raw", "source": "raw stuff"},
            ]
        )

        result = ipynb_processor(data, filename="nb.ipynb")

        assert result["text"] == (
            "# Title\n\nhello\n\n```python\nx = 1\nprint(x)\n```\n\nraw stuff"
        )
        meta = result["meta"]
        assert meta["kind"] == "notebook"
        assert "error" not in meta
        assert meta["extra"]["cell_counts"] == {"code": 1, "markdown": 1, "raw": 1}
        assert meta["extra"]["language"] == "python"
        assert meta["extra"]["nbformat"] == 4

    def test_language_used_for_fence(self):
        data = nb_bytes([code_cell("1 + 1")], language="julia")

        result = ipynb_processor(data, filename="nb.ipynb")

        assert "```julia\n1 + 1\n```" in result["text"]
        assert result["meta"]["extra"]["language"] == "julia"

    def test_segments_slice_text_exactly(self):
        data = nb_bytes(
            [
                {"cell_type": "markdown", "source": "alpha"},
                code_cell("beta"),
                {"cell_type": "raw", "source": "gamma"},
            ]
        )

        result = ipynb_processor(data, filename="nb.ipynb")

        segs = result["meta"]["segments"]
        labels = [s["label"] for s in segs]
        assert labels == ["cell 1 (markdown)", "cell 2 (code)", "cell 3 (raw)"]
        assert all(s["kind"] == "section" for s in segs)
        text = result["text"]
        assert text[segs[0]["start"] : segs[0]["end"]] == "alpha"
        assert text[segs[1]["start"] : segs[1]["end"]] == "```python\nbeta\n```"
        assert text[segs[2]["start"] : segs[2]["end"]] == "gamma"


class TestOutputs:
    def _nb_with_outputs(self):
        return nb_bytes(
            [
                code_cell(
                    "print('hi')",
                    outputs=[
                        {"output_type": "stream", "name": "stdout", "text": "hi\n"},
                        {
                            "output_type": "execute_result",
                            "data": {"text/plain": "42"},
                            "execution_count": 1,
                            "metadata": {},
                        },
                        {
                            "output_type": "display_data",
                            "data": {"image/png": TINY_PNG_B64},
                            "metadata": {},
                        },
                    ],
                )
            ]
        )

    def test_outputs_false_by_default_excludes_text_and_images(self):
        result = ipynb_processor(self._nb_with_outputs(), filename="nb.ipynb")

        assert "```output" not in result["text"]
        assert result["images"] == []

    def test_outputs_true_includes_text_blocks_and_png(self):
        result = ipynb_processor(
            self._nb_with_outputs(), filename="nb.ipynb", outputs=True
        )

        assert "```output\nhi\n```" in result["text"]
        assert "```output\n42\n```" in result["text"]
        assert len(result["images"]) == 1
        img = result["images"][0]
        assert img["name"] == "nb-cell-1-output.png"
        assert img["mimetype"] == "image/png"
        assert img["bytes"] == TINY_PNG

    def test_output_segment_covers_outputs(self):
        result = ipynb_processor(
            self._nb_with_outputs(), filename="nb.ipynb", outputs=True
        )

        seg = result["meta"]["segments"][0]
        sliced = result["text"][seg["start"] : seg["end"]]
        assert sliced == result["text"]  # single cell: segment spans everything
        assert sliced.endswith("```")

    def test_long_stream_output_truncated(self):
        long = "x" * 5000
        data = nb_bytes(
            [
                code_cell(
                    "spam()",
                    outputs=[{"output_type": "stream", "name": "stdout", "text": long}],
                )
            ]
        )

        result = ipynb_processor(data, filename="nb.ipynb", outputs=True)

        assert "… (truncated)" in result["text"]
        assert "x" * 2001 not in result["text"]
        assert "x" * 100 in result["text"]


class TestEdgeCases:
    def test_empty_notebook(self):
        result = ipynb_processor(nb_bytes([]), filename="empty.ipynb")

        assert result["text"] == ""
        meta = result["meta"]
        assert "error" not in meta
        assert meta["kind"] == "notebook"
        assert meta["extra"]["cell_counts"] == {"code": 0, "markdown": 0, "raw": 0}
        assert "segments" not in meta

    def test_malformed_json_is_parse_error(self):
        result = ipynb_processor(b"{not json", filename="bad.ipynb")

        err = result["meta"]["error"]
        assert err["code"] == "parse-error"
        assert "parse" in err["message"].lower()

    def test_missing_cells_key_is_parse_error(self):
        result = ipynb_processor(b'{"nbformat": 4}', filename="bad.ipynb")

        assert result["meta"]["error"]["code"] == "parse-error"
        assert "cells" in result["meta"]["error"]["message"]

    def test_nbformat3_worksheets_gets_explanatory_parse_error(self):
        nb3 = json.dumps(
            {
                "nbformat": 3,
                "worksheets": [{"cells": [{"cell_type": "code", "input": "x = 1"}]}],
            }
        ).encode()

        result = ipynb_processor(nb3, filename="old.ipynb")

        err = result["meta"]["error"]
        assert err["code"] == "parse-error"
        assert "nbformat 3" in err["message"]
        assert "nbconvert" in err["message"]

    def test_non_dict_json_is_parse_error(self):
        result = ipynb_processor(b"[1, 2, 3]", filename="list.ipynb")

        assert result["meta"]["error"]["code"] == "parse-error"
