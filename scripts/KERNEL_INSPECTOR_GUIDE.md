# Kernel Inspector - Quick Guide

## What It Does
Connects to your running Jupyter kernel to inspect variables, history, and debug issues.

## Basic Usage

```bash
# Quick inspection (most common)
uv run python docs/scripts/kernel_inspector.py

# Show help
uv run python docs/scripts/kernel_inspector.py --help
```

## Common Scenarios

### 🔍 **Debug a specific variable**
```bash
# See what 'agent' contains
uv run python docs/scripts/kernel_inspector.py --var agent

# Check 'response' object
uv run python docs/scripts/kernel_inspector.py --var response
```

### 📜 **See more history**
```bash
# Show last 10 inputs/outputs instead of 4
uv run python docs/scripts/kernel_inspector.py --history 10
```

### ❌ **Find errors**
```bash
# Look for recent errors/exceptions
uv run python docs/scripts/kernel_inspector.py --errors-only
```

### 🧪 **Test something quickly**
```bash
# Execute code in the kernel
uv run python docs/scripts/kernel_inspector.py --exec "print(type(agent))"
uv run python docs/scripts/kernel_inspector.py --exec "len(In)"
uv run python docs/scripts/kernel_inspector.py --exec "list(agent.__dict__.keys())"
```

### 🔧 **Multiple kernels**
```bash
# List all available kernels
uv run python docs/scripts/kernel_inspector.py --list-kernels

# Use older kernel (index 1 instead of 0)
uv run python docs/scripts/kernel_inspector.py --kernel-index 1
```

## Quick Reference

| Flag | Short | Purpose | Example |
|------|-------|---------|---------|
| `--var` | `-v` | Inspect specific variable | `-v agent` |
| `--history` | `-h` | Number of In/Out entries | `-h 10` |
| `--errors-only` | `-e` | Show only errors | `-e` |
| `--exec` | `-x` | Execute custom code | `-x "print(type(a))"` |
| `--list-kernels` | `-l` | List available kernels | `-l` |
| `--kernel-index` | `-k` | Use specific kernel | `-k 1` |

## Pro Tips

1. **Start with basic inspection** - just run without flags first
2. **Use `--var` for deep dives** - when you need to understand a specific object
3. **Use `--exec` for quick tests** - faster than switching to Jupyter
4. **Check `--errors-only` when debugging** - finds problems quickly
5. **Clean up old kernels** - `find ~/.local/share/jupyter/runtime/ -name "kernel-*.json" -mtime +1 -delete`

## Example Workflow

```bash
# 1. Basic inspection to see what's happening
uv run python docs/scripts/kernel_inspector.py

# 2. Found 'agent' variable, inspect it
uv run python docs/scripts/kernel_inspector.py --var agent

# 3. Test something quickly
uv run python docs/scripts/kernel_inspector.py --exec "agent.run('test')"

# 4. Look for errors if something failed
uv run python docs/scripts/kernel_inspector.py --errors-only
```

This gives you complete visibility into the user's Jupyter session for effective debugging! 