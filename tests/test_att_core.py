from __future__ import annotations

import zipfile
from pathlib import Path


def _make_nested_zip(path: Path) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("inner/inner.txt", "hello from inner zip\n")


def test_unpack_directory_and_archives(tmp_path: Path) -> None:
    # Arrange: directory with a text file, a nested zip, and an .xlsx (not expanded)
    (tmp_path / "hello.txt").write_text("Hello world!\n", encoding="utf-8")
    _make_nested_zip(tmp_path / "nested.zip")
    # Create a placeholder .xlsx (not a real workbook).
    # Unpack should NOT explode it — processor handles it by extension.
    (tmp_path / "table.xlsx").write_bytes(b"not-a-real-xlsx\n")

    # Act
    from attachments import unpack

    pairs = unpack(str(tmp_path))
    names = {name for name, _ in pairs}

    # Assert: directory walked, nested.zip expanded, .xlsx not expanded
    assert "hello.txt" in names
    assert any(
        n.startswith("nested.zip/") and n.endswith("inner/inner.txt") for n in names
    )
    assert "table.xlsx" in names
    # Ensure no accidental explosion of xlsx
    assert not any("table.xlsx/" in n for n in names)


def test_att_text_and_xlsx(tmp_path: Path) -> None:
    # Arrange
    (tmp_path / "hello.txt").write_text("Hello world!\n", encoding="utf-8")
    (tmp_path / "notes.md").write_text("# Title\nBody\n", encoding="utf-8")
    (tmp_path / "table.xlsx").write_bytes(b"not-a-real-xlsx\n")

    # Act
    from attachments import att

    artifacts = att(str(tmp_path))
    by_source = {a["meta"].get("source"): a for a in artifacts}

    # Assert text files processed via text processor
    assert "hello.txt" in by_source
    assert "Hello world" in by_source["hello.txt"]["text"]
    assert "notes.md" in by_source
    assert "Title" in by_source["notes.md"]["text"]

    # Assert xlsx artifact present; depending on optional deps, either
    # parsed or a typed error in meta.
    assert "table.xlsx" in by_source
    xlsx_meta = by_source["table.xlsx"]["meta"]
    ok = ("engine" in xlsx_meta.get("extra", {})) or ("error" in xlsx_meta)
    assert ok, f"unexpected xlsx meta: {xlsx_meta}"
