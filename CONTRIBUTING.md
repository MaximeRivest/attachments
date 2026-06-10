Contributing to attachments
===========================

Thanks for helping! Start with [VISION.md](VISION.md) to understand where the
project is going, then [DEVELOPMENT.md](DEVELOPMENT.md) for the step-by-step
guide to adding processors (file formats) and sources (protocols/schemes) —
that's where most contributions land.

**The contributor playbook in one line:** a processor PR is one pure function
`(bytes, **options) -> Artifact` + a declared option schema
(`@processor(".myf", options=(...))`) + tests (including the missing-dep
path) — the conformance suite (`tests/test_conformance.py`) iterates the live
processor registry and picks your processor up automatically.

Quickstart (2 minutes)
----------------------

```bash
# 1) Clone and enter the repo
git clone <your-fork-or-repo-url>.git attachments
cd attachments

# 2) Create the venv and install deps (uv)
#    (Installs dev deps, including optional processor libs used by tests.)
uv sync

# 3) Sanity checks
uv run ruff format .   # format
uv run ruff check .    # lint
uv run pytest -q       # tests
```

Prerequisites
-------------
- Python 3.12+
- `uv` for dependency and environment management
- Git

Tip: If you have multiple Python versions installed, use `uv python pin 3.12`
at the repo root to align collaborators.

Daily development loop
----------------------

```bash
uv run pytest -q                 # run the test suite (with coverage)
uv run pytest tests/test_dsl.py  # run one file
uv run ruff format . && uv run ruff check .
```

Doctests run as part of the suite (`--doctest-modules` over `src/`), so keep
docstring examples accurate — they are tested documentation.

Adding/removing dependencies
----------------------------

The core package has **zero required dependencies** — this is a hard rule.
Anything a processor or source needs goes in `[project.optional-dependencies]`
in `pyproject.toml`, with a matching entry in `deps.py`'s `DEPENDENCY_MAP`.
See the checklist in [DEVELOPMENT.md](DEVELOPMENT.md). After editing
dependencies, run `uv lock` and commit `uv.lock`.

Code style and conventions
--------------------------
- `ruff format` and `ruff check` must pass (CI enforces both).
- Processors are pure functions `(bytes, **options) -> Artifact`; never raise
  for missing optional deps — return an error artifact with an install hint.
- Error messages teach: include the `pip install attachments[...]` remedy.
- No aspirational docs: nothing goes in README/docs unless it runs today.

Tests
-----
- Tests live flat in `tests/` (e.g. `tests/test_core.py`,
  `tests/test_conformance.py`).
- Every processor needs both a missing-dep test (graceful error artifact) and
  an installed-path test (skipped when the dep is absent).
- The conformance suite validates every registered processor's output against
  `spec/artifact.schema.json` automatically — add a sample-file generator for
  your extension in `tests/test_conformance.py` to opt in to content checks.

Branches, commits, and PRs
--------------------------
- Branch from `master`, keep PRs focused and small.
- CI (lint + tests) must be green.
- Describe *what changed and why*; link the VISION.md epic if applicable.
