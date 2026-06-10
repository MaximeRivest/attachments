# api.attachments.dev — launch-day runbook

> **Untested build notice:** docker was not available where this kit was
> authored. Before anything else, validate the image builds, from the repo
> root:
>
> ```bash
> uv build && docker build -f deploy/Dockerfile -t attachments-api .
> ```

Architecture: one raw EC2 CPU instance runs the whole free tier (nginx TLS →
gunicorn `attachments.server:create_app`, everything preinstalled and
RAM-warm via `deploy/warmup.py` + `--preload`). Nothing stateful by design —
no DB, no uploads kept; backups are unnecessary. Phase 2 adds a separate GPU
instance for LightOnOCR.

## 1. EC2 sizing

Prices are **approximate us-east-1 on-demand, check current** at
https://aws.amazon.com/ec2/pricing/on-demand/.

| Instance   | vCPU / RAM   | Role                         | ~$/mo (on-demand) | Notes |
|------------|--------------|------------------------------|-------------------|-------|
| c7a.large  | 2 / 4 GiB    | Free tier launch pick        | ~$75              | `WEB_CONCURRENCY=2`; tight but fine for launch traffic |
| c7g.large  | 2 / 4 GiB    | Cheaper ARM alternative      | ~$53              | Graviton; all deps ship aarch64 wheels — verify the docker build on arm64 first |
| c7a.xlarge | 4 / 8 GiB    | If launch traffic spikes     | ~$150             | `WEB_CONCURRENCY=4`, `API_MEM_LIMIT=6g` |
| g6.xlarge  | 4 / 16 GiB + L4 24 GB | GPU phase 2 (vLLM + LightOnOCR-2-1B) | ~$580 on-demand / spot often ~60-70% less | Run only while needed; spot is fine (stateless) |

Disk: 30 GB gp3 is plenty (image + models + logs).

## 2. DNS

1. Buy/confirm `attachments.dev` (see LAUNCH.md §7 — this is the publish
   blocker; the client default is `https://api.attachments.dev/v1`).
2. A record: `api.attachments.dev` → the instance's Elastic IP
   (allocate an Elastic IP first so the address survives stop/start).
3. Wait for propagation: `dig +short api.attachments.dev` returns the IP.

## 3. Security group

- Inbound: **80/tcp and 443/tcp from 0.0.0.0/0 only.**
- SSH: 22/tcp from your IP only (or use SSM Session Manager and open nothing).
- GPU phase 2: on the GPU instance's SG, allow 8100/tcp **only from the CPU
  instance's security group** — never from the internet.

## 4. Launch sequence

```bash
# 0. Locally: build the wheel the image installs
cd ~/Projects/attachmentsv3 && uv build

# 1. Launch Ubuntu 24.04 instance (c7a.large, 30GB gp3, Elastic IP, SG above)
#    with deploy/ec2-user-data.sh as user data. It installs docker, fail2ban,
#    unattended-upgrades, and tries clone + certbot + compose up.

# 2. Pre-publish the repo is private, so ship the tree (incl. dist/) yourself:
rsync -av --exclude .venv --exclude .git ~/Projects/attachmentsv3/ \
    ubuntu@api.attachments.dev:/tmp/attachments/
ssh ubuntu@api.attachments.dev 'sudo rsync -a /tmp/attachments/ /opt/attachments/'

# 3. On the box: env file, first cert (needs DNS live), bring up the stack
ssh ubuntu@api.attachments.dev
sudo cp /opt/attachments/deploy/free-tier.env.example /opt/attachments/deploy/.env
sudo bash /opt/attachments/deploy/ec2-user-data.sh   # re-run: idempotent-ish;
                                                     # issues cert + compose up
# (or manually:)
cd /opt/attachments
sudo docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d --build

# 4. Smoke (section 5)
```

## 5. Smoke tests

```bash
# Health (expects status ok + features incl. pdf, ocr, audio)
curl -fsS https://api.attachments.dev/health | python3 -m json.tool

# POST a PDF via curl
curl -fsS -X POST https://api.attachments.dev/process \
  -F "file=@some.pdf" -F "pages=1-2" | python3 -m json.tool | head -30

# Python client path (what users actually do)
python3 - <<'EOF'
from attachments import att, configure
configure(service_url="https://api.attachments.dev", prefer="service-only")
a = att("some.pdf")
print(a[0]["meta"]["via"], a[0]["text"][:200])
EOF

# Limits behave: an oversized body gets 413 from nginx, rapid POSTs get 429
# Warm check: the FIRST /process with ocr should NOT pay model-load time
docker compose -f deploy/docker-compose.yml logs api | grep warmup
```

> Note: the shipped client default is `https://api.attachments.dev/v1`; if
> the server mounts routes at `/` (no `/v1` prefix), either pass
> `service_url="https://api.attachments.dev"` explicitly or add a `/v1`
> location alias in nginx. Verify which one is true on launch day.

## 6. Ops

- **Logs:** `docker compose -f deploy/docker-compose.yml logs -f api nginx`
  (json-file, rotated at 50 MB x3). nginx access log includes
  `rt=`/`urt=` upstream timing for spotting slow OCR requests.
- **Update flow:** `rsync` new tree (or `git pull` post-publish) →
  `uv build` → `docker compose ... up -d --build`. Post-PyPI: switch the
  Dockerfile to the commented `pip install attachments[server]==X.Y.Z` line
  and updates become a one-line version bump.
- **fail2ban:** installed by user-data with defaults (sshd jail). Optional:
  add an nginx jail keyed on repeated 429s.
- **unattended-upgrades:** enabled by user-data; reboot occasionally for
  kernel updates (stack restarts via `restart: unless-stopped`).
- **Backups:** nothing stateful by design. The only persistent data is the
  Let's Encrypt volume, which is re-issuable in minutes. No backups needed.

## 7. GPU phase 2 — LightOnOCR

1. Launch g6.xlarge (Ubuntu 24.04, NVIDIA driver + nvidia-container-toolkit;
   the AWS "Deep Learning Base GPU AMI" has both). Spot is acceptable —
   stateless; on interruption the api falls back per the server's
   `ocr_engine=lighton` error handling (verify behavior with the team adding
   that code).
2. On the GPU box, run the vllm block from `deploy/docker-compose.yml`
   (uncomment it into a standalone compose file there): vLLM OpenAI server,
   `--model lightonai/LightOnOCR-2-1B`, port 8100.
3. Security group: 8100 reachable only from the CPU instance's SG.
4. On the CPU box: set `ATTACHMENTS_LIGHTON_URL=http://<gpu-private-ip>:8100/v1`
   in `deploy/.env`, uncomment the env line in compose, `up -d`.
5. Smoke: `curl http://<gpu-private-ip>:8100/v1/models` from the CPU box,
   then a `/process` request with `ocr_engine=lighton` and compare output
   against the rapidocr path.
6. Cost control: stop the GPU instance whenever it isn't needed; the CPU
   tier keeps working on rapidocr.

## 8. Cost control

- CloudWatch **billing alarm** (us-east-1, "EstimatedCharges") at e.g. $100
  and $200/mo with email/SNS — set this BEFORE launch.
- Elastic IP: free while attached; charged when idle/detached.
- Spot for GPU only (interruption = degraded OCR, not an outage). Keep the
  CPU instance on-demand: it IS the service.
- Egress: responses are JSON (base64 images can be large); watch the data
  transfer line in the first bill.

## 9. Abuse playbook

1. Identify: `docker compose ... logs nginx | grep -v ' 200 '` and the
   `rt=` field; top talkers:
   `awk '{print $1}' access.log | sort | uniq -c | sort -rn | head`.
2. Block an IP: add `deny <ip>;` inside the server block in
   `deploy/nginx.conf`, then `docker compose ... exec nginx nginx -s reload`.
3. Tighten globally: drop the `heavy` zone to `5r/m`, lower `burst`,
   lower `client_max_body_size`; reload nginx.
4. Escalate: set `ATTACHMENTS_SERVER_KEY` in `deploy/.env` (switches the free
   tier to shared-beta-key mode — POSTs without the key get 401), publish the
   key in the docs, `docker compose ... up -d` to apply.
5. Nuclear: security group → remove 0.0.0.0/0 on 443 while you investigate.

## Post-deploy corrections (2026-06-10, first production deploy)

Applied to this kit after the first real deployment of api.attachments.dev:
- ca-central-1 has no c7a.large — use **m6i.large** (8 GiB suits warm-in-RAM).
- nginx: `/v1/process` and `/v1/unpack` are in the **heavy** rate zone
  (the server accepts /v1-prefixed routes; without this the limit could be
  bypassed via the prefix).
- user-data no longer falls back to git clone (would fetch the old public
  0.25.x repo until the migration) — rsync is the only code path.
- certbot account email is set via `certbot update_account -m <email>` if the
  boot-time registration used a placeholder.
- Library ≥ this commit supports **keyless servers**: clients need only
  `configure(service_url=...)`; no dummy api_key workaround.

## 7. Landing page (attachments.dev)

The same box serves the static landing page from `site/` (mounted read-only
into the nginx container at `/var/www/site` — see docker-compose.yml).

- **Update flow:** edit `site/index.html` locally, then
  `rsync -az -e "ssh -i ~/.ssh/attachments-deploy.pem" site ubuntu@<EIP>:/tmp/stage/ && ssh ... 'sudo rsync -a /tmp/stage/site /opt/attachments/'`
  No reload needed (static files are read per-request).
- **DNS layout (GoDaddy):** `A @ -> <EIP>`, `A api -> <EIP>`, `CNAME www -> @`
  (GoDaddy pre-creates the www CNAME; do NOT try to PUT an A record named www —
  it 400s against the existing CNAME, and the CNAME is correct).
- **DNS via API:** `curl -X PUT "https://api.godaddy.com/v1/domains/attachments.dev/records/A/<name>" -H "Authorization: sso-key $GODADDY_API_KEY:$GODADDY_API_SECRET" -H "Content-Type: application/json" -d '[{"data":"<IP>","ttl":600}]'`
- **Certificate covers all three names** (api, apex, www) in ONE lineage
  (`--cert-name api.attachments.dev`); the renew loop renews them together.

### ⚠ certbot one-off commands need --entrypoint

The compose `certbot` service's entrypoint is the 12h renew LOOP. A plain
`docker compose run certbot certonly ...` hands your arguments to that loop
and HANGS SILENTLY. Always override:

    docker compose -f deploy/docker-compose.yml --env-file deploy/.env \
      run --rm --entrypoint certbot certbot certonly --webroot -w /var/www/certbot \
      --cert-name api.attachments.dev -d api.attachments.dev -d attachments.dev \
      -d www.attachments.dev --expand --non-interactive --agree-tos -m mrive052@gmail.com

Then `... exec -T nginx nginx -s reload`.
