# Launch checklist — attachments 1.0

This repo (`github.com/maximerivest/attachments`, branch `main`) is 1.0.
The 0.25 code lives on the `legacy-0.25` branch and its `v0.25.x` tags.

## Where we are

| | |
|---|---|
| PyPI | `1.0.0b2` (beta) is the 1.0 pre-release; plain `pip install attachments` still gets 0.25.1 |
| Hosted service | `api.attachments.dev` live, redeployed 2026-10-09 (see `deploy/DEPLOYED.md`, not in git) |
| Domain | `attachments.dev` is owned and serves the shipped default `service_url` |

## How to publish any version

Publishing is done by GitHub, never from a laptop:
`.github/workflows/publish-to-pypi.yml` runs on every pushed `v*` tag. It
runs the full test suite on the tagged commit, builds once, installs the
built files into clean environments to check them, uploads them to PyPI
through trusted publishing (no token stored anywhere; files are signed),
then creates the GitHub release from the changelog. "Run workflow" on the
Actions page does everything except the upload: a dry run.

1. Set the version in **both** `pyproject.toml` and
   `src/attachments/__init__.py` (`tests/test_version.py` fails if they
   differ).
2. Pre-release (`aN`, `bN`, `rcN`): Development Status `4 - Beta`.
   Final: `5 - Production/Stable`. The same test enforces this.
3. Move the `## [Unreleased]` notes under `## [X.Y.Z] - YYYY-MM-DD` in
   CHANGELOG.md. The release fails without that section; it becomes the
   GitHub release text.
4. Commit, push `main`, wait for CI to pass.
5. `git tag vX.Y.Z && git push origin vX.Y.Z`. Watch the run on GitHub.
6. Check from a clean machine:

   ```bash
   cd "$(mktemp -d)" && uv venv -q && . .venv/bin/activate
   uv pip install "attachments[pdf]==X.Y.Z"
   python -c "import attachments; print(attachments.__version__)"
   att --help | head -3
   ```

A version on PyPI can never be replaced, only yanked. If a release is
broken, fix it and publish the next number.

PyPI trusts the workflow by its file name. Renaming
`publish-to-pypi.yml` breaks publishing until the trusted publisher is
updated at pypi.org → attachments → Publishing.

## Before 1.0.0

- [ ] Scanned PDFs fit Claude's 32 MB request limit by default (JPEG for
      pages with no text) and `.claude()` / `.openai()` warn, with the fix,
      when a request is over a provider's limit.
- [ ] Automatic OCR: pages in parallel, progress shown, time cap; fix the
      missing spaces seen on the server ("Scanned page1line2lorem…").
- [ ] Mistyped options show in the result summary, and the hint suggests
      the real option name (`pages`, not the alias `page`).
- [ ] Photos: strip GPS and other camera data unless asked.
- [ ] Refresh the demo notebook, ANNOUNCEMENT.md and the demo GIF
      (`vhs scripts/demo.tape`) with folders, web pages, slide pictures,
      `from_prompt` and page lists.
- [ ] CI: recheck the LibreOffice install on GitHub's Ubuntu 26 runners
      (switch on 2026-10-19); weekly run against the newest libraries.

## Releasing 1.0.0

On top of "How to publish":

- [ ] Development Status `5 - Production/Stable`.
- [ ] Remove `>=1.0.0b1` from the install commands in README.md,
      `src/attachments/skill/SKILL.md` and docs/MIGRATION.md, and the
      sentences saying plain `pip install attachments` gets 0.25.
- [ ] Pin an issue: "Migrating from 0.25? Read docs/MIGRATION.md".

## Announce

Source text: [ANNOUNCEMENT.md](ANNOUNCEMENT.md).

- [ ] GitHub release for `v1.0.0` (the workflow creates it; add the GIF)
- [ ] Hacker News — Show HN: "attachments 1.0 – turn anything into
      LLM-ready text+images in one function" (link to repo)
- [ ] r/Python, r/LocalLLaMA, r/LangChain
- [ ] X/Twitter + LinkedIn thread (lead with the GIF)
- [ ] Python Discord #show-and-tell, PyCoder's Weekly submission

## Day 2

- Watch PyPI install errors and GitHub issues for the first 48 hours.
- 0.25 is maintenance-only on `legacy-0.25`: fix breakage, add nothing.
- The hosted service: [deploy/RUNBOOK.md](deploy/RUNBOOK.md); the outside
  monitor (`.github/workflows/monitor.yml`) emails on downtime or a
  certificate under 21 days. GitHub pauses scheduled workflows after 60
  days without repo activity.
