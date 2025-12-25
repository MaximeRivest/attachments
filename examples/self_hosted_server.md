# Self-Hosted Attachments Server

This example shows how to set up a self-hosted attachments server so your team can process files without installing dependencies on every machine.

## The Problem

Installing all attachments dependencies can be complex:
- PDF processing needs `pypdf`, `pymupdf`, and optionally system libraries
- Audio transcription needs `whisper` (large model downloads, GPU optional)
- OCR needs `tesseract` system binary
- Some deps have complex build requirements

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
│ # Returns artifact!      │ artifact │ │ • whisper (Audio)          │   │
│                          │          │ │ • tesseract (OCR)          │   │
└──────────────────────────┘          │ │ • ... everything else      │   │
                                      │ └────────────────────────────┘   │
                                      └──────────────────────────────────┘
```

---

## Server Setup

### 1. Install on Server Machine

```bash
# Install attachments with all processors
pip install attachments[server]

# Or be specific about what you need
pip install attachments[pdf,xlsx,docx,pptx,audio,ocr]
```

### 2. Set Security Key

```bash
# Set a secret key for authentication
export ATTACHMENTS_SERVER_KEY="your-team-secret-key"

# Optional: Customize max upload size (default 256MB)
export ATTACHMENTS_MAX_UPLOAD=536870912  # 512MB
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
║  URL:  http://0.0.0.0:8000                                   ║
║  Auth: enabled                                               ║
╠══════════════════════════════════════════════════════════════╣
║  Endpoints:                                                  ║
║    POST /process  - Process a file                           ║
║    POST /unpack   - Unpack a URL                             ║
║    GET  /health   - Health check                             ║
║    GET  /formats  - List supported formats                   ║
╚══════════════════════════════════════════════════════════════╝

Available features: pdf, pdf-text, pdf-images, xlsx, xlsx-pandas, docx, pptx
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

# Excel files
artifacts = att("sales-data.xlsx")
print(f"Rows: {artifacts[0]['flags']['rows']}")

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

### Docker

```dockerfile
# Dockerfile
FROM python:3.12-slim

# Install system deps for some processors (optional)
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

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

### Health Check

```bash
curl http://server:8000/health
```

```json
{
  "status": "ok",
  "version": "0.1.0",
  "features": {
    "pdf": true,
    "pdf-text": true,
    "pdf-images": true,
    "xlsx": true,
    "xlsx-pandas": true
  }
}
```

### List Formats

```bash
curl http://server:8000/formats
```

```json
{
  "formats": [".pdf", ".xlsx", ".txt", ".md", "__text__", ...],
  "count": 24
}
```

### Process File

```bash
curl -X POST http://server:8000/process \
  -H "Authorization: Bearer your-secret" \
  -F "file=@document.pdf"
```

```json
{
  "text": "Extracted text content...",
  "images": [
    {
      "name": "document-page-1.png",
      "mimetype": "image/png",
      "bytes_b64": "iVBORw0KGgo...",
      "page": 1
    }
  ],
  "audio": [],
  "video": [],
  "flags": {
    "source": "document.pdf",
    "type": "pdf",
    "pages": 5
  }
}
```

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
ServiceError: Service request failed: Connection refused
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
ServiceError: Unauthorized
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

**Fix**: Increase server limit:
```bash
export ATTACHMENTS_MAX_UPLOAD=1073741824  # 1GB
```
