"""Tests for the coding-agent skill (src/attachments/skill) and `att --skill`.

Covers:
    - The skill is true: every Python block in SKILL.md runs, in order,
      against real files; the Anthropic/OpenAI clients are stand-ins that
      check each request's shape the way the real APIs would
    - Every option the skill's table names is declared by the code
    - Front matter: name matches the folder, description within limits
    - `att --skill`: status per agent; `--install`: install, re-install
      (no-op), update, links and foreign folders left alone, named folders,
      failure keeps the previous copy; usage errors
"""

from __future__ import annotations

import base64
import re
import sys
import types
from pathlib import Path

import pytest

import attachments
from attachments import _skill, cli, dsl_schema
from attachments.deps import check_dep

SKILL_MD = _skill.SKILL_DIR / "SKILL.md"
TEXT = SKILL_MD.read_text(encoding="utf-8")


# =============================================================================
# The skill's content
# =============================================================================


def test_front_matter():
    match = re.match(r"---\nname: (.+)\ndescription: (.+)\n---\n", TEXT)
    assert match, "SKILL.md must start with name and description front matter"
    assert match.group(1) == _skill.SKILL_NAME
    description = match.group(2)
    assert 200 < len(description) <= 1024  # Claude Code's limit is 1024
    assert "0.25" in description  # the install trap is visible before loading


def test_skill_folder_holds_only_what_agents_read():
    names = {p.name for p in _skill.SKILL_DIR.iterdir() if p.name != "__pycache__"}
    assert names == {"SKILL.md", "options.md"}
    assert "options.md" in TEXT


def test_every_option_in_the_table_is_declared():
    schema = dsl_schema()
    declared = {
        o["name"]
        for group in ("processors", "sources")
        for opts in schema[group].values()
        for o in opts
    } | {
        a
        for group in ("processors", "sources")
        for opts in schema[group].values()
        for o in opts
        for a in o["aliases"]
    }
    table = TEXT.split("| file | option | effect |", 1)[1].split("\n\n", 1)[0]
    option_cells = [row.split("|")[2] for row in table.splitlines()[2:]]
    named = {name for cell in option_cells for name in re.findall(r"`(\w+):", cell)}
    assert named, "the option table moved; update this test"
    assert named <= declared, f"not declared: {sorted(named - declared)}"


def _python_blocks() -> list[str]:
    return re.findall(r"```python\n(.*?)```", TEXT, flags=re.S)


class _Recorder:
    """Stand-in client namespace: records calls, checks request shapes."""

    def __init__(self, calls: list, check):
        self._calls, self._check = calls, check

    def create(self, **kwargs):
        self._check(kwargs)
        self._calls.append(kwargs)
        return types.SimpleNamespace(content=[], choices=[], output_text="")


def _check_claude(kw: dict) -> None:
    assert {"model", "max_tokens", "messages"} <= set(kw)
    for message in kw["messages"]:
        assert message["role"] in ("user", "assistant")
        for block in message["content"]:
            if block["type"] == "text":
                assert block["text"], "Anthropic rejects empty text blocks"
            else:
                assert block["type"] == "image"
                assert block["source"]["type"] == "base64"
                base64.b64decode(block["source"]["data"], validate=True)


def _check_chat(kw: dict) -> None:
    assert {"model", "messages"} <= set(kw)
    for part in kw["messages"][0]["content"]:
        assert part["type"] in ("text", "image_url")
        if part["type"] == "image_url":
            assert part["image_url"]["url"].startswith("data:image/")


def _check_responses(kw: dict) -> None:
    assert {"model", "input"} <= set(kw)
    for part in kw["input"][0]["content"]:
        assert part["type"] in ("input_text", "input_image")
        if part["type"] == "input_image":
            assert part["image_url"].startswith("data:image/")


@pytest.fixture
def fake_clients(monkeypatch):
    calls: dict[str, list] = {"claude": [], "chat": [], "responses": []}
    anthropic = types.ModuleType("anthropic")
    anthropic.Anthropic = lambda: types.SimpleNamespace(  # type: ignore[attr-defined]
        messages=_Recorder(calls["claude"], _check_claude)
    )
    openai = types.ModuleType("openai")
    openai.OpenAI = lambda: types.SimpleNamespace(  # type: ignore[attr-defined]
        chat=types.SimpleNamespace(completions=_Recorder(calls["chat"], _check_chat)),
        responses=_Recorder(calls["responses"], _check_responses),
    )
    monkeypatch.setitem(sys.modules, "anthropic", anthropic)
    monkeypatch.setitem(sys.modules, "openai", openai)
    return calls


@pytest.fixture
def skill_files(tmp_path, monkeypatch):
    """The files the skill's examples name, plus offline stand-ins for its
    URL and GitHub examples."""
    pymupdf = pytest.importorskip("pymupdf")
    from PIL import Image

    def pdf(path: Path, pages: int) -> None:
        doc = pymupdf.open()
        for n in range(1, pages + 1):
            doc.new_page().insert_text((72, 72), f"Page {n}: revenue grew {n}%.")
        doc.save(path)
        doc.close()

    pdf(tmp_path / "report.pdf", 5)
    Image.new("RGB", (800, 600), "orange").save(tmp_path / "chart.png")
    (tmp_path / "photos").mkdir()
    Image.new("RGB", (640, 480), "gray").save(tmp_path / "photos" / "img_0042.jpg")
    (tmp_path / "scans").mkdir()
    pdf(tmp_path / "scans" / "a.pdf", 1)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "notes.txt").write_text("Meeting notes.")
    pdf(tmp_path / "docs" / "brief.pdf", 2)
    (tmp_path / "repo").mkdir()
    (tmp_path / "repo" / "main.py").write_text("print('hi')\n")

    real_att = attachments.att
    offline = {
        "https://example.com/paper.pdf": str(tmp_path / "report.pdf"),
        "github://owner/repo[ref: main]": str(tmp_path / "repo"),
    }

    def att(source, *args, **kwargs):
        if isinstance(source, str):
            source = offline.get(source, source)
        return real_att(source, *args, **kwargs)

    att.options = real_att.options  # type: ignore[attr-defined]
    att.from_prompt = real_att.from_prompt  # type: ignore[attr-defined]
    monkeypatch.setattr(attachments, "att", att)
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.mark.skipif(
    not (check_dep("pdf").available and check_dep("image").available),
    reason="the skill's examples use PDFs and pictures",
)
def test_every_python_example_runs(skill_files, fake_clients):
    blocks = _python_blocks()
    assert len(blocks) >= 8
    namespace: dict = {}
    for number, block in enumerate(blocks, start=1):
        try:
            exec(compile(block, f"SKILL.md block {number}", "exec"), namespace)
        except Exception as exc:  # pragma: no cover - the message is the point
            pytest.fail(f"SKILL.md python block {number} failed: {exc!r}\n{block}")
    assert len(fake_clients["claude"]) == 1
    assert len(fake_clients["chat"]) == 1
    assert len(fake_clients["responses"]) == 1
    # Section 5's promise: with sources=False no name reaches the model.
    _check_claude({"model": "m", "max_tokens": 1, "messages": namespace["messages"]})
    hidden = repr(namespace["messages"])
    assert "img_0042" not in hidden and "## " not in hidden
    assert [b["type"] for b in namespace["messages"][0]["content"]] == ["image", "text"]
    # Section 4 asked for page pictures: they were sent, page by page.
    blocks4 = fake_clients["claude"][0]["messages"][0]["content"]
    assert [b["type"] for b in blocks4][:4] == ["text", "image", "text", "image"]
    assert (skill_files / "cache.json").is_file()


def test_command_line_examples_run(skill_files, capsys):
    pytest.importorskip("pymupdf")
    assert cli.main(["report.pdf", "--pages", "1-4"]) == 0
    assert "Page 4" in capsys.readouterr().out
    assert cli.main(["docs/", "--json"]) == 0
    data = __import__("json").loads(capsys.readouterr().out)
    assert attachments.Artifacts.from_wire(data)
    assert cli.main(["--options", ".pdf"]) == 0


# =============================================================================
# att --skill
# =============================================================================


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A home folder where Claude Code and Pi are present, Codex is not."""
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".pi" / "agent").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def _states() -> dict[str, str]:
    return {place.agent: place.state for place in _skill.status()}


def test_status_lists_only_agents_present(home):
    assert _states() == {"Claude Code": "not installed", "Pi": "not installed"}


def test_install_everywhere_then_nothing_to_do(home, capsys):
    assert cli.main(["--skill", "--install"]) == 0
    out = capsys.readouterr().out
    assert out.count("installed (attachments ") == 2
    assert _states() == {"Claude Code": "up to date", "Pi": "up to date"}
    copy = home / ".claude" / "skills" / "attachments"
    assert (copy / "SKILL.md").read_text() == TEXT
    assert not list((home / ".claude" / "skills").glob(".attachments-*"))
    assert cli.main(["--skill", "--install"]) == 0
    assert capsys.readouterr().out.count("already up to date") == 2


def test_out_of_date_copy_is_updated(home, capsys):
    cli.main(["--skill", "--install"])
    stale = home / ".pi" / "agent" / "skills" / "attachments"
    (stale / "SKILL.md").write_text(TEXT.replace("Attachments 1.0", "Attachments 0.9"))
    (stale / "old-notes.md").write_text("from an older version")
    assert _states()["Pi"] == "out of date"
    capsys.readouterr()
    assert cli.main(["--skill", "--install"]) == 0
    assert "attachments: updated (attachments " in capsys.readouterr().out
    assert _states()["Pi"] == "up to date"
    assert not (stale / "old-notes.md").exists()


def test_link_is_left_alone(home, tmp_path_factory, capsys):
    checkout = tmp_path_factory.mktemp("checkout")
    skills = home / ".claude" / "skills"
    skills.mkdir()
    (skills / "attachments").symlink_to(checkout)
    assert _states()["Claude Code"] == "linked"
    assert cli.main(["--skill", "--install"]) == 0
    assert "left alone: a link to" in capsys.readouterr().out
    assert (skills / "attachments").is_symlink()


def test_someone_elses_folder_is_left_alone(home, capsys):
    other = home / ".claude" / "skills" / "attachments"
    other.mkdir(parents=True)
    (other / "SKILL.md").write_text("---\nname: email-attachments\n---\nmine\n")
    assert _states()["Claude Code"] == "other"
    assert cli.main(["--skill", "--install"]) == 1
    assert "holds something else" in capsys.readouterr().err
    assert (other / "SKILL.md").read_text().endswith("mine\n")
    assert _states()["Pi"] == "up to date"  # the others still got it


def test_install_into_named_folders(tmp_path, capsys):
    target = tmp_path / "project" / ".claude" / "skills"
    assert cli.main(["--skill", "--install", str(target)]) == 0
    assert (target / "attachments" / "SKILL.md").read_text() == TEXT
    assert (target / "attachments" / "options.md").is_file()


def test_failed_update_keeps_the_previous_copy(home, monkeypatch):
    cli.main(["--skill", "--install"])
    copy = home / ".claude" / "skills" / "attachments"
    (copy / "SKILL.md").write_text(TEXT + "\nlocal edit\n")

    def broken_copytree(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(_skill.shutil, "copytree", broken_copytree)
    with pytest.raises(OSError, match="disk full"):
        _skill.install([home / ".claude" / "skills"])
    assert (copy / "SKILL.md").read_text().endswith("local edit\n")
    assert not list(copy.parent.glob(".attachments-*"))


def test_no_agent_found(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert cli.main(["--skill"]) == 0
    assert "no coding agent found" in capsys.readouterr().out
    assert cli.main(["--skill", "--install"]) == 1
    assert "name a skills folder" in capsys.readouterr().err


@pytest.mark.parametrize("argv", [["--skill", "--force"], ["report.pdf", "--skill"]])
def test_usage_errors(argv, capsys):
    assert cli.main(argv) == 2
    assert "--skill" in capsys.readouterr().err
