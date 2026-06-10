"""
Sync tests for the generated DSL assets.

=============================================================================
TEST GUIDELINES FOR GENERATED ASSETS
=============================================================================

GOOD tests:
    - spec/dsl-schema.json on disk == the live dsl_schema() serialization
      (CI fails when option declarations change without regenerating)
    - docs/dsl-options.md on disk == the regenerated cheatsheet
    - src/attachments/__init__.pyi on disk == the regenerated typing stub
      (covers the public exports AND every declared option/alias kwarg)
    - The stub parses as valid Python and re-exports all of __all__
    - Basic shape of the committed JSON (version, .pdf, github://)

BAD tests:
    - Testing dsl_schema() internals (test_options.py)
    - Re-testing markdown rendering details beyond byte-for-byte sync
    - Running a real type checker (best-effort, done out-of-band)

The generator lives outside the package (scripts/gen_dsl_assets.py), so it
is imported here via importlib.util.spec_from_file_location — no sys.path
manipulation, and pytest can run this from the repo root.

=============================================================================
"""

from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

import attachments
from attachments import dsl_schema

REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = REPO_ROOT / "scripts" / "gen_dsl_assets.py"
SCHEMA_PATH = REPO_ROOT / "spec" / "dsl-schema.json"
DOCS_PATH = REPO_ROOT / "docs" / "dsl-options.md"
STUB_PATH = REPO_ROOT / "src" / "attachments" / "__init__.pyi"

REGEN_HINT = "stale — regenerate with: uv run python scripts/gen_dsl_assets.py"


@pytest.fixture(scope="module")
def generator() -> ModuleType:
    """Import scripts/gen_dsl_assets.py as a module via importlib."""
    spec = importlib.util.spec_from_file_location("gen_dsl_assets", GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_schema_json_in_sync(generator: ModuleType) -> None:
    """spec/dsl-schema.json must match the live dsl_schema() serialization."""
    expected = generator.render_schema_json(dsl_schema())
    on_disk = SCHEMA_PATH.read_text(encoding="utf-8")
    assert on_disk == expected, f"spec/dsl-schema.json is {REGEN_HINT}"


def test_docs_markdown_in_sync(generator: ModuleType) -> None:
    """docs/dsl-options.md must match the regenerated cheatsheet."""
    expected = generator.render_options_markdown(dsl_schema())
    on_disk = DOCS_PATH.read_text(encoding="utf-8")
    assert on_disk == expected, f"docs/dsl-options.md is {REGEN_HINT}"


def test_schema_json_valid_and_complete() -> None:
    """The committed JSON is valid, versioned, and covers .pdf and github://."""
    data = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert ".pdf" in data["processors"]
    assert "github://" in data["sources"]


def test_init_stub_in_sync(generator: ModuleType) -> None:
    """src/attachments/__init__.pyi must match the regenerated typing stub."""
    expected = generator.render_init_stub(dsl_schema())
    on_disk = STUB_PATH.read_text(encoding="utf-8")
    assert on_disk == expected, f"src/attachments/__init__.pyi is {REGEN_HINT}"


def test_init_stub_is_valid_python_and_covers_public_api() -> None:
    """The committed stub parses and declares every name in __all__.

    Re-exports use the redundant ``import name as name`` form; ``att`` is
    declared as an ``_Att`` instance (typed call signature + .options/.help).
    """
    tree = ast.parse(STUB_PATH.read_text(encoding="utf-8"))
    declared: set[str] = set()
    relative_imports: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if node.level == 1:  # package-relative re-export
                    assert alias.asname == alias.name, (
                        f"stub must re-export with 'as': {alias.name}"
                    )
                    relative_imports.add(alias.name)
                declared.add(alias.asname or alias.name)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            declared.add(node.target.id)
    missing = set(attachments.__all__) - declared
    assert not missing, f"stub misses public names: {sorted(missing)}"
    # att is declared via the _Att instance, not re-exported from .core.
    assert "att" not in relative_imports


def test_init_stub_types_every_declared_option_and_alias() -> None:
    """Every declared option and alias is a named kwarg of _Att.__call__."""
    tree = ast.parse(STUB_PATH.read_text(encoding="utf-8"))
    att_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "_Att"
    )
    call = next(
        node
        for node in att_class.body
        if isinstance(node, ast.FunctionDef) and node.name == "__call__"
    )
    kwarg_names = {arg.arg for arg in call.args.kwonlyargs}
    schema = dsl_schema()
    for section in ("processors", "sources"):
        for option_dicts in schema[section].values():
            for option in option_dicts:
                assert option["name"] in kwarg_names
                for alias in option["aliases"]:
                    assert alias in kwarg_names
    assert {"api_key", "prefer"} <= kwarg_names
