"""``att()`` on folders, patterns and archives: the overview artifact,
folder options, and the inputs ``att()`` accepts (lists, paths, ``~``).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from attachments import att


def _tree(root: Path, files: dict[str, str]) -> Path:
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return root


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return _tree(
        tmp_path / "proj",
        {
            "README.md": "# Proj",
            "src/app.py": "print('hi')",
            "src/util/helpers.py": "x = 1",
            ".env": "API_KEY=secret",
            "node_modules/dep/index.js": "x",
        },
    )


class TestOverview:
    def test_folder_starts_with_an_overview(self, project: Path):
        a = att(str(project))
        overview = a[0]
        assert overview["meta"]["kind"] == "directory"
        assert overview["meta"]["source"] == str(project)
        assert [x["meta"]["source"] for x in a[1:]] == [
            "README.md",
            "src/app.py",
            "src/util/helpers.py",
        ]
        text = overview["text"]
        assert text.startswith(f"Folder {project} — 3 files read")
        assert "secrets: 1 file (.env)" in text
        assert "node_modules/" in text
        assert "proj/\n├── README.md\n└── src/\n    ├── app.py\n    └── util/" in text
        assert "API_KEY" not in a.text  # the secret never reaches the prompt

    def test_extra_numbers(self, project: Path):
        extra = att(str(project))[0]["meta"]["extra"]
        assert extra["kind"] == "folder" and extra["files"] == 3
        assert extra["skipped"]["secret"]["examples"] == [".env"]

    def test_tree_false(self, project: Path):
        a = att(f"{project}[tree: false]")
        assert [x["meta"].get("kind") for x in a] == ["text"] * 3

    def test_files_false_is_the_overview_only(self, project: Path):
        a = att(str(project), files=False)
        assert len(a) == 1
        assert "contents not read" in a[0]["text"]
        assert "src/" in a[0]["text"]

    def test_patterns_have_no_overview_by_default(self, project: Path):
        a = att(str(project / "src" / "**" / "*.py"))
        assert [x["meta"]["source"] for x in a] == ["app.py", "util/helpers.py"]
        assert (
            att(str(project / "src" / "**" / "*.py[tree: true]"))[0]["meta"]["kind"]
            == "directory"
        )

    def test_limit_hit_is_always_reported(self, project: Path):
        a = att(str(project / "**" / "*"), max_files=1)
        overview = a[0]
        assert overview["meta"]["kind"] == "directory"
        assert "Stopped at max_files: 1 — 2 more files not read" in overview["text"]
        assert any("max_files" in w for w in overview["meta"]["warnings"])
        assert len(a) == 2

    def test_git_details(self, project: Path):
        if shutil.which("git") is None:
            pytest.skip("git not installed")
        run = lambda *cmd: subprocess.run(  # noqa: E731
            ["git", "-C", str(project), *cmd], check=True, capture_output=True
        )
        run("init", "-q", "-b", "main")
        run("remote", "add", "origin", "https://bot:tok3n@github.com/o/proj.git")
        run("add", "README.md")
        run("-c", "user.email=a@b", "-c", "user.name=t", "commit", "-qm", "init")
        commit = run("rev-parse", "HEAD").stdout.decode().strip()
        overview = att(str(project))[0]
        assert (
            f"Git: main @ {commit[:8]} (https://github.com/o/proj.git)"
            in overview["text"]
        )
        assert "tok3n" not in overview["text"]
        assert overview["meta"]["extra"]["git"]["commit"] == commit

    def test_invalid_folder_option_is_a_typed_error(self, project: Path):
        [a] = att(str(project), max_size="lots")
        assert a["meta"]["error"]["code"] == "invalid-option"

    def test_bad_option_type_warns_on_the_overview(self, project: Path):
        a = att(str(project), max_files="many")
        assert any("max_files" in w for w in a[0]["meta"]["warnings"])

    def test_folder_options_on_a_single_file_warn(self, project: Path):
        [a] = att(str(project / "README.md"), max_files=3)
        assert "apply to folders" in a["meta"]["warnings"][0]

    def test_empty_result_explains_itself(self, tmp_path: Path):
        _tree(tmp_path, {".env": "x", "uv.lock": "x"})
        [a] = att(str(tmp_path), tree=False)
        assert a["meta"]["kind"] == "directory"
        assert "0 files read" in a["text"] and "secrets" in a["text"]

    def test_folder_options_do_not_warn_per_file(self, project: Path):
        a = att(str(project), max_files=10, hidden=True, glob="*.py")
        assert all("warnings" not in x["meta"] for x in a)


class TestInputs:
    def test_list_of_paths_and_path_objects(self, project: Path):
        a = att([project / "README.md", str(project / "src" / "app.py")])
        assert [x["meta"]["source"] for x in a] == ["README.md", "app.py"]

    def test_options_apply_to_every_item(self, tmp_path: Path):
        _tree(tmp_path, {"a.csv": "x\n1\n2\n3", "b.csv": "y\n1\n2\n3"})
        a = att([tmp_path / "a.csv", tmp_path / "b.csv"], rows=1)
        assert [x["text"] for x in a] == [
            "| x |\n| --- |\n| 1 |",
            "| y |\n| --- |\n| 1 |",
        ]

    def test_nested_iterables_and_generators(self, project: Path):
        files = (p for p in [project / "README.md"])
        a = att([files, [str(project / "src" / "app.py")]])
        assert len(a) == 2

    def test_bad_items_become_errors_in_place(self, project: Path):
        a = att([project / "README.md", 42, None])
        assert a[0]["meta"]["source"] == "README.md"
        assert [x["meta"]["error"]["code"] for x in a[1:]] == ["unpack-error"] * 2

    def test_bytes_explain_themselves(self):
        [a] = att(b"%PDF-1.4")
        assert "not file contents" in a["meta"]["error"]["message"]

    def test_empty_list(self):
        assert len(att([])) == 0

    def test_tilde_and_file_uri(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        (tmp_path / "notes.txt").write_text("n")
        assert att("~/notes.txt")[0]["text"] == "n"
        assert att((tmp_path / "notes.txt").as_uri())[0]["text"] == "n"


def test_hiding_names_also_hides_the_overview(tmp_path: Path):
    _tree(tmp_path / "pets", {"tabby_cat.txt": "meow", "beagle.txt": "woof"})
    a = att(str(tmp_path / "pets"))
    assert "tabby_cat" in a.to_text()
    for output in (
        a.to_text(sources=False),
        str(a.parts(sources=False)),
        str(a.claude("Which animals?", sources=False)),
        str(a.openai("Which animals?", sources=False)),
        str(a.chunk(max_chars=1000, sources=False)),
    ):
        assert "tabby_cat" not in output and "beagle" not in output
        assert "meow" in output


def test_overview_conforms_to_the_artifact_schema(project: Path):
    import json

    jsonschema = pytest.importorskip("jsonschema")
    schema_path = Path(__file__).parent.parent / "spec" / "artifact.schema.json"
    schema = json.loads(schema_path.read_text())
    for artifact in att(str(project), max_files=1).to_wire():
        jsonschema.validate(artifact, schema)
