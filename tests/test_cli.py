from __future__ import annotations

import json
from pathlib import Path

from attachments import cli


def test_parse_mixed_args_paths_and_options():
    paths, opts = cli._parse_mixed_args(
        ["--copy", "report.pdf", "--pages", "1-4", "--lang=en", "notes.txt"]
    )
    assert paths == ["report.pdf", "notes.txt"]
    assert opts["copy"] == "true"
    assert opts["pages"] == "1-4"
    assert opts["lang"] == "en"


def test_build_dsl_from_options_excludes_control():
    dsl = cli._build_dsl_from_options(
        {
            "copy": "true",
            "pages": "1-4",
            "sheet": "Sales",
            "verbose": "true",
        }
    )
    assert "[pages:1-4]" in dsl
    assert "[sheet:Sales]" in dsl
    assert "copy" not in dsl


def test_main_renders_meta_error_to_stderr(tmp_path: Path, capsys):
    code = cli.main([str(tmp_path / "missing.txt")])
    captured = capsys.readouterr()

    # Every input failed -> nonzero exit so pipelines/CI notice
    assert code == 1
    assert "[unpack-error]" in captured.err
    assert "unpack failed" in captured.err


def test_main_all_failed_json_exits_nonzero(tmp_path: Path, capsys):
    code = cli.main([str(tmp_path / "missing.txt"), "--json"])
    out = capsys.readouterr().out

    assert code == 1
    data = json.loads(out)
    assert data[0]["meta"]["error"]["code"] == "unpack-error"


def test_main_partial_failure_exits_zero(tmp_path: Path, capsys):
    ok = tmp_path / "ok.txt"
    ok.write_text("fine\n", encoding="utf-8")

    code = cli.main([str(ok), str(tmp_path / "missing.txt")])
    captured = capsys.readouterr()

    assert code == 0  # partial success is still success
    assert "fine" in captured.out
    assert "[unpack-error]" in captured.err


def test_main_no_args_prints_help(capsys):
    code = cli.main([])
    out = capsys.readouterr().out
    assert code == 0
    assert "attachments CLI" in out


def test_main_options_lists_all(capsys):
    code = cli.main(["--options"])
    out = capsys.readouterr().out

    assert code == 0
    assert ".pdf" in out
    assert ".xlsx" in out
    assert "github://" in out
    assert "pages (page)" in out
    assert "ref (branch, tag)" in out


def test_main_options_single_extension(capsys):
    code = cli.main(["--options", ".xlsx"])
    out = capsys.readouterr().out

    assert code == 0
    assert "sheet" in out
    assert "rows (max_rows)" in out
    assert ".pdf" not in out


def test_main_options_extension_without_dot(capsys):
    code = cli.main(["--options", "pdf"])
    out = capsys.readouterr().out

    assert code == 0
    assert "pages (page)" in out


def test_main_options_unknown_extension(capsys):
    code = cli.main(["--options", ".nope"])
    err = capsys.readouterr().err

    assert code == 1
    assert "No options registered" in err


def test_main_process_text_file(tmp_path: Path, capsys):
    p = tmp_path / "hello.txt"
    p.write_text("Hello CLI!\n", encoding="utf-8")

    code = cli.main([str(p)])
    out = capsys.readouterr().out

    assert code == 0
    assert "Hello CLI!" in out


def test_main_json_output(tmp_path: Path, capsys):
    p = tmp_path / "hello.txt"
    p.write_text("Hello JSON\n", encoding="utf-8")

    code = cli.main([str(p), "--json"])
    out = capsys.readouterr().out

    assert code == 0
    data = json.loads(out)
    assert isinstance(data, list)
    assert data[0]["text"].startswith("Hello JSON")


def test_main_copy_uses_clipboard_helper(monkeypatch, tmp_path: Path, capsys):
    copied: dict[str, str] = {}

    def fake_copy(text: str):
        copied["text"] = text

    monkeypatch.setattr(cli, "_copy_to_clipboard", fake_copy)

    p = tmp_path / "hello.txt"
    p.write_text("Copy me\n", encoding="utf-8")

    code = cli.main([str(p), "--copy", "--prompt", "Prompt:"])
    out = capsys.readouterr().out

    assert code == 0
    assert "Copied to clipboard" in out
    assert copied["text"].startswith("Prompt:")
    assert "Copy me" in copied["text"]


def test_main_copy_error_returns_nonzero(monkeypatch, tmp_path: Path, capsys):
    monkeypatch.setattr(
        cli,
        "_copy_to_clipboard",
        lambda _text: (_ for _ in ()).throw(RuntimeError("pyperclip missing")),
    )

    p = tmp_path / "hello.txt"
    p.write_text("Copy me\n", encoding="utf-8")

    code = cli.main([str(p), "--copy"])
    err = capsys.readouterr().err

    assert code == 1
    assert "pyperclip" in err.lower()
