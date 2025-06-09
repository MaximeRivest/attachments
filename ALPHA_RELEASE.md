# Alpha Release Strategy for Attachments

## 🎯 Objective
Release new features for alpha testing without affecting stable users who run `pip install attachments`.

## 📦 Version Strategy

### Current Setup
- **Stable version**: `0.12.0` (current PyPI stable)
- **Alpha version**: `0.13.0a1` (new features with enhanced DSL)
- **Next alpha**: `0.13.0a2`, `0.13.0a3`, etc.
- **Next stable**: `0.13.0` (when alpha testing is complete)

### Version Semantics
```
0.13.0a1 = version 0.13.0, alpha release 1
0.13.0a2 = version 0.13.0, alpha release 2  
0.13.0   = version 0.13.0, stable release
```

## 🚀 Release Process

### 1. For Alpha Releases

**Update version:**
```bash
# In pyproject.toml
version = "0.13.0a1"  # or a2, a3, etc.
```

**Push tag to trigger GitHub Actions:**
```bash
# Create and push tag
git tag -a v0.13.0a1 -m "Alpha release v0.13.0a1: Enhanced DSL cheatsheet system"
git push origin v0.13.0a1

# GitHub Actions automatically:
# 1. Builds the package
# 2. Publishes to PyPI (marked as pre-release)
# 3. Creates GitHub release
```

**Install for testers:**
```bash
# Explicit alpha version
pip install attachments==0.13.0a1

# Or get latest pre-release
pip install --pre attachments
```

### 2. For Stable Release

**Update version:**
```bash
# In pyproject.toml  
version = "0.13.0"  # Remove 'a1' suffix
```

**Push tag to trigger GitHub Actions:**
```bash
# Create and push tag  
git tag -a v0.13.0 -m "Stable release v0.13.0: Enhanced DSL cheatsheet system"
git push origin v0.13.0

# GitHub Actions automatically:
# 1. Builds the package
# 2. Publishes to PyPI (marked as stable)
# 3. Creates GitHub release
```

**Regular users get it:**
```bash
pip install attachments  # Gets 0.13.0 (stable)
```

## 📋 What Each User Type Gets

| User Type | Command | Gets Version | Notes |
|-----------|---------|--------------|-------|
| **Regular users** | `pip install attachments` | `0.12.0` (stable) | Safe, tested version |
| **Alpha testers** | `pip install attachments==0.13.0a1` | `0.13.0a1` (alpha) | Latest features |
| **Pre-release enthusiasts** | `pip install --pre attachments` | `0.13.0a1` (latest pre) | Always latest alpha |

## 🔄 Iteration Process

1. **Release alpha**: `0.13.0a1`
2. **Get feedback** from alpha testers  
3. **Fix issues** and release `0.13.0a2`
4. **Repeat** until ready for stable
5. **Release stable**: `0.13.0`
6. **Start next cycle**: `0.14.0a1`

## 🧪 What's New in Alpha 0.13.0a1

### Enhanced DSL Cheatsheet System
- **Type information**: Shows expected data types (int, string, boolean)
- **Default values**: Shows what happens when commands aren't specified  
- **Allowable values**: Lists valid options for restricted commands
- **Auto-generated**: Updates automatically from source code analysis
- **Rich documentation**: Better descriptions and context

### Improved Development Experience
- **AST-based discovery**: Finds DSL commands by analyzing code structure
- **Smart suggestions**: "Did you mean" suggestions for typos
- **Better logging**: Enhanced verbosity system with hierarchical output
- **Auto-updating docs**: Documentation rebuilds automatically

### Examples of Enhanced Information
```python
# Before: Just knew 'characters' command existed
# After: Know it expects int, defaults to 1000, used in splitter

# Before: Guessed at 'format' options  
# After: See exact list: plain, text, txt, markdown, md, html, code, xml, csv, structured
```

## 📝 Communication Strategy

### For Alpha Testers
- Clear installation instructions
- List of new features
- Known issues and limitations
- Feedback channels (GitHub issues)

### For Regular Users  
- No changes to their workflow
- `pip install attachments` still gets stable version
- Optional mention of alpha program in docs

## 🛡️ Safety Measures

1. **Pre-release tags**: Alpha versions are marked as pre-release on PyPI
2. **Explicit opt-in**: Users must explicitly request alpha versions
3. **Stable fallback**: Regular install command unchanged
4. **Clear labeling**: Version numbers clearly indicate alpha status
5. **Documentation**: Clear warnings about alpha stability

## 🎯 Success Metrics

- Alpha testers can install and use new features
- Regular users unaffected  
- Feedback collection from alpha users
- Issues identified and resolved before stable release
- Smooth transition from alpha to stable

---

**Ready to release alpha 0.13.0a1 with enhanced DSL cheatsheet system! 🚀** 