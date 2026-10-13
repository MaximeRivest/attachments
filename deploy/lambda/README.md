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
