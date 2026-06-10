"""Tests for the attachments MCP server (`attachments-mcp`).

Uses the mcp SDK's in-memory client-server session — no subprocesses,
no network. `mcp` is a dev dependency, so everything here runs in CI.
"""

from __future__ import annotations

import importlib
import io
import sys

import anyio
import pytest

from attachments import mcp_server
from attachments.mcp_server import (
    MAX_IMAGE_BYTES,
    MAX_IMAGES,
    _normalize_options_key,
    create_server,
    main,
)


def _call(tool: str, arguments: dict):
    """Call one tool against a fresh in-memory server, return the result."""
    from mcp.shared.memory import (
        create_connected_server_and_client_session as connect,
    )

    async def go():
        async with connect(create_server()) as client:
            return await client.call_tool(tool, arguments)

    return anyio.run(go)


def _texts(result) -> str:
    """All text content of a tool result, joined."""
    return "\n".join(c.text for c in result.content if c.type == "text")


def _png_bytes(width: int = 4, height: int = 4, *, noise: bool = False) -> bytes:
    """A real PNG; with noise=True the payload compresses poorly (large)."""
    from PIL import Image

    if noise:
        import os as _os

        image = Image.frombytes("RGB", (width, height), _os.urandom(width * height * 3))
    else:
        image = Image.new("RGB", (width, height), "red")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _two_page_pdf(path) -> None:
    """Write a 2-page PDF with distinct extractable text per page."""
    import pymupdf

    doc = pymupdf.open()
    for marker in ("alpha-page-one", "beta-page-two"):
        page = doc.new_page()
        page.insert_text((72, 72), marker)
    doc.save(str(path))
    doc.close()


# ---------------------------------------------------------------------------
# Tool listing / schemas
# ---------------------------------------------------------------------------


class TestToolListing:
    def test_exactly_two_tools(self):
        from mcp.shared.memory import (
            create_connected_server_and_client_session as connect,
        )

        async def go():
            async with connect(create_server()) as client:
                return await client.list_tools()

        tools = {t.name: t for t in anyio.run(go).tools}
        assert sorted(tools) == ["att", "att_options"]

        att_schema = tools["att"].inputSchema
        assert att_schema["required"] == ["source"]
        assert att_schema["properties"]["source"]["type"] == "string"
        assert "options" in att_schema["properties"]
        assert "options" not in att_schema.get("required", [])

        opts_schema = tools["att_options"].inputSchema
        assert "extension" in opts_schema["properties"]
        assert opts_schema.get("required", []) == []

    def test_descriptions_teach(self):
        from mcp.shared.memory import (
            create_connected_server_and_client_session as connect,
        )

        async def go():
            async with connect(create_server()) as client:
                return await client.list_tools()

        tools = {t.name: t for t in anyio.run(go).tools}
        att_desc = tools["att"].description
        assert "github://" in att_desc
        assert "pages" in att_desc and "ocr" in att_desc
        assert "never raise" in att_desc
        assert "per-format options" in tools["att_options"].description


# ---------------------------------------------------------------------------
# att tool
# ---------------------------------------------------------------------------


class TestAttTool:
    def test_text_file(self, tmp_path):
        path = tmp_path / "notes.md"
        path.write_text("The quick brown fox.")
        result = _call("att", {"source": str(path)})
        assert not result.isError
        assert "The quick brown fox." in _texts(result)
        assert result.content[0].type == "text"

    def test_image_source_returns_image_content(self, tmp_path):
        path = tmp_path / "pic.png"
        path.write_bytes(_png_bytes())
        result = _call("att", {"source": str(path)})
        images = [c for c in result.content if c.type == "image"]
        assert len(images) == 1
        assert images[0].mimeType == "image/png"
        assert images[0].data  # base64 payload present
        # Text block comes FIRST.
        assert result.content[0].type == "text"

    def test_oversized_image_skipped_with_note(self, tmp_path, monkeypatch):
        monkeypatch.setattr(mcp_server, "MAX_IMAGE_BYTES", 64)
        path = tmp_path / "big.png"
        png = _png_bytes(64, 64, noise=True)
        assert len(png) > 64
        path.write_bytes(png)
        result = _call("att", {"source": str(path)})
        assert not any(c.type == "image" for c in result.content)
        text = _texts(result)
        assert "image skipped" in text
        assert "cap" in text

    def test_image_cap_count(self, monkeypatch):
        # Unit-level: the cap logic without 7 real files.
        from attachments.mcp_server import _content_from_artifacts
        from attachments.types import make_artifact

        png = _png_bytes()
        artifacts = [
            make_artifact(
                images=[
                    {"name": f"p-{i}.png", "mimetype": "image/png", "bytes": png}
                    for i in range(MAX_IMAGES + 2)
                ],
                meta={"source": "deck.pptx"},
            )
        ]
        blocks = _content_from_artifacts("deck.pptx", artifacts)
        assert sum(b.type == "image" for b in blocks) == MAX_IMAGES
        assert "2 more image(s) omitted" in blocks[0].text

    def test_nonexistent_file_is_teaching_text_not_exception(self, tmp_path):
        result = _call("att", {"source": str(tmp_path / "ghost.pdf")})
        assert not result.isError  # errors come back as readable text
        text = _texts(result)
        assert "unpack-error" in text
        assert "--- notes ---" in text

    def test_options_dict_is_kwargs_twin(self, tmp_path):
        path = tmp_path / "two.pdf"
        _two_page_pdf(path)
        full = _texts(_call("att", {"source": str(path)}))
        assert "alpha-page-one" in full and "beta-page-two" in full
        limited = _texts(
            _call("att", {"source": str(path), "options": {"pages": "1-1"}})
        )
        assert "alpha-page-one" in limited
        assert "beta-page-two" not in limited

    def test_warnings_reach_the_agent(self, tmp_path):
        path = tmp_path / "data.csv"
        path.write_text("a,b\n1,2\n")
        result = _call("att", {"source": str(path), "options": {"pages": "1-2"}})
        text = _texts(result)
        assert "--- notes ---" in text
        assert "pages" in text  # unknown-option warning surfaced

    def test_empty_result_is_explained(self):
        from attachments.mcp_server import _content_from_artifacts

        blocks = _content_from_artifacts("void.bin", [])
        assert len(blocks) == 1
        assert "no content extracted" in blocks[0].text


# ---------------------------------------------------------------------------
# att_options tool
# ---------------------------------------------------------------------------


class TestAttOptionsTool:
    def test_pdf_table(self):
        text = _texts(_call("att_options", {"extension": ".pdf"}))
        assert "pages" in text
        assert "DSL syntax" in text

    def test_extension_without_dot(self):
        assert "sheet" in _texts(_call("att_options", {"extension": "xlsx"}))

    def test_full_catalog(self):
        text = _texts(_call("att_options", {}))
        assert "Processors" in text
        assert ".pdf" in text
        assert "github://" in text

    def test_normalize_options_key(self):
        assert _normalize_options_key("PDF") == ".pdf"
        assert _normalize_options_key("__text__") == "__text__"


# ---------------------------------------------------------------------------
# Lazy mcp import guard
# ---------------------------------------------------------------------------


class TestMissingMcp:
    def test_module_imports_without_mcp(self, monkeypatch):
        """attachments.mcp_server must import cleanly when mcp is absent."""
        for name in [n for n in sys.modules if n == "mcp" or n.startswith("mcp.")]:
            monkeypatch.delitem(sys.modules, name)
        monkeypatch.setitem(sys.modules, "mcp", None)  # mask the SDK
        monkeypatch.delitem(sys.modules, "attachments.mcp_server")
        module = importlib.import_module("attachments.mcp_server")
        assert hasattr(module, "main")

    def test_main_prints_teaching_message(self, monkeypatch, capsys):
        for name in [n for n in sys.modules if n == "mcp" or n.startswith("mcp.")]:
            monkeypatch.delitem(sys.modules, name)
        monkeypatch.setitem(sys.modules, "mcp", None)
        monkeypatch.delitem(sys.modules, "attachments.mcp_server")
        module = importlib.import_module("attachments.mcp_server")
        assert module.main([]) == 1
        err = capsys.readouterr().err
        assert "attachments-mcp requires the mcp extra" in err
        assert "pip install attachments[mcp]" in err


# ---------------------------------------------------------------------------
# main() / --help
# ---------------------------------------------------------------------------


class TestMain:
    def test_help_flag(self, capsys):
        assert main(["--help"]) == 0
        out = capsys.readouterr().out
        assert "claude mcp add attachments" in out
        assert "mcpServers" in out
        assert "ATTACHMENTS_SERVICE_URL" in out

    @pytest.mark.parametrize("flag", ["-h", "help"])
    def test_help_aliases(self, flag, capsys):
        assert main([flag]) == 0
        assert "attachments-mcp" in capsys.readouterr().out

    def test_constants_sane(self):
        assert MAX_IMAGES == 6
        assert MAX_IMAGE_BYTES == 1_500_000
