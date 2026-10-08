"""Old Office / OpenDocument files via LibreOffice (``legacy_office.py``).

Conversion tests need LibreOffice (skipped otherwise); they make their
own ``.doc`` / ``.ppt`` / ``.odt`` from fresh docx/pptx files with
LibreOffice itself. Failure handling (missing program, crash, timeout)
uses small fake programs and always runs.
"""

from __future__ import annotations

import io
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from attachments import att
from attachments.deps import find_libreoffice
from attachments.types import is_missing_dependency

SOFFICE = find_libreoffice()
needs_lo = pytest.mark.skipif(SOFFICE is None, reason="LibreOffice not installed")


def _docx_bytes() -> bytes:
    docx = pytest.importorskip("docx")
    doc = docx.Document()
    doc.add_heading("Quarterly Report", level=1)
    doc.add_paragraph("Revenue grew in every region.")
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text, table.cell(0, 1).text = "Region", "Growth"
    table.cell(1, 0).text, table.cell(1, 1).text = "North", "12%"
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _pptx_bytes() -> bytes:
    pptx = pytest.importorskip("pptx")
    prs = pptx.Presentation()
    for title in ("Kickoff", "Roadmap"):
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        slide.shapes.title.text = title
        slide.placeholders[1].text = f"{title} details"
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def _convert(tmp_path: Path, data: bytes, src_ext: str, target: str) -> Path:
    src = tmp_path / f"made{src_ext}"
    src.write_bytes(data)
    subprocess.run(
        [
            SOFFICE,
            f"-env:UserInstallation={(tmp_path / 'profile').as_uri()}",
            "--headless",
            "--convert-to",
            target,
            "--outdir",
            str(tmp_path),
            str(src),
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )
    return tmp_path / f"made.{target}"


@needs_lo
@pytest.mark.parametrize("ext", ["doc", "odt"])
def test_word_formats(tmp_path: Path, ext: str):
    path = _convert(tmp_path, _docx_bytes(), ".docx", ext)
    [a] = att(str(path))
    assert a["meta"]["kind"] == "document"
    assert a["meta"]["extra"]["converted_from"] == f".{ext}"
    assert "Quarterly Report" in a["text"]
    assert "North" in a["text"] and "12%" in a["text"]


@needs_lo
@pytest.mark.parametrize("ext", ["ppt", "odp"])
def test_slide_formats_keep_slide_segments(tmp_path: Path, ext: str):
    path = _convert(tmp_path, _pptx_bytes(), ".pptx", ext)
    [a] = att(str(path))
    assert a["meta"]["kind"] == "slides"
    assert [s["page"] for s in a["meta"]["segments"]] == [1, 2]
    assert "Roadmap details" in a["text"]


def test_options_are_the_modern_formats():
    names = {o["name"] for o in att.options(".doc")}
    assert names == {o["name"] for o in att.options(".docx")}
    assert {o["name"] for o in att.options(".ppt")} == {
        o["name"] for o in att.options(".pptx")
    }


def _fake_program(tmp_path: Path, body: str) -> str:
    path = tmp_path / "fake-soffice"
    path.write_text(f"#!{sys.executable}\n{body}\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return str(path)


@pytest.mark.skipif(os.name != "posix", reason="fake program is a script")
class TestFailures:
    def test_missing_libreoffice(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(
            "attachments._processors.legacy_office.find_libreoffice", lambda: None
        )
        (tmp_path / "old.doc").write_bytes(b"\xd0\xcf\x11\xe0")
        [a] = att(str(tmp_path / "old.doc"))
        assert is_missing_dependency(a)
        assert "LibreOffice" in a["meta"]["error"]["message"]
        assert "pip install" not in a["meta"]["error"]["message"]

    def test_failed_conversion_is_a_parse_error(self, tmp_path: Path, monkeypatch):
        fake = _fake_program(
            tmp_path, "import sys; sys.stderr.write('boom'); sys.exit(1)"
        )
        monkeypatch.setenv("ATTACHMENTS_LIBREOFFICE", fake)
        (tmp_path / "old.ppt").write_bytes(b"\xd0\xcf\x11\xe0")
        [a] = att(str(tmp_path / "old.ppt"))
        assert a["meta"]["error"]["code"] == "parse-error"
        assert "boom" in a["meta"]["error"]["message"]

    def test_hung_conversion_is_killed(self, tmp_path: Path, monkeypatch):
        fake = _fake_program(tmp_path, "import time; time.sleep(60)")
        monkeypatch.setenv("ATTACHMENTS_LIBREOFFICE", fake)
        monkeypatch.setenv("ATTACHMENTS_LIBREOFFICE_TIMEOUT", "1")
        (tmp_path / "old.doc").write_bytes(b"\xd0\xcf\x11\xe0")
        [a] = att(str(tmp_path / "old.doc"))
        assert "did not finish within 1 s" in a["meta"]["error"]["message"]

    def test_the_file_name_never_reaches_the_command_line(
        self, tmp_path: Path, monkeypatch
    ):
        log = tmp_path / "argv.txt"
        fake = _fake_program(
            tmp_path,
            f"import sys; open({str(log)!r}, 'w').write(repr(sys.argv)); sys.exit(1)",
        )
        monkeypatch.setenv("ATTACHMENTS_LIBREOFFICE", fake)
        evil = tmp_path / "--convert-to=x; rm -rf ~.doc"
        evil.write_bytes(b"\xd0\xcf\x11\xe0")
        att(str(evil))
        assert "rm -rf" not in log.read_text()
