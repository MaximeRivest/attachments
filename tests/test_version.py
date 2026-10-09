"""The version is written in two places; a release must not ship them apart."""

import tomllib
from pathlib import Path

import attachments

ROOT = Path(__file__).resolve().parent.parent


def test_dunder_version_matches_pyproject():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    assert attachments.__version__ == project["version"]


def test_development_status_matches_version():
    """A pre-release (a/b/rc) must not call itself Production/Stable."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    is_pre = any(tag in project["version"] for tag in ("a", "b", "rc"))
    stable = "Development Status :: 5 - Production/Stable" in project["classifiers"]
    assert stable != is_pre
