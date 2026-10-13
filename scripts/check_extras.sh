#!/usr/bin/env bash
# Each extra alone, in a fresh environment, against tests/extras/check.py (what CI's
# `extras` job does). Run before a release:
#   scripts/check_extras.sh                      # build this checkout, every extra
#   scripts/check_extras.sh pdf "pdf,ocr"        # some extras only
#   WHEEL='attachments==1.0.0' scripts/check_extras.sh pdf   # a published version instead
set -euo pipefail
cd "$(dirname "$0")/.."
SPECS=("$@")
[ ${#SPECS[@]} -gt 0 ] || SPECS=("" pdf image docx pptx xlsx html svg office "pdf,ocr" all-local)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
if [ -z "${WHEEL:-}" ]; then
    uv build --wheel -q -o "$WORK/dist"
    WHEEL="attachments @ file://$(ls "$WORK"/dist/*.whl)"
fi
status=0
for spec in "${SPECS[@]}"; do
    env="$WORK/env"
    rm -rf "$env"
    uv venv -q --python 3.12 "$env"
    if [ -n "$spec" ]; then
        req="${WHEEL/attachments/attachments[$spec]}"
    else
        req="$WHEEL"
    fi
    VIRTUAL_ENV="$env" uv pip install -q "$req"
    echo "=== ${spec:-bare}"
    (cd "$WORK" && "$env/bin/python" "$OLDPWD/tests/extras/check.py" "$spec") || status=1
done
exit $status
