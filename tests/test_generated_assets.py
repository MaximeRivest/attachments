"""
Sync tests for the generated DSL assets.

=============================================================================
TEST GUIDELINES FOR GENERATED ASSETS
=============================================================================

GOOD tests:
    - spec/dsl-schema.json on disk == the live dsl_schema() serialization
      (CI fails when option declarations change without regenerating)
    - docs/dsl-options.md on disk == the regenerated cheatsheet
    - Basic shape of the committed JSON (version, .pdf, github://)

BAD tests:
    - Testing dsl_schema() internals (test_options.py)
    - Re-testing markdown rendering details beyond byte-for-byte sync

The generator lives outside the package (scripts/gen_dsl_assets.py), so it
is imported here via importlib.util.spec_from_file_location — no sys.path
manipulation, and pytest can run this from the repo root.

=============================================================================
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

from attachments import dsl_schema

REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = REPO_ROOT / "scripts" / "gen_dsl_assets.py"
SCHEMA_PATH = REPO_ROOT / "spec" / "dsl-schema.json"
DOCS_PATH = REPO_ROOT / "docs" / "dsl-options.md"

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
