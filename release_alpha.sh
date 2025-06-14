#!/bin/bash
set -e

echo "🚀 Releasing Alpha Version 0.16.0a1"
echo "====================================="

# Ensure we have the latest DSL cheatsheet
echo "📋 Generating latest DSL cheatsheet..."
python scripts/generate_dsl_cheatsheet.py

# Commit any final changes
echo "💾 Committing final changes..."
git add .
git commit -m "feat: Magical auto_attach function v0.16.0a1

- Automatically detects files and URLs in prompts
- Supports DSL commands in square brackets
- Handles multiple root directories including URLs
- Combines original prompt with extracted content
- Ready-to-use with any adapter (.openai_responses(), .claude(), etc.)" || echo "No changes to commit"

# Tag the release
echo "🏷️  Creating alpha release tag..."
git tag -a v0.16.0a1 -m "Alpha release v0.16.0a1: Magical auto_attach function"

# Push to GitHub
echo "⬆️  Pushing to GitHub..."
git push origin main
git push origin v0.16.0a1

echo "✅ Alpha release v0.16.0a1 pushed to GitHub!"
echo ""
echo "🤖 GitHub Actions will now automatically:"
echo "   1. Build the package"
echo "   2. Publish to PyPI as pre-release"
echo "   3. Create GitHub release with notes"
echo ""
echo "📋 Once published, alpha testers can install with:"
echo "   pip install attachments==0.16.0a1"
echo "   # or"
echo "   pip install --pre attachments"
echo ""
echo "🛡️  Regular users still get stable version:"
echo "   pip install attachments  # Gets 0.15.0" 