# 🔗 Attachments – The Python Funnel for LLM Context

### Turn *any* file into model-ready text ＋ images, in one line

**MIT-licensed**, modular, and type-safe. The same simple interface you know, now with a robust architecture underneath.

> **TL;DR**  
> ```bash
> pip install attachments
> ```
> ```python
> from attachments import Attachments
> ctx = Attachments("report.pdf", "photo.jpg")
> llm_ready_text   = str(ctx)       # all extracted text, "prompt-engineered"
> llm_ready_images = ctx.images     # list[str] – base64 PNGs
> ```

**Why Attachments?** Stop re-writing file-to-LLM plumbing in every project. One line gets you from files to AI-ready content, with a **modular architecture** that's easy to extend.

## ✨ What's New in v0.4

- 🏗️ **Modular Architecture**: Clean separation of `loaders`, `presenters`, `modifiers`, `adapters`
- 📜 **MIT License Compatible**: Default PDF support via `pypdf` + `pypdfium2` (BSD licenses)
- 🎯 **Type-Safe Dispatch**: Components auto-register based on Python types
- 🔧 **Easy Extension**: Add new file formats with a single decorated function
- 📦 **Better Dependencies**: Optional heavy dependencies, lighter default install

## 🚀 Quick Start

```bash
pip install attachments
```

```python
from attachments import Attachments

# Simple usage - just like before
ctx = Attachments("contract.pdf", "diagram.png")
print(ctx)                    # pretty text view
print(f"Images: {len(ctx.images)}")  # base64 PNG count

# With page selection and transformations  
ctx = Attachments(
    "report.pdf[1,3-5,-1]",          # pages 1, 3-5, and last
    "slides.pptx[1-3]",              # first 3 slides from PowerPoint
    "data.csv[sample:100]",          # random sample of 100 rows
    "chart.jpg",                     # images as base64 PNGs
    "summary.pdf"                    # additional documents
)
```

## 🤖 AI Integration

### OpenAI (GPT)

```python
from openai import OpenAI
from attachments import Attachments
from attachments.core import adapt

# Load files (single or multiple)
ctx = Attachments("research_paper.pdf", "chart.png")

# Adapters work with both Attachments and Attachment objects!
messages = adapt.openai_chat(ctx, "Summarize the key findings:")

client = OpenAI()
response = client.chat.completions.create(
    model="gpt-4o",
    messages=messages
)
print(response.choices[0].message.content)

# For OpenAI's new responses API
input_data = adapt.openai_responses(ctx, "what is in these documents?")
response = client.responses.create(
    model="gpt-4o",
    input=input_data
)
```

### Anthropic (Claude)

```python
import anthropic
from attachments import Attachments
from attachments.core import adapt

# Process multiple files with DSL commands
ctx = Attachments("presentation.pptx[1-5]", "data.csv", "chart.png")

# Adapter automatically handles the squashing!
messages = adapt.claude(ctx, "Analyze these slides and data:")

client = anthropic.Anthropic()
message = client.messages.create(
    model="claude-3-5-sonnet-20241022", 
    max_tokens=8192,
    messages=messages
)
print(message.content[0].text)
```

## 📋 Supported Formats

### Built-in Support
- **Documents**: PDF (MIT-compatible via `pypdf`), CSV, plain text
- **Images**: PNG, JPEG, BMP, GIF, WEBP, HEIC/HEIF via PIL
- **Path Expressions**: `file.pdf[1,3-5]`, `data.csv[sample:100]`, etc.

### Extended Support (Optional)
```bash
# More file formats (including PowerPoint)
pip install 'attachments[extended]'

# Everything
pip install 'attachments[all]'
```

With extended support, you get:
- **Presentations**: PowerPoint (PPTX) via `python-pptx`
- **Rich Documents**: Word (DOCX), Excel, and more via `markitdown`

## 🏗️ Modular Architecture 

The new architecture separates concerns into specialized components:

```python
from attachments.core import load, present, modify, adapt

# Low-level interface for advanced users
pdf_doc = load.pdf("report.pdf")           # Load PDF
pptx_doc = load.pptx("slides.pptx")        # Load PowerPoint (extended)
pages = modify.pages(pdf_doc, "1,3-5")     # Select specific pages  
slides = modify.pages(pptx_doc, "1-3")     # Select specific slides
text = present.text(pages)                 # Extract text
xml = present.xml(slides)                  # Extract XML structure
images = present.images(pages)             # Render as images
openai_msgs = adapt.openai(text, images)   # Format for OpenAI
```

Each component is **auto-registered** based on Python types. The function name becomes the namespace attribute:

```python
from attachments.core.decorators import loader

@loader(lambda path: path.endswith('.xyz'))  
def xyz_file(path: str):
    # Load your custom format
    return your_custom_object
    
# Now available as: load.xyz_file("document.xyz")
```

## 📝 Path Expression DSL

| Expression              | Result                                      |
|------------------------|---------------------------------------------|
| `report.pdf[1,3-5,-1]` | Pages 1, 3-5, and last page               |
| `slides.pptx[1-3]`     | First 3 slides from PowerPoint            |
| `slides.pptx[-1]`      | Last slide only                           |
| `data.csv[sample:10]`  | Random sample of 10 rows                  |
| `data.csv[sample:100]` | Random sample of 100 rows                 |
| `image.jpg[resize:50%]` | Resize image to 50% of original size     |

## 🔧 Extension Examples

### Add a New Loader

```python
from attachments.core.decorators import loader

@loader(lambda path: path.endswith('.json'))
def json_file(path: str):
    import json
    with open(path) as f:
        return json.load(f)

# Now available as: load.json_file("data.json")
```

### Add a New Presenter

```python
from attachments.core.decorators import presenter

@presenter
def summary(data: dict) -> str:
    """Generate summary for dictionary data."""
    return f"Dictionary with {len(data)} keys: {list(data.keys())[:5]}..."
```

The type system automatically routes content to the right handlers!

## 📜 License & Compatibility

**MIT License** with careful dependency management:

- ✅ **Default**: MIT-compatible libraries only (`pypdf`, `pypdfium2`, `pillow`)  
- ⚠️ **Optional**: AGPL libraries via explicit opt-in (`PyMuPDF` with `[pdf-agpl]`)

This ensures your project stays MIT-licensed unless you explicitly choose otherwise.

## 🛠️ Development

```bash
git clone https://github.com/MaximeRivest/attachments
cd attachments
uv sync
uv run pytest
```

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for detailed design documentation and [`CONTRIBUTING.md`](CONTRIBUTING.md) for contribution guidelines.

## 🎯 API Reference

### High-Level Interface

| Object                    | Description                                  |
|--------------------------|----------------------------------------------|
| `Attachments(*paths)`    | Load and process multiple files             |
| `Attachments.attachments`| List of loaded Attachment objects           |
| `Attachments.text`       | All extracted text, joined with newlines    |
| `Attachments.images`     | List of base64-encoded PNG data URLs        |

### Core Components (Low-Level API)

| Module                   | Purpose                                      | Example |
|--------------------------|----------------------------------------------|---------|
| `attachments.core.load`  | File loaders with `\|` composition         | `load.pdf \| load.image` |
| `attachments.core.modify` | Content modifiers                          | `modify.pages(att, "1-3")` |
| `attachments.core.present` | Format converters                         | `present.text(att)` |
| `attachments.core.adapt` | LLM API adapters                           | `adapt.openai_chat(att, prompt)` |

### Available Adapters

| Adapter | Purpose | Usage |
|---------|---------|-------|
| `adapt.openai_chat` | OpenAI Chat Completions | `client.chat.completions.create(messages=...)` |
| `adapt.openai_responses` | OpenAI Responses API | `client.responses.create(input=...)` |
| `adapt.claude` | Anthropic Messages | `client.messages.create(messages=...)` |

## 🚀 What's Next?

The modular architecture makes it easy to add:
- 📄 **New file formats** (DOCX, XLSX, HTML, etc.)
- 🎨 **New presentations** (LaTeX, HTML, RTF, etc.) 
- ⚙️ **New modifiers** (translate, summarize, filter, etc.)
- 🔌 **New adapters** (Gemini, local models, etc.)

**Join us!** File an issue, open a PR, or share your custom components. Let's build the universal file-to-AI pipeline together! 🌟

---

**Attachments** – Because every AI project starts with "How do I get my data into the model?" 🤖