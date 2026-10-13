# api.attachments.dev and attachments.dev on lambda

Since 2026-10-13 the hosted service and the website run on lambda (the home server), not on
AWS. They are reached the same way as api.sciencemadereadable.com:

```
visitor ─HTTPS─> relay (encrypted-link-relay, OVH, 144.217.95.30)
                   HAProxy :443 ─> Caddy :8443 (TLS, Let's Encrypt, no access log)
                   ─> 127.0.0.1:18820, the far end of an SSH tunnel that lambda keeps open
         ─tunnel─> lambda nginx 127.0.0.1:8820 (rate limits, CORS, website, gzip)
                   ─> the service, unix socket /run/attachments-api/api.sock
```

- **Nothing on lambda is open to the internet.** Lambda dials out to the relay. The relay's
  account `att-tunnel` can only listen on 127.0.0.1:18820 and cannot reach lambda.
- **Visitors' addresses.** The relay's Caddy writes the visitor's address in
  `X-Forwarded-For`, ignoring any sent by the visitor. nginx counts its rate limits by it:
  10 uploads a minute per address (burst 20), 2 other requests a second. Tested 2026-10-13:
  20 × 200 then 429; a spoofed `X-Forwarded-For` was ignored.
- **The service's sandbox** (`~/Projects/os/machines/hosts/lambda/attachments-api.nix`) runs
  gunicorn inside the files of `deploy/Dockerfile`'s image, unpacked read-only under
  `/var/lib/attachments-api/releases/<version>/rootfs`. It runs as user `attachments-api`
  with no view of /home and no write access outside its own home (LibreOffice's profile) and
  /tmp. The kernel refuses it every non-public address: loopback, the LAN, the tailnet,
  link-local and cloud metadata. That holds for LibreOffice too, and for DNS rebinding, which
  the library's own check cannot stop. It resolves names through public DNS. Limits:
  12 CPUs, 16 GB, low CPU weight. No container network: rootful podman bridges have
  disturbed tailscaled on lambda before (ai-services.nix).

## OCR: LightOnOCR-3 on GPU 1, RapidOCR standing in

Since 2026-10-13 the service reads scanned pages with **LightOnOCR-3-0.8B** (olmOCR-bench on
lambda: 82.8 against 39.7 for RapidOCR; scanned pages 64 % against 20 %). It runs as
`model-vllm-lighton-ocr` (`hosts/lambda/attachments-api.nix`): vLLM on GPU 1, answering only on
the unix socket `/run/lighton-ocr/vllm.sock` (group `lighton-ocr`; the service is a member and
has the folder bound into its sandbox, which still opens no local address). The service sets
`ATTACHMENTS_OCR_ENGINE=lighton` and `ATTACHMENTS_LIGHTON_URL=unix:/run/lighton-ocr/vllm.sock`.

- **RapidOCR reads whatever LightOn cannot**, page by page: model not running, an error, a page
  it never finishes. The answer says so (`meta.warnings`, `meta.extra.ocr_fallback_pages`) and
  `meta.extra.ocr_backend` names the engine. Visitors never get an error for it.
- **GPU 1 is shared.** The model starts only when GPU 1 has room (20 % of it, ~5 GB) and
  nobody reserved it; otherwise it is skipped cleanly and `lighton-ocr-retry.timer` tries again
  every 10 minutes. Figurer training reserves GPU 1: `figurer/train/gpu1_services.sh stop`
  leaves `/run/gpu1-reserved` and stops it with the household services; `start` removes the
  marker and starts them all. Every GPU 1 service now refuses to start while the marker is
  there, so a rebuild cannot start them next to a training run (it did on 2026-10-13).
- **A test page before use.** Each start ends with a check (`lighton-ocr-canary`): the model
  must read a small invoice right, with the library's settings. If it does not, the service
  stops and leaves `/run/lighton-ocr/disabled` with the reason; no more starts until someone
  looks and removes it.
- **Tested on lambda 2026-10-13** (on GPU 0 for 13 minutes, the science site's 9B paused, with
  the service's exact command): first start 6.5 minutes (compiling, cached since), test page
  read right; 1.7 GiB of weights, cache for 102,732 tokens, 5.3 GB in use under load. Through
  the public address: a 10-page scan in 10 s, every word right; three such scans at once
  13.5 s, no fallback; the same page twice, identical text; vLLM logs no page content. The
  1914 letter of olmOCR-bench: "Bangor. Pa. may 22. nd 1914. Col. Rosevelt / Commade &
  Friend" (RapidOCR: "Bangou. .Pa. may22. P nd 1914. CeoeWRosevelt bernrade Frind"). The
  library's Markdown equals the benchmark's on all 1,403 saved answers.
- **The library on the server is not a PyPI release**: `1.0.0b8+lighton.2` is 1.0.0b8 plus
  this change (branch `server/1.0.0b8-lighton`, deployed with `release.sh --wheel`), because
  `main` also holds unreleased work. The next PyPI release includes it.

```bash
systemctl status model-vllm-lighton-ocr     # running? why not? (journalctl -u model-vllm-lighton-ocr)
sudo cat /run/lighton-ocr/disabled          # present: the test page failed, and why
sudo rm /run/lighton-ocr/disabled && sudo systemctl start lighton-ocr-retry   # try again
cat /run/gpu1-reserved                      # who holds GPU 1
```

## Everyday commands

```bash
deploy/lambda/release.sh 1.0.0b9      # publish a PyPI version: build, unpack, switch, health check
deploy/lambda/release.sh --rollback   # back to the previous release (two are kept)
deploy/lambda/release.sh --status
.venv/bin/python deploy/lambda/smoke.py                                          # lambda only
.venv/bin/python deploy/lambda/smoke.py https://api.attachments.dev https://attachments.dev  # public
~/Projects/attachments-web/deploy.sh   # the website, into /srv/attachments-site

journalctl -u attachments-api -f       # the service
systemctl status attachments-tunnel    # the tunnel (reconnects by itself)
sudo tail -f /var/log/nginx/attachments-api.log
```

Settings (workers, OCR page cap, upload cap) are in the .nix file. Change them there and
rebuild lambda; `release.sh` is only for new versions.

## The relay

Copies of its two files are in `relay/`:
- `/etc/caddy/conf.d/attachments.caddy`. Caddy there has no reload: `sudo systemctl restart
  caddy` interrupts every site on the relay (the science site, Chattering previews) for a few
  seconds.
- `/etc/ssh/sshd_config.d/11-att-tunnel.conf`, plus `/var/lib/att-tunnel/.ssh/authorized_keys`
  (`restrict,port-forwarding,permitlisten="127.0.0.1:18820"` and lambda's
  `~/.ssh/att-tunnel_ed25519.pub`).

Administration: `ssh ubuntu@encrypted-link-relay`.

## DNS (GoDaddy)

`attachments.dev` and `api.attachments.dev`: A 144.217.95.30, TTL 600 (until 2026-10-13:
3.97.211.179, AWS). `www` is a CNAME to the bare domain. No AAAA record: IPv6 visitors would
each get a whole /64 of addresses to spread over the rate limits.

## What this depends on, compared with AWS

- **Lambda, its power and the home connection.** When lambda reboots, a rebuild restarts the
  service (about 30 s of warm-up), or the connection drops, the service and the website are
  down. AWS did not share that. The GitHub monitor (`.github/workflows/monitor.yml`, every 6 h)
  notices.
- **The relay**, shared with sciencemadereadable.com and Chattering Anywhere: 2 vCPU, 3.7 GB.
  Proxying is light. Uploads (up to 25 MiB) and answers (page pictures, often a few MB) cross
  the home connection.
- **Cost:** nothing extra. The relay was already paid for. AWS cost about $105 a month.
- **Speed:** OCR reads 1.4–1.6 s a page (AWS: 4.5 s); 4 workers instead of 2.
- **The GPU:** a model on lambda's GPUs (LightOnOCR) can now serve the service at no extra cost,
  once the library supports it. It needs one careful hole in the sandbox: `IPAddressDeny` works
  per address, not per port, so allowing 127.0.0.1 would reopen every service on lambda to
  strangers' URLs. Give the model its own address instead (for example a dummy interface
  address only it listens on) and allow just that one.
