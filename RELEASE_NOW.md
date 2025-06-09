# 🚀 Ready to Release Alpha 0.13.0a1

## What's Set Up ✅

1. **Version updated** to `0.13.0a1` in `pyproject.toml`
2. **GitHub Actions workflows** created for automatic publishing
3. **Release script** ready to tag and push
4. **Documentation** updated with alpha installation instructions

## To Release Alpha Right Now 🎯

**Option 1: Use the script**
```bash
./release_alpha.sh
```

**Option 2: Manual commands**
```bash
# Generate latest DSL cheatsheet
python scripts/generate_dsl_cheatsheet.py

# Commit and tag
git add .
git commit -m "feat: Enhanced DSL cheatsheet system v0.13.0a1"
git tag -a v0.13.0a1 -m "Alpha release v0.13.0a1: Enhanced DSL cheatsheet system"

# Push (this triggers GitHub Actions)
git push origin main
git push origin v0.13.0a1
```

## What Happens Next 🤖

1. **GitHub Actions triggers** on the `v0.13.0a1` tag
2. **Builds package** automatically
3. **Publishes to PyPI** as pre-release
4. **Creates GitHub release** with installation instructions

## Alpha Testers Get It With 📦

```bash
# Explicit version
pip install attachments==0.13.0a1

# Latest pre-release
pip install --pre attachments
```

## Regular Users Unaffected 🛡️

```bash
# Still gets stable 0.12.0
pip install attachments
```

---

**Ready when you are! 🚀** 