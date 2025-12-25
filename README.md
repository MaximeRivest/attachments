# attachments

> Turn anything into LLM-ready artifacts.

## Quick Start

```bash
# Install core (text files work out of the box)
pip install attachments

# Add format support as needed
pip install attachments[pdf]         # PDF support
pip install attachments[xlsx]        # Excel support
pip install attachments[service]     # API fallback mode
pip install attachments[all-local]   # Everything
```

```python
from attachments import att, configure, check_deps

# See what's available
check_deps()  # {'pdf': True, 'xlsx': True, 'service': False, ...}

# Process anything
artifacts = att("document.pdf")
artifacts = att("data/")                    # Directory
artifacts = att("github://owner/repo")      # GitHub repo
artifacts = att("https://example.com/f.pdf") # URL

# Inline options with DSL syntax
artifacts = att("report.pdf[pages: 1-4]")
artifacts = att("report.pdf[pages: 1-10, images: true, dpi: 300]")
artifacts = att("data.xlsx[sheet: Sales, rows: 100]")
artifacts = att("github://org/repo[branch: develop]")

# With service fallback (when local deps missing)
configure(api_key="att_...")
artifacts = att("document.pdf")  # Uses service if pypdf not installed
```

## DSL Syntax

Specify options inline with `[key: value, ...]`:

```python
# PDF options
att("doc.pdf[pages: 1-4]")              # Pages 1-4 (1-based)
att("doc.pdf[pages: 5-10, images: true]") # With image rendering
att("doc.pdf[dpi: 300]")                # High-res images
att("doc.pdf[password: secret]")        # Encrypted PDF

# Excel options
att("data.xlsx[sheet: Revenue]")        # Specific sheet
att("data.xlsx[sheet: 0, rows: 50]")    # First sheet, 50 rows

# GitHub options
att("github://org/repo[branch: main]")  # Specific branch
att("github://org/repo[ref: v1.0.0]")   # Tag

# Combine with URLs
att("https://arxiv.org/pdf/2301.00001.pdf[pages: 1-5]")
```

**Keys:** `pages`, `page`, `sheet`, `rows`, `images`, `dpi`, `password`, `branch`, `ref`
**Values:** Numbers, booleans (`true`/`false`), ranges (`1-4`), strings

## Hybrid Local/Service Architecture

```
┌─────────────────────────────────────────────────────┐
│  att("file.pdf", prefer="local")                    │
└─────────────────────┬───────────────────────────────┘
                      │
         ┌────────────▼────────────┐
         │ Has local processor?    │
         │ (pypdf installed?)      │
         └────────────┬────────────┘
                ┌─────┴─────┐
              Yes          No
                │            │
         ┌──────▼──────┐    │
         │ Try local   │    │
         └──────┬──────┘    │
                │           │
         ┌──────▼──────┐    │
         │ Succeeded?  ├────┤
         └──────┬──────┘    │
              Yes          No + has API key
                │            │
                │     ┌──────▼──────┐
                │     │ Try service │
                │     └──────┬──────┘
                │            │
         ┌──────▼────────────▼──────┐
         │     Return artifact      │
         └──────────────────────────┘
```

**Modes:**
- `prefer="local"` (default): Try local, fall back to service
- `prefer="service"`: Try service first, fall back to local
- `prefer="local-only"`: Only local, fail if deps missing
- `prefer="service-only"`: Only service, requires API key

## Self-Hosted Server

Run your own server with all deps, let others connect with zero deps:

```bash
# On server (one machine, all deps):
pip install attachments[server]
export ATTACHMENTS_SERVER_KEY="team-secret"
attachments-server --host 0.0.0.0 --port 8000

# On clients (zero deps needed):
pip install attachments[service]
```

```python
from attachments import att, configure

configure(service_url="http://server:8000", api_key="team-secret")
att("document.pdf")  # Processed on server!
```

See [examples/self_hosted_server.md](examples/self_hosted_server.md) for:
- Docker & Docker Compose setup
- Systemd service configuration
- CI/CD integration (GitHub Actions)
- Serverless deployment patterns
- API reference & troubleshooting

---

# Architecture: The Genius of attachments

## The Core Insight

The architecture answers one question brilliantly:

> **"How do I turn *anything* into something an LLM can consume?"**

```python
att("file.pdf")           # local file
att("data/")              # directory
att("github://org/repo")  # entire repo
att("https://...")        # URL
att("s3://bucket/key")    # extensible to anything
```

**One function. One output format. Any input.**

## The Genius: Composable Universality

### 1. The Artifact as Universal Currency

```python
{
    "text": "...",      # What LLMs read
    "images": [...],    # What multimodal LLMs see
    "audio": [],        # Future-ready
    "video": [],        # Future-ready
    "flags": {...}      # Metadata for routing/debugging
}
```

This isn't just a data structure—it's a **protocol**. Every processor speaks the same language. Every consumer expects the same shape. You can:

- Chain processors
- Merge artifacts from different sources
- Build middleware that transforms artifacts
- Route based on flags

### 2. Two Orthogonal Registries

```
┌─────────────────┐         ┌─────────────────┐
│  WHERE it comes │         │  WHAT it is     │
│  from           │         │                 │
│                 │         │                 │
│  unpack_handlers│         │  processors     │
│  - github://    │         │  - .pdf         │
│  - s3://        │         │  - .xlsx        │
│  - dropbox://   │         │  - .docx        │
└────────┬────────┘         └────────┬────────┘
         │                           │
         └──────────┬────────────────┘
                    ▼
              (filename, bytes)
                    │
                    ▼
               artifact
```

**Source and format are decoupled.** A PDF from S3 uses the same processor as a PDF from disk. This is the key insight that makes the system scale.

### 3. The "Unpack" Abstraction

The real genius is that `unpack()` flattens **any hierarchical structure** into a list:

```python
unpack("repo.zip")
# → [("repo/src/main.py", bytes), ("repo/README.md", bytes), ...]

unpack("github://org/monorepo")
# → [("src/app/index.ts", bytes), ("src/lib/utils.ts", bytes), ...]
```

Archives, repos, directories—all become flat lists. The rest of the pipeline doesn't care about hierarchy.

---

## How It Becomes Most Powerful

### 1. LLM Context Assembly

```python
def build_context(sources: list[str]) -> str:
    """Turn anything into LLM context."""
    artifacts = []
    for src in sources:
        artifacts.extend(att(src))

    # Smart assembly - fit into context window
    return assemble_for_context(artifacts, max_tokens=100_000)

# Usage
context = build_context([
    "github://company/backend",      # Entire codebase
    "https://docs.api.com/spec.pdf", # API spec
    "~/notes/requirements.txt",      # Local notes
])
```

### 2. RAG Pipeline Integration

```python
def ingest_to_vectordb(source: str, db: VectorDB):
    for artifact in att(source):
        # Text → chunks → embeddings
        if artifact["text"]:
            chunks = chunk_text(artifact["text"])
            db.add(chunks, metadata=artifact["flags"])

        # Images → vision model → descriptions → embeddings
        for img in artifact["images"]:
            description = vision_model.describe(img["bytes"])
            db.add([description], metadata={**artifact["flags"], "image": img["name"]})

# Ingest entire GitHub org
for repo in github.org_repos("my-company"):
    ingest_to_vectordb(f"github://my-company/{repo}", db)
```

### 3. Middleware Pattern

```python
def add_middleware(processor_fn):
    """Wrap any processor with cross-cutting concerns."""
    def wrapped(data: bytes, **opts) -> dict:
        artifact = processor_fn(data, **opts)

        # Add token count
        artifact["flags"]["tokens"] = count_tokens(artifact["text"])

        # Add content hash for dedup
        artifact["flags"]["hash"] = hashlib.sha256(data).hexdigest()

        # Truncate if too large
        if artifact["flags"]["tokens"] > 50_000:
            artifact["text"] = truncate_smart(artifact["text"], 50_000)
            artifact["flags"]["truncated"] = True

        return artifact
    return wrapped

# Apply to all processors
for key in processors:
    processors[key] = add_middleware(processors[key])
```

### 4. The Ultimate Vision: Universal Knowledge Ingestion

```python
# Register ALL the sources
register_unpack_handler("s3://", s3_handler)
register_unpack_handler("gdrive://", gdrive_handler)
register_unpack_handler("notion://", notion_handler)
register_unpack_handler("slack://", slack_handler)
register_unpack_handler("confluence://", confluence_handler)

# Register ALL the formats
register_processor(".docx", docx_processor)
register_processor(".pptx", pptx_processor)
register_processor(".eml", email_processor)
register_processor(".mp3", whisper_transcribe)

# Now THIS works:
knowledge = att("notion://workspace/Engineering")
knowledge += att("gdrive://shared/Product Specs")
knowledge += att("github://company/*")  # All repos
knowledge += att("slack://channel/announcements?since=2024-01-01")

# Feed to LLM
llm.chat(f"Given this context:\n{format_artifacts(knowledge)}\n\nAnswer: {question}")
```

---

## The Power Formula

```
Power = (Sources × Formats) → Unified Artifact → Any Consumer
```

| Sources (unpack) | Formats (processors) | Consumers |
|------------------|---------------------|-----------|
| Local files | PDF | LLM prompts |
| GitHub | Office docs | Vector DBs |
| S3/GCS | Code | Search indices |
| HTTP | Images | Summarizers |
| Notion | Audio/Video | Analytics |
| Slack | Email | Knowledge graphs |
| Confluence | Archives | |

**Each new source multiplies with ALL formats. Each new format works with ALL sources.**

That's the genius: **multiplicative extensibility** through two orthogonal registries connected by a universal intermediate representation.

---

## Adding New Processors & Sources

See [DEVELOPMENT.md](DEVELOPMENT.md) for:
- How to build new format processors
- How to build new source handlers
- Dependency management checklist
- Testing patterns
