#!/usr/bin/env bash
# Put a published attachments version live on lambda (api.attachments.dev).
#
#   deploy/lambda/release.sh 1.0.0b8      # build, switch, check; rolls back if the check fails
#   deploy/lambda/release.sh --rollback   # back to the previous release
#   deploy/lambda/release.sh --status
#
# The service (attachments-api, ~/Projects/os/machines/hosts/lambda/attachments-api.nix) runs
# gunicorn inside the file tree of deploy/Dockerfile's image, unpacked under
# /var/lib/attachments-api/releases/<version>/rootfs, with systemd's sandbox around it: no
# container network, and the kernel refuses every private address (see the .nix file). This
# script builds that image from the PyPI wheel (checksum checked against PyPI), unpacks it,
# points /var/lib/attachments-api/current at it and restarts the service. Two releases are kept.
set -euo pipefail

STATE=/var/lib/attachments-api
REPO=$(cd "$(dirname "$0")/../.." && pwd)
KEEP=2

die() { echo "release: $*" >&2; exit 1; }

health() {
    # Through nginx (the same path the relay uses), then the version it reports.
    local want=$1 body
    for _ in $(seq 1 60); do
        if body=$(curl -fsS -m 5 -H 'Host: api.attachments.dev' http://127.0.0.1:8820/health 2>/dev/null); then
            if [ -z "$want" ] || python3 -c 'import json,sys; v=json.loads(sys.argv[1])["version"]; sys.exit(v!=sys.argv[2])' "$body" "$want"; then
                echo "$body"; return 0
            fi
        fi
        sleep 3
    done
    return 1
}

switch_to() {
    sudo -n ln -sfn "releases/$1" "$STATE/current.new"
    sudo -n mv -T "$STATE/current.new" "$STATE/current"
    sudo -n systemctl restart attachments-api
}

case "${1:-}" in
--status)
    readlink "$STATE/current" || echo "no release yet"
    ls "$STATE/releases" 2>/dev/null
    systemctl --no-pager --lines=0 status attachments-api | head -5
    exit 0 ;;
--rollback)
    cur=$(basename "$(readlink "$STATE/current")")
    # shellcheck disable=SC2010  # release names are version numbers
    prev=$(ls -1t "$STATE/releases" | grep -vx "$cur" | head -1)
    [ -n "$prev" ] || die "no earlier release to go back to"
    echo "rolling back $cur -> $prev"
    switch_to "$prev"
    health "" && echo "back on $prev"
    exit 0 ;;
""|-*) sed -n 2,7p "$0"; exit 2 ;;
esac

VERSION=$1
DEST=$STATE/releases/$VERSION
[ -e "$DEST" ] && die "$DEST exists already (remove it first to rebuild)"
id attachments-api >/dev/null 2>&1 || die "user attachments-api missing: rebuild lambda with attachments-api.nix first"

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/dist" "$WORK/deploy"
cp "$REPO/deploy/Dockerfile" "$REPO/deploy/warmup.py" "$REPO/deploy/wsgi.py" "$WORK/deploy/"

# The wheel exactly as PyPI publishes it.
read -r url sha < <(curl -fsS "https://pypi.org/pypi/attachments/$VERSION/json" | python3 -c '
import json, sys
for u in json.load(sys.stdin)["urls"]:
    if u["filename"].endswith(".whl"):
        print(u["url"], u["digests"]["sha256"])')
[ -n "${url:-}" ] || die "no wheel for $VERSION on PyPI"
curl -fsSL -o "$WORK/dist/${url##*/}" "$url"
echo "$sha  $WORK/dist/${url##*/}" | sha256sum -c --quiet || die "wheel checksum differs from PyPI's"

IMAGE=localhost/attachments-api:$VERSION
echo "building $IMAGE (the build runs the strict warm-up: OCR, LibreOffice)"
podman build -q -f "$WORK/deploy/Dockerfile" -t "$IMAGE" "$WORK" >/dev/null

# Unpack the image's files. Owned by root and mounted read-only by the service; its home
# (LibreOffice's profile) is a separate writable folder bound over /home/attachments.
cid=$(podman create "$IMAGE")
sudo -n mkdir -p "$DEST/rootfs"
podman export "$cid" | sudo -n tar -x -C "$DEST/rootfs" --numeric-owner
podman rm -f "$cid" >/dev/null
sudo -n chown -R root:root "$DEST/rootfs/app" "$DEST/rootfs/home/attachments"
# A name for the service's user inside the tree (LibreOffice asks for one).
uid=$(id -u attachments-api); gid=$(id -g attachments-api)
echo "attachments-api:x:$uid:$gid::/home/attachments:/usr/sbin/nologin" | sudo -n tee -a "$DEST/rootfs/etc/passwd" >/dev/null
echo "attachments-api:x:$gid:" | sudo -n tee -a "$DEST/rootfs/etc/group" >/dev/null
echo "$VERSION $sha $(date -u +%FT%TZ)" | sudo -n tee "$DEST/RELEASE" >/dev/null

prev=$(basename "$(readlink "$STATE/current" 2>/dev/null)" 2>/dev/null || true)
echo "switching ${prev:-nothing} -> $VERSION"
switch_to "$VERSION"
if ! health "$VERSION"; then
    echo "release: $VERSION failed its health check" >&2
    sudo -n journalctl -u attachments-api -n 30 --no-pager >&2 || true
    if [ -n "$prev" ] && [ -e "$STATE/releases/$prev" ]; then
        switch_to "$prev"; health "" >/dev/null && echo "rolled back to $prev" >&2
    fi
    exit 1
fi
echo "live: $VERSION"

# Keep the newest $KEEP releases (the live one always stays).
# shellcheck disable=SC2010  # release names are version numbers
ls -1t "$STATE/releases" | grep -vx "$VERSION" | tail -n +"$KEEP" | while read -r old; do
    sudo -n rm -rf "${STATE:?}/releases/$old"; echo "removed release $old"
done
podman image prune -f >/dev/null || true
