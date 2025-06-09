#!/bin/bash
set -e

echo "Generating DSL cheatsheet..."
python scripts/generate_dsl_cheatsheet.py

echo "Building documentation..."
myst build

echo "Finding and copying the cheatsheet..."
# The file is usually named index.html inside a directory named after the source file.
CHEATSHEET_HTML=$(find _build -path "*/dsl-cheatsheet/index.html" -print -quit)

if [ -z "$CHEATSHEET_HTML" ]; then
    echo "Error: Could not find the generated cheatsheet HTML file."
    exit 1
fi

cp "$CHEATSHEET_HTML" docs/dsl_cheatsheet.html

echo "Cheatsheet copied to docs/dsl_cheatsheet.html"
echo "You can now inspect this file." 