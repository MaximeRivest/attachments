#!/bin/bash
# EC2 user-data bootstrap for api.attachments.dev — Ubuntu 24.04 LTS.
#
# Paste into the EC2 "User data" field at launch (or run manually as root on
# a fresh box). Idempotent-ish: safe to re-run; each step checks before doing.
#
# DECISION POINTS are marked "==> " — read them before launching.
set -euo pipefail
exec > >(tee -a /var/log/attachments-bootstrap.log) 2>&1
echo "=== attachments bootstrap $(date -u +%FT%TZ) ==="

# --- 1. Base packages + unattended security upgrades -------------------------
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl git unattended-upgrades fail2ban
dpkg-reconfigure -f noninteractive unattended-upgrades

# --- 2. Docker Engine + compose plugin (official Docker repo) ----------------
if ! command -v docker >/dev/null 2>&1; then
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
        > /etc/apt/sources.list.d/docker.list
    apt-get update
    apt-get install -y docker-ce docker-ce-cli containerd.io \
        docker-buildx-plugin docker-compose-plugin
fi
usermod -aG docker ubuntu || true

# --- 3. Get the code ----------------------------------------------------------
# ==> DECISION: pre-publish, the repo is private and dist/*.whl is not in git.
#     Either (a) rsync the repo (including dist/) from your workstation:
#         rsync -av --exclude .venv ~/Projects/attachmentsv3/ ubuntu@<ip>:/opt/attachments/
#     or (b) git clone (post-migration, public repo) and `uv build` or scp the
#     wheel into /opt/attachments/dist/ separately.
APP_DIR=/opt/attachments
if [ ! -d "$APP_DIR/.git" ] && [ ! -f "$APP_DIR/deploy/docker-compose.yml" ]; then
    git clone https://github.com/MaximeRivest/attachments.git "$APP_DIR" \
        || echo "==> clone failed (private repo?) — rsync the tree to $APP_DIR instead"
fi

# --- 4. Environment file --------------------------------------------------------
if [ -f "$APP_DIR/deploy/free-tier.env.example" ] && [ ! -f "$APP_DIR/deploy/.env" ]; then
    cp "$APP_DIR/deploy/free-tier.env.example" "$APP_DIR/deploy/.env"
    echo "==> review $APP_DIR/deploy/.env before going live"
fi

# --- 5. First TLS certificate (run ONCE, after DNS A record resolves) ----------
# nginx can't start its TLS server block until the cert exists, so first
# issuance uses certbot standalone on port 80 — BEFORE compose is up.
# ==> DECISION: run this manually once DNS is live; it is skipped if certs exist.
DOMAIN=api.attachments.dev
if ! docker volume inspect deploy_certbot-etc >/dev/null 2>&1; then
    docker volume create deploy_certbot-etc
    docker volume create deploy_certbot-webroot
fi
if ! docker run --rm -v deploy_certbot-etc:/etc/letsencrypt certbot/certbot \
        certificates 2>/dev/null | grep -q "$DOMAIN"; then
    echo "==> issuing first certificate for $DOMAIN (requires DNS + port 80 open)"
    docker run --rm -p 80:80 \
        -v deploy_certbot-etc:/etc/letsencrypt \
        certbot/certbot certonly --standalone \
        -d "$DOMAIN" --non-interactive --agree-tos \
        -m jardindescollinesdeloutaouais@gmail.com \
        || echo "==> certbot failed (DNS not propagated yet?) — re-run this block later"
fi

# --- 6. Build + start the stack -------------------------------------------------
if [ -f "$APP_DIR/deploy/docker-compose.yml" ] && ls "$APP_DIR"/dist/attachments-*.whl >/dev/null 2>&1; then
    cd "$APP_DIR"
    docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d --build
    echo "=== stack up; smoke: curl -fsS https://$DOMAIN/health ==="
else
    echo "==> code or wheel missing — rsync the repo (with dist/) then run:"
    echo "    cd $APP_DIR && docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d --build"
fi

echo "=== bootstrap done ==="
