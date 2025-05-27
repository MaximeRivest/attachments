# Attachments – the Python funnel for LLM context

### Turn *any* file into model-ready text ＋ images, in one line

Most users will not have to learn anything more than: `Attachments("path/to/file.pdf")`

> **TL;DR**  
> ```bash
> pip install attachments
> ```
> ```python
> from attachments import Attachments
> ctx = Attachments("https://github.com/MaximeRivest/attachments/raw/main/src/attachments/data/sample.pdf",
>                    "https://github.com/MaximeRivest/attachments/raw/refs/heads/main/src/attachments/data/sample_multipage.pptx")
> llm_ready_text   = str(ctx)       # all extracted text, already "prompt-engineered"
> llm_ready_images = ctx.images     # list[str] – base64 PNGs
> ```


Attachments aims to be **the** community funnel from *file → text + base64 images* for LLMs.  
Stop re-writing that plumbing in every project – contribute your *loader / transform / renderer* plugin instead!

## Quick-start ⚡

```bash
pip install attachments
```

### Try it now with sample files

```python
from attachments import Attachments
from attachments.data import get_sample_path

# Option 1: Use included sample files (works offline)
pdf_path = get_sample_path("sample.pdf")
txt_path = get_sample_path("sample.txt")
ctx = Attachments(pdf_path, txt_path)

print(str(ctx))      # Pretty text view
print(len(ctx.images))  # Number of extracted images

# Try different file types
docx_path = get_sample_path("test_document.docx")
csv_path = get_sample_path("test.csv")
json_path = get_sample_path("sample.json")

ctx = Attachments(docx_path, csv_path, json_path)
print(f"Processed {len(ctx)} files: Word doc, CSV data, and JSON")

# Option 2: Use URLs (same API, works with any URL)
ctx = Attachments(
    "https://github.com/MaximeRivest/attachments/raw/main/src/attachments/data/sample.pdf",
    "https://github.com/MaximeRivest/attachments/raw/main/src/attachments/data/sample_multipage.pptx"
)

print(str(ctx))      # Pretty text view  
print(len(ctx.images))  # Number of extracted images
```

### Advanced usage with DSL

```python
from attachments import Attachments

a = Attachments(
    "https://github.com/MaximeRivest/attachments/raw/main/src/attachments/data/" \
    "sample_multipage.pptx[3-5]"
)
print(a)           # pretty text view
len(a.images)      # 👉 base64 PNG list
```

### Send to OpenAI

```bash
pip install openai
```

```python
from openai import OpenAI
from attachments import Attachments

pdf = Attachments("https://github.com/MaximeRivest/attachments/raw/main/src/attachments/data/sample_multipage.pptx[3-5]")

client = OpenAI()
resp = client.chat.completions.create(
    model="gpt-4.1-nano",
    messages=pdf.openai_chat("Analyse the following document:")
)
print(resp.choices[0].message.content)
```

or with the response API

```python
from openai import OpenAI
from attachments import Attachments

pdf = Attachments("https://github.com/MaximeRivest/attachments/raw/main/src/attachments/data/sample_multipage.pptx[3-5]")

client = OpenAI()
resp = client.responses.create(
    input=pdf.openai_responses("Analyse the following document:"),
    model="gpt-4.1-nano"
)
print(resp.output[0].content[0].text)
```

### Send to Anthropic / Claude

```bash
pip install anthropic
```

```python
import anthropic
from attachments import Attachments

pptx = Attachments("https://github.com/MaximeRivest/attachments/raw/main/src/attachments/data/sample_multipage.pptx[3-5]")

msg = anthropic.Anthropic().messages.create(
    model="claude-3-5-haiku-20241022",
    max_tokens=8_192,
    messages=pptx.claude("Analyse the slides:")
)
print(msg.content)
```

### DSPy Integration

```bash
pip install dspy
```

```python
import dspy
from attachments import Attachments

dspy.configure(lm=dspy.LM('openai/gpt-4.1-nano'))
rag = dspy.ChainOfThought("question, document -> answer")

result = rag(
    question="What is the main message of the document?", 
    document=Attachments("https://github.com/MaximeRivest/attachments/raw/main/src/attachments/data/sample_multipage.pptx[3-5]").dspy()
)
print(result.answer)
```

### Advanced Pipeline Processing

For power users, use the full grammar system with composable pipelines:

```python
from attachments import attach, load, modify, present, refine, adapt

# Custom processing pipeline
result = (attach("document.pdf[pages:1-5]") 
         | load.pdf_to_pdfplumber 
         | modify.pages 
         | present.markdown + present.images
         | refine.add_headers | refine.truncate
         | adapt.claude("Analyze this content"))

# Web scraping pipeline
title = (attach("https://en.wikipedia.org/wiki/Llama[select:title]")
        | load.url_to_bs4 
        | modify.select 
        | present.text)

# Reusable processors
csv_analyzer = (load.csv_to_pandas 
               | modify.limit 
               | present.head + present.summary + present.metadata
               | refine.add_headers)

# Use as function
result = csv_analyzer("data.csv[limit:100]")
analysis = result.claude("What patterns do you see?")
```



---

## DSL cheatsheet 📝

| Piece                     | Example                   | Notes                                         |
| ------------------------- | ------------------------- | --------------------------------------------- |
| **Select pages / slides** | `report.pdf[1,3-5,-1]`    | Supports ranges, negative indices, `N` = last |
| **Image transforms**      | `photo.jpg[rotate:90]`    | Any token implemented by a `Transform` plugin |
| **Data-frame summary**    | `table.csv[summary:true]` | Ships with a quick `df.describe()` renderer   |
| **Web content selection** | `url[select:title]`       | CSS selectors for web scraping               |
| **Web element highlighting** | `url[select:h1][viewport:1920x1080]` | Visual highlighting in screenshots |
| **Image processing**      | `image.jpg[crop:100,100,400,300][rotate:45]` | Chain multiple transformations |
| **Content filtering**     | `doc.pdf[format:plain][images:false]` | Control text/image extraction |
| **Repository processing** | `repo[files:false][ignore:standard]` | Smart codebase analysis |

---

## Supported formats (out of the box)

* **Docs**: PDF, PowerPoint (`.pptx`), CSV, TXT, Markdown, HTML
* **Images**: PNG, JPEG, BMP, GIF, WEBP, HEIC/HEIF, …
* **Web**: URLs with BeautifulSoup parsing and CSS selection
* **Archives**: ZIP files → image collections with tiling
* **Repositories**: Git repos with smart ignore patterns
* **Data**: CSV with pandas, JSON

---

## Advanced Examples 🧩

### **Multimodal Document Processing**
```python
# PDF with image tiling and analysis
result = Attachments("report.pdf[tile:2x3][resize_images:400]")
analysis = result.claude("Analyze both text and visual elements")

# Multiple file types in one context
ctx = Attachments("report.pdf", "data.csv", "chart.png")
comparison = ctx.openai("Compare insights across all documents")
```

### **Repository Analysis**
```python
# Codebase structure only
structure = Attachments("./my-project[mode:structure]")

# Full codebase analysis with smart filtering
codebase = Attachments("./my-project[ignore:standard]")
review = codebase.claude("Review this code for best practices")

# Custom ignore patterns
filtered = Attachments("./app[ignore:.env,*.log,node_modules]")
```

### **Web Scraping with CSS Selectors**
```python
# Extract specific content from web pages
title = Attachments("https://example.com[select:h1]")
paragraphs = Attachments("https://example.com[select:p]")

# Visual highlighting in screenshots with animations
highlighted = Attachments("https://example.com[select:h1][viewport:1920x1080]")
# Creates screenshot with animated highlighting of h1 elements

# Multiple element highlighting with counters
multi_select = Attachments("https://example.com[select:h1, .important][fullpage:true]")
# Shows "H1 (1/3)", "DIV (2/3)", etc. with different colors for multiple selections

# Pipeline approach for complex scraping
content = (attach("https://en.wikipedia.org/wiki/Llama[select:p]")
          | load.url_to_bs4 
          | modify.select 
          | present.text
          | refine.truncate)
```

### **Image Processing Chains**
```python
# HEIC support with transformations
processed = Attachments("IMG_2160.HEIC[crop:100,100,400,300][rotate:90]")

# Batch image processing with tiling
collage = Attachments("photos.zip[tile:3x2][resize_images:800]")
description = collage.claude("Describe this image collage")
```

### **Data Analysis Workflows**
```python
# Rich data presentation
data_summary = Attachments("sales_data.csv[limit:1000][summary:true]")

# Pipeline for complex data processing
result = (attach("data.csv[limit:500]")
         | load.csv_to_pandas 
         | modify.limit
         | present.head + present.summary + present.metadata
         | refine.add_headers
         | adapt.claude("What trends do you see?"))
```

---

## Extending 🧩

```python
# my_ocr_renderer.py
from attachments.plugin_api import register_plugin, requires
from attachments.core import Renderer

@register_plugin("renderer_text", priority=50)
@requires("pytesseract", "PIL")
class ImageOCR(Renderer):
    content_type = "text"

    def match(self, obj):
        from PIL import Image
        return isinstance(obj, Image.Image)

    def render(self, obj, meta):
        import pytesseract
        return pytesseract.image_to_string(obj)
```

1. Put the file somewhere on disk.
2. `export ATTACHMENTS_PLUGIN_PATH=/abs/path/to/dir_or_file`
3. `import attachments` – your plugin is auto-discovered, no code changes.

---

## API reference (essentials)

| Object / method         | Description                                                     |
| ----------------------- | --------------------------------------------------------------- |
| `Attachments(*sources)` | Many `Attachment` objects flattened into one container          |
| `Attachments.text`      | All text joined with blank lines                                |
| `Attachments.images`    | Flat list of base64 PNGs                                        |
| `.claude(prompt="")`    | Claude API format with image support                            |
| `.openai_chat(prompt="")` | OpenAI Chat Completions API format                            |
| `.openai_responses(prompt="")` | OpenAI Responses API format (different structure)       |
| `.openai(prompt="")`    | Alias for openai_chat (backwards compatibility)                 |
| `.dspy()`               | DSPy BaseType-compatible objects                                 |

### Grammar System (Advanced)

| Namespace | Purpose | Examples |
|-----------|---------|----------|
| `load.*` | File format → objects | `pdf_to_pdfplumber`, `csv_to_pandas`, `url_to_bs4` |
| `modify.*` | Transform objects | `pages`, `limit`, `select`, `crop`, `rotate` |
| `present.*` | Extract content | `text`, `images`, `markdown`, `summary` |
| `refine.*` | Post-process | `truncate`, `add_headers`, `tile_images` |
| `adapt.*` | Format for APIs | `claude`, `openai`, `dspy` |

**Operators**: `|` (sequential), `+` (additive)

---

### Roadmap

Join us – file an issue or open a PR! 🚀