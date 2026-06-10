# Launch checklist — attachments 1.0.0

Working tree: this repo (`attachmentsv3`, remote
`github.com/MaximeRivest/attachmentsv3`). It replaces the content of the
published repo `github.com/MaximeRivest/attachments` (currently 0.25.x).
**Nothing below publishes anything until you run it.**

## 0. Final gate (5 min)

```bash
uv run pytest -q                      # must be green (927 tests as of this checklist)
uvx ruff check src tests scripts
git status                            # commit everything before tagging
```

## 1. Record the demo GIF

```bash
# Install vhs: brew install vhs   (or: go install github.com/charmbracelet/vhs@latest;
# Linux release binaries need ttyd + ffmpeg on PATH)
vhs scripts/demo.tape                 # writes demo.gif (~75s) in the repo root
```

Watch `demo.gif` once. If pacing is off, tune `DEMO_PAUSE` inside
`scripts/demo.py` or the `Sleep` in `scripts/demo.tape` and re-record.
Optionally embed it at the top of README.

## 2. Repo migration (attachmentsv3 → attachments)

Goal: this history becomes the content of `MaximeRivest/attachments`,
with the 0.25.x history preserved.

**➤ DECISION 1 — preserve v1 as a branch (recommended) or rely on tags only.**

Recommended flow (preserves v1 on a `v1-maintenance` branch, replaces
`main`/`master` with this tree's history):

```bash
# In the OLD repo clone (~/Projects/attachments):
cd ~/Projects/attachments
git switch master                # or main — whatever the default branch is
git tag v0.25.3-final            # belt and suspenders
git branch v1-maintenance
git push origin v1-maintenance v0.25.3-final

# In THIS repo:
cd ~/Projects/attachmentsv3
git remote add public https://github.com/MaximeRivest/attachments.git
git push public master --force   # replaces the default branch with 1.0 history
git push public --tags
```

Notes:
- `--force` rewrites the default branch of the public repo. The old history
  is still reachable via `v1-maintenance` and the tag. Open PRs against the
  old tree will go stale — close them with a pointer to MIGRATION.md.
- **➤ DECISION 2:** alternatively, merge histories
  (`git merge --allow-unrelated-histories -s ours v1`) to keep one linear
  repo — messier log, no force-push. Force-replace is cleaner; the branch
  preserves everything that matters.
- Update the repo description + topics on GitHub; point the default branch
  protection rules at the new tree.
- Archive or add a README pointer to `attachmentsv3` afterwards so people
  land on the canonical repo.

## 3. Publish to PyPI

**➤ DECISION 3 — pre-release first?** VISION.md suggested `1.0.0aN`; pip
ignores pre-releases by default so it's zero-risk. If you want one:
bump version to `1.0.0a1`, build, publish, smoke, then do 1.0.0.

```bash
cd ~/Projects/attachmentsv3
rm -rf dist && uv build              # fresh sdist + wheel (dist/ has stale ones)
uv publish                           # prompts for PyPI token (or set UV_PUBLISH_TOKEN)
# twine equivalent: uvx twine upload dist/*
git tag v1.0.0 && git push public v1.0.0
```

## 4. Post-publish smoke (fresh venv, ~3 min)

```bash
cd "$(mktemp -d)"
uv venv && source .venv/bin/activate
pip install attachments==1.0.0
python -c "from attachments import att; print(att('https://raw.githubusercontent.com/MaximeRivest/attachments/master/README.md'))" | head
pip install "attachments[pdf]"
python -c "from attachments import check_deps; print(check_deps())"
att --options | head
```

Also verify the PyPI page renders README correctly (links are relative —
GitHub URLs resolve once step 2 is done).

## 5. Announce

Source text: [ANNOUNCEMENT.md](ANNOUNCEMENT.md) (HN/Reddit/blog ready).

- [ ] GitHub release for `v1.0.0` (paste ANNOUNCEMENT.md, attach demo.gif)
- [ ] Hacker News — Show HN: "attachments 1.0 – turn anything into
      LLM-ready text+images in one function" (link to repo)
- [ ] r/Python, r/LocalLLaMA, r/LangChain
- [ ] X/Twitter + LinkedIn thread (lead with the GIF)
- [ ] Python Discord #show-and-tell, PyCoder's Weekly submission
- [ ] Pin an issue: "Migrating from 0.25.x? Read docs/MIGRATION.md"

## 6. Day-2

- Watch PyPI install errors / GitHub issues for the first 48h.
- 0.25.x stays maintenance-only on the `v1-maintenance` branch; backport
  nothing, fix only breakage.

## 7. BLOCKER before `uv publish` — the service_url default

`attachments.config` defaults `service_url` to `https://api.attachments.dev/v1`.
**Decision required (Maxime):**

- **If you buy `attachments.dev`** (premium-priced .dev — compare Cloudflare
  Registrar/Porkbun against GoDaddy before paying): keep the default, and
  park the domain with an HTTPS placeholder immediately so the name can never
  be squatted while pointing at our shipped default.
- **If you don't buy it**: change the default to `None` before publishing and
  make service mode require an explicit `configure(service_url=...)`. Shipping
  a default URL on an unowned domain means whoever registers it later receives
  users' files and API keys.

Either path is a 10-minute change + test update; do NOT publish without
resolving this line.
