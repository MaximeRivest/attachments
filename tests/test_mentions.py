"""``att.from_prompt``: files a prompt mentions, treated as untrusted input."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from attachments import att
from attachments._mentions import find_mentions


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch) -> Path:
    (tmp_path / "data.csv").write_text("a,b\n1,2\n")
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "todo list.md").write_text("- ship")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print(1)")
    (tmp_path / ".env").write_text("KEY=secret")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def sources(artifacts) -> list[str]:
    return [a["meta"]["source"] for a in artifacts]


class TestFindMentions:
    def test_kinds_and_order(self):
        found = find_mentions(
            'Use `notes/todo list.md`, then data.csv[rows: 1] and "src". '
            "Also https://x.org/a.pdf). Mail bob@x.org; it's fine."
        )
        assert [(m.text, m.explicit, m.url) for m in found] == [
            ("notes/todo list.md", True, False),
            ("data.csv[rows: 1]", False, False),
            ("src", True, False),
            ("https://x.org/a.pdf", False, True),
        ]

    def test_sentence_punctuation_is_not_part_of_a_name(self):
        assert [m.text for m in find_mentions("See report.pdf. Then a.txt,")] == [
            "report.pdf",
            "a.txt",
        ]


class TestFromPrompt:
    def test_attaches_existing_mentions_in_order(self, workspace: Path):
        a = att.from_prompt("Compare data.csv with `notes/todo list.md` and src/app.py")
        assert sources(a) == ["data.csv", "notes/todo list.md", "src/app.py"]

    def test_lookalikes_and_missing_files_are_ignored(self, workspace: Path):
        assert len(att.from_prompt("Node.js vs Vue.js, e.g. report.pdf")) == 0

    def test_dsl_in_the_prompt(self, workspace: Path):
        (workspace / "long.csv").write_text("n\n1\n2\n3\n")
        [a] = att.from_prompt("look at long.csv[rows: 1]")
        assert a["text"] == "| n |\n| --- |\n| 1 |"
        assert a["meta"]["source"] == "long.csv"

    def test_duplicates_once(self, workspace: Path):
        assert sources(att.from_prompt("data.csv and again data.csv")) == ["data.csv"]

    def test_folders_only_when_quoted(self, workspace: Path):
        assert len(att.from_prompt("the src folder")) == 0
        a = att.from_prompt("the `src` folder")
        assert a[0]["meta"]["kind"] == "directory"
        assert a[0]["meta"]["source"] == "src"

    def test_cannot_escape_the_root(self, workspace: Path, tmp_path_factory):
        outside = tmp_path_factory.mktemp("outside") / "secret.txt"
        outside.write_text("nope")
        rel = os.path.relpath(outside, workspace)
        prompt = f"read {outside} and {rel} and `/etc/hostname` and ~/x.txt"
        assert len(att.from_prompt(prompt)) == 0

    def test_links_out_of_the_root_are_refused(self, workspace: Path, tmp_path_factory):
        outside = tmp_path_factory.mktemp("o") / "private.txt"
        outside.write_text("nope")
        (workspace / "link.txt").symlink_to(outside)
        assert len(att.from_prompt("open link.txt")) == 0

    def test_secrets_are_never_attached(self, workspace: Path):
        (workspace / "deploy.pem").write_text("KEY")
        assert len(att.from_prompt("print `.env` and deploy.pem")) == 0

    def test_root_option(self, workspace: Path, tmp_path_factory):
        other = tmp_path_factory.mktemp("other")
        (other / "plan.md").write_text("plan")
        assert sources(att.from_prompt("see plan.md", root=[workspace, other])) == [
            "plan.md"
        ]

    def test_urls_are_off_by_default(self, workspace: Path, http_server):
        url = http_server.route("/page", "<h1>Hi</h1>")
        assert len(att.from_prompt(f"summarize {url}")) == 0
        assert http_server.requests == []
        a = att.from_prompt(f"summarize {url}", urls=True)
        assert a[0]["text"] == "# Hi"

    def test_options_apply(self, workspace: Path):
        [a] = att.from_prompt("data.csv", rows=1)
        assert a["text"] == "| a | b |\n| --- | --- |\n| 1 | 2 |"
