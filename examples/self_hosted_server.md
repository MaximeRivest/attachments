# Self-Hosted Attachments Server

This example shows how to set up a self-hosted attachments server so your team can process files without installing dependencies on every machine.

## The Problem

Installing all attachments dependencies on every machine adds up:
- PDF processing needs `pypdf` and `pymupdf`
- Excel needs `openpyxl` (and optionally `pandas`)
- Word/PowerPoint need `python-docx` / `python-pptx`
- HTML needs `beautifulsoup4` + `lxml`, images need `Pillow`
- Future heavy processors (OCR, audio transcription) will be worse

## The Solution

**One machine has all the deps. Everyone else just connects to it.**

```
┌──────────────────────────┐          ┌──────────────────────────────────┐
│ Client Machines          │          │ Server Machine                   │
│ (minimal deps)           │          │ (all deps installed)             │
│                          │          │                                  │
│ pip install              │   HTTP   │ pip install attachments[server]  │
│   attachments[service]   │ ──────>  │                                  │
│                          │          │ attachments-server               │
│ from attachments import  │          │   --host 0.0.0.0                 │
│   att, configure         │          │   --port 8000                    │
│                          │          │                                  │
│ configure(               │          │ ┌────────────────────────────┐   │
│   service_url="...",     │          │ │ All processors available:  │   │
│   api_key="..."          │          │ │ • pypdf, pymupdf (PDF)     │   │
│ )                        │          │ │ • openpyxl, pandas (Excel) │   │
│                          │          │ │ • python-docx (Word)       │   │
│ att("document.pdf")      │  <────   │ │ • python-pptx (PowerPoint) │   │
│ # Returns artifact!      │ artifact │ │ • bs4, lxml (HTML)         │   │
│                          │          │ │ • Pillow (images)          │   │
└──────────────────────────┘          │ └────────────────────────────┘   │
                                      └──────────────────────────────────┘
```

---

## Server Setup

### 1. Install on Server Machine

```bash
# Install attachments with all shipped processors
pip install attachments[server]

# Or be specific about what you need
pip install attachments[pdf,xlsx,docx,pptx,html,image]
```

### 2. Set Security Key

```bash
# Set a secret key for authentication
export ATTACHMENTS_SERVER_KEY="your-team-secret-key"

# Optional: Customize max upload size (default 256MB).
# Oversized request bodies are rejected with HTTP 413 before being read.
export ATTACHMENTS_MAX_UPLOAD=536870912  # 512MB

# Optional: allow /unpack to fetch private/internal addresses.
# By default the server BLOCKS URLs that resolve to loopback, link-local
# (cloud metadata), or private-range hosts — an SSRF guard. Only enable
# this if the server runs in a trusted network and needs internal URLs.
export ATTACHMENTS_ALLOW_PRIVATE_URLS=1
```

### 3. Start the Server

```bash
# Simple mode (development)
attachments-server --host 0.0.0.0 --port 8000

# Or via Python module
python -m attachments.server --host 0.0.0.0 --port 8000
```

You'll see:
```
╔══════════════════════════════════════════════════════════════╗
║                   Attachments Server                         ║
╠══════════════════════════════════════════════════════════════╣
║  URL:  http://0.0.0.0:8000                                  ║
║  Auth: enabled                                              ║
╠══════════════════════════════════════════════════════════════╣
║  Endpoints:                                                  ║
║    POST /process  - Process a file                           ║
║    POST /unpack   - Unpack a URL                             ║
║    GET  /health   - Health check                             ║
║    GET  /formats  - List supported formats                   ║
║    GET  /options  - DSL option schemas                       ║
╚══════════════════════════════════════════════════════════════╝

Available features: pdf, pdf-text, pdf-images, xlsx, xlsx-pandas, docx, pptx, html, image, service
```

---

## Client Setup

### 1. Install Minimal Dependencies

```bash
# Only httpx is needed!
pip install attachments[service]
```

### 2. Configure and Use

```python
from attachments import att, configure

# Point to your server (do this once at startup)
configure(
    service_url="http://your-server-ip:8000",
    api_key="your-team-secret-key"
)

# Now everything works!
artifacts = att("quarterly-report.pdf")
print(artifacts[0]["text"][:500])
print(artifacts[0]["meta"]["via"])  # "service"

# Excel files
artifacts = att("sales-data.xlsx")
print(f"Sheets: {artifacts[0]['meta']['extra']['sheets']}")

# Even URLs work - server fetches and processes
artifacts = att("https://arxiv.org/pdf/2301.00001.pdf")
```

### 3. Environment Variables (Alternative)

Instead of `configure()`, you can use environment variables:

```bash
export ATTACHMENTS_SERVICE_URL="http://your-server-ip:8000"
export ATTACHMENTS_API_KEY="your-team-secret-key"
```

```python
from attachments import att

# Automatically uses env vars
artifacts = att("document.pdf")
```

---

## Production Deployment

For production use the WSGI app (`attachments.server:create_app`) with
gunicorn instead of the stdlib development server:

### Docker

```dockerfile
# Dockerfile
FROM python:3.12-slim

# Install attachments with all deps
RUN pip install attachments[server] gunicorn

# Security: don't run as root
RUN useradd -m attachments
USER attachments

EXPOSE 8000

# Use gunicorn for production
CMD ["gunicorn", "attachments.server:create_app()", \
     "-b", "0.0.0.0:8000", \
     "-w", "4", \
     "--timeout", "120"]
```

```bash
# Build and run
docker build -t attachments-server .
docker run -d \
  -p 8000:8000 \
  -e ATTACHMENTS_SERVER_KEY=your-secret \
  attachments-server
```

### Docker Compose

```yaml
# docker-compose.yml
version: '3.8'

services:
  attachments:
    build: .
    ports:
      - "8000:8000"
    environment:
      - ATTACHMENTS_SERVER_KEY=${ATTACHMENTS_SERVER_KEY}
      - ATTACHMENTS_MAX_UPLOAD=536870912
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

### Systemd Service

```ini
# /etc/systemd/system/attachments.service
[Unit]
Description=Attachments Server
After=network.target

[Service]
Type=simple
User=attachments
Environment="ATTACHMENTS_SERVER_KEY=your-secret"
ExecStart=/usr/local/bin/gunicorn attachments.server:create_app() -b 0.0.0.0:8000 -w 4
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable attachments
sudo systemctl start attachments
```

---

## Use Cases

### 1. Team Development Server

One developer sets up the server, whole team uses it:

```python
# In your team's shared config
ATTACHMENTS_CONFIG = {
    "service_url": "http://dev-server.internal:8000",
    "api_key": os.environ["TEAM_ATTACHMENTS_KEY"],
}

# In any project
from attachments import configure
configure(**ATTACHMENTS_CONFIG)
```

### 2. CI/CD Pipeline

Server in your infrastructure, GitHub Actions connects:

```yaml
# .github/workflows/process-docs.yml
jobs:
  process:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install attachments client
        run: pip install attachments[service]

      - name: Process documents
        env:
          ATTACHMENTS_SERVICE_URL: ${{ secrets.ATTACHMENTS_URL }}
          ATTACHMENTS_API_KEY: ${{ secrets.ATTACHMENTS_KEY }}
        run: python scripts/process_docs.py
```

### 3. Serverless Functions

Lambda/Cloud Functions with zero deps:

```python
# lambda_function.py
from attachments import att, configure

# Configure once (cold start)
configure(
    service_url=os.environ["ATTACHMENTS_URL"],
    api_key=os.environ["ATTACHMENTS_KEY"],
)

def handler(event, context):
    # Process uploaded file
    file_path = download_from_s3(event["bucket"], event["key"])
    artifacts = att(file_path)

    # Store results
    save_to_database(artifacts)

    return {"status": "processed", "artifacts": len(artifacts)}
```

### 4. Air-Gapped Environment

Keep all processing inside your secure network:

```
┌─────────────────────────────────────────────────────────────┐
│                    Secure Network                           │
│                                                             │
│   ┌─────────────┐      ┌─────────────────────────────┐      │
│   │ Workstation │ ───> │ Attachments Server          │      │
│   │ (client)    │      │ (all processing here)       │      │
│   └─────────────┘      └─────────────────────────────┘      │
│                                                             │
│   No external API calls. No data leaves the network.        │
└─────────────────────────────────────────────────────────────┘
```

---

## API Reference

GET routes are public; POST routes require `Authorization: Bearer <key>`
when `ATTACHMENTS_SERVER_KEY` is set.

### Health Check

```bash
curl http://server:8000/health
```

```json
{
  "status": "ok",
  "version": "1.0.0",
  "features": {
    "pdf": true,
    "pdf-text": true,
    "pdf-images": true,
    "xlsx": true,
    "xlsx-pandas": true,
    "docx": true,
    "pptx": true,
    "html": true,
    "image": true,
    "service": true
  }
}
```

(`features` lists only the dependency groups available on the server.)

### List Formats

```bash
curl http://server:8000/formats
```

```json
{
  "formats": ["__text__", ".txt", ".md", ".markdown", ".rst", ".csv", "...", ".pdf", ".xlsx", ".docx", ".pptx", ".png"],
  "count": 35
}
```

### List DSL Options

The full declared option schemas (`attachments.dsl_schema()` export — the
same data behind `att.options()` and `att --options`):

```bash
curl http://server:8000/options
```

```json
{
  "version": 1,
  "processors": {
    ".pdf": [
      {"name": "pages", "type": "pages", "aliases": ["page"], "param": null,
       "default": null, "help": "Pages to include: a 1-based page number or range.",
       "example": "pages: 1-4"}
    ]
  },
  "sources": {
    "github://": [
      {"name": "ref", "type": "str", "aliases": ["branch", "tag"], "param": null,
       "default": null, "help": "Git branch, tag, or ref to clone.", "example": "ref: main"}
    ]
  }
}
```

(Excerpt — every processor with declared options appears under `processors`.)

### Process File

DSL options travel as extra form fields (here: `pages=1-2`):

```bash
curl -X POST http://server:8000/process \
  -H "Authorization: Bearer your-secret" \
  -F "file=@document.pdf" \
  -F "pages=1-2"
```

The response body is exactly an Artifact (images carry `bytes_b64` on the
wire — see `spec/IR-CONTRACT.md`):

```json
{
  "text": "Hello from page 1. Quarterly revenue grew 12%.\n\nHello from page 2. ...",
  "images": [],
  "audio": [],
  "video": [],
  "meta": {
    "source": "document.pdf",
    "kind": "pdf",
    "segments": [
      {"kind": "page", "label": "page 1", "start": 0, "end": 46},
      {"kind": "page", "label": "page 2", "start": 48, "end": 94}
    ],
    "extra": {"encrypted": false, "text_backend": "pypdf", "pages": 3, "parsed_pages": 2}
  }
}
```

With `images: true`, each rendered page appears as
`{"name": "document.pdf-page-1.png", "mimetype": "image/png", "bytes_b64": "iVBORw0KGgo...", "page": 1}`.

### Unpack URL

```bash
curl -X POST http://server:8000/unpack \
  -H "Authorization: Bearer your-secret" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://github.com/org/repo/archive/main.zip"}'
```

```json
{
  "files": [
    {"filename": "README.md", "data_b64": "IyBQcm9qZWN0..."},
    {"filename": "src/main.py", "data_b64": "aW1wb3J0IG9z..."}
  ]
}
```

---

## Troubleshooting

### Connection Refused

```
ServiceError: Service request failed: ... Connection refused
```

**Fix**: Check server is running and port is open:
```bash
# On server
curl http://localhost:8000/health

# Check firewall
sudo ufw allow 8000
```

### Unauthorized (401)

```
ServiceError: Invalid API key
```

**Fix**: Check API key matches:
```bash
# Server
echo $ATTACHMENTS_SERVER_KEY

# Client
echo $ATTACHMENTS_API_KEY
```

### Timeout

```
ServiceError: Service request timed out after 60s
```

**Fix**: Increase timeout for large files:
```python
configure(
    service_url="http://server:8000",
    api_key="secret",
    timeout=300  # 5 minutes
)
```

### File Too Large (413)

```
{"error": "Upload too large (max 268435456)"}
```

**Fix**: Increase server limit:
```bash
export ATTACHMENTS_MAX_UPLOAD=1073741824  # 1GB
```

### Blocked URL (400)

```
{"error": "Blocked URL 'http://10.0.0.5/x': host '10.0.0.5' resolves to non-public address 10.0.0.5"}
```

`/unpack` refuses URLs that resolve to private/internal addresses by
default (SSRF guard). If the server should fetch internal URLs:

```bash
export ATTACHMENTS_ALLOW_PRIVATE_URLS=1
```
