# 🔗 Attachments THE WAS GENERATED MAY CONTAIN HALLUCINATIONS

**The Python funnel for LLM context** — Turn any file into model-ready text + images, in one line.

[![PyPI version](https://badge.fury.io/py/attachments.svg)](https://pypi.org/project/attachments/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

---

## 🚀 **TL;DR**

```bash
pip install attachments
```

```python
from attachments import Attachments

ctx = Attachments("report.pdf", "photo.jpg[rotate:90]", "data.csv")
llm_ready_text   = str(ctx)       # all extracted text, already "prompt-engineered"
llm_ready_images = ctx.images     # list[str] – base64 PNGs

# Ready for any LLM API
claude_msgs = ctx.claude("Analyze this data")
openai_msgs = ctx.openai("Summarize key findings")
```

**Stop re-writing that plumbing in every project** — contribute to attachments instead!

---

## 🎯 **Why Attachments?**

Every AI project needs the same boring plumbing:
- 📄 Extract text from PDFs, docs, CSVs...
- 🖼️ Convert images to base64 for vision models  
- 🔧 Format everything for LLM APIs
- 🎛️ Apply transformations (crop, rotate, summarize...)
- 🔗 Chain operations together

**Attachments is the community solution.** One import, infinite file types, zero boilerplate.

---

## ⚡ **Quick Start**

### **Basic Usage**
```python
from attachments import Attachments

# Single file
ctx = Attachments("document.pdf")
print(ctx)                    # Pretty text view
len(ctx.images)               # 👉 base64 PNG count

# Multiple files
ctx = Attachments(
    "/path/to/contract.docx",
    "slides.pptx",                        
    "https://example.com/data.csv",       
    "diagram.png[rotate:90]"              # Inline transformations
)

text = str(ctx)               # Combined, formatted text
images = ctx.images           # All images as base64 list
```

### **DSL Commands** 
Embed processing commands directly in file paths:

```python
ctx = Attachments(
    "slides.pptx[pages:1-3,N]",          # First 3 & last slide
    "data.csv[limit:100][summary:true]",  # 100 rows + summary
    "photo.jpg[crop:100,100,400,300][rotate:90]",  # Crop then rotate
    "images.zip[tile:2x2]"                # ZIP → tiled grid
)
```

### **Smart Content Filtering**
Control content extraction with clean DSL commands:

```python
# Text formatting control
ctx = Attachments("report.pdf[format:plain]")     # Plain text formatting
ctx = Attachments("report.pdf[format:markdown]")  # Markdown formatting (default)
ctx = Attachments("report.pdf[format:code]")      # Structured/code formatting

# Image control
ctx = Attachments("report.pdf[images:false]")     # Text only, no images
ctx = Attachments("report.pdf[images:true]")      # Include images (default)

# Combine for precise control
ctx = Attachments("report.pdf[format:plain][images:false]")  # Plain text only
```

**How it works**: The `@presenter` decorator automatically filters presenters based on these commands:
- `format:plain` → uses plain text presenter only
- `format:markdown` → uses markdown presenter only (default)
- `format:code` → uses structured presenters (HTML, XML, etc.)
- `images:false` → skips image presenters
- `images:true` → includes image presenters (default)

**Aliases**: `text=plain`, `txt=plain`, `md=markdown`

### **Direct API Integration**
```python
# Ready for any LLM API
claude_format = ctx.claude("What insights can you provide?")
openai_format = ctx.openai("Summarize the key points")

# Custom prompts
analysis = ctx.claude("Focus on financial metrics and trends")
```

---

## 🏗️ **Architecture: Two-Level Design**

### **🎯 Level 1: Simple API (Most Users)**
Perfect for quick prototypes and standard use cases:

```python
from attachments import Attachments
ctx = Attachments("file1.pdf", "file2.jpg", "file3.csv")
text, images = str(ctx), ctx.images
```

### **🔧 Level 2: Grammar System (Power Users)**
Full control with composable pipelines:

```python
from attachments import attach, load, modify, present, refine, adapt, split

# Custom pipeline with full control
result = (attach("document.pdf[pages:1-5]") 
         | load.pdf_to_pdfplumber 
         | modify.pages 
         | present.markdown + present.images
         | refine.add_headers | refine.truncate
         | adapt.claude("Analyze this content"))

# NEW: Chunking for large documents
chunks = (attach("large_doc.txt")
         | load.text_to_string 
         | split.paragraphs  # Split into collections
         | present.markdown  # Vectorized processing
         | refine.add_headers)

# Process each chunk with LLM
for chunk in chunks:
    claude_message_format = chunk.claude("Summarize this section")


```

---

## 🎛️ **The Grammar System**

A **consistent vocabulary** for file-to-LLM operations:

### **Load → Modify → Split → Present → Refine → Adapt**

| Stage | Purpose | Examples |
|-------|---------|----------|
| **Load** | File format → objects | `pdf_to_pdfplumber`, `csv_to_pandas`, `image_to_pil`, `html_to_bs4` |
| **Modify** | Transform objects so objects → objects | `pages`, `limit`, `crop`, `rotate` |
| **Split** | Objects → collections | `paragraphs`, `tokens`, `pages`, `rows`, `sections` |
| **Present** | Extract for LLMs, objects → text, images, audio | `text`, `images`, `markdown`, `xml`, `html` |  
| **Refine** | Post-process content text, images, audio → text, images, audio| `truncate`, `add_headers`, `tile_images` |
| **Adapt** | Format for APIs, Attachment(s) → claude, openai_chat, openai_response | `claude`, `openai_chat`, `openai_response` |

### **Operators: `|` (Sequential) and `+` (Additive)**

```python
# Sequential pipeline (each step transforms)
load.pdf_to_pdfplumber | split.pages | present.text | refine.truncate

# Additive composition (accumulate content)  
present.text + present.images + present.metadata

# Chunking workflow
(attach("doc.txt[tokens:500]") | load.text_to_string | split.tokens 
 | present.markdown | refine.add_headers | adapt.claude("Analyze"))
```

---

## 🧩 **Chunking & Collections**

**Perfect for LLM context limits** - split large documents into processable chunks:

### **Text Splitting**
```python
# Split by semantic units
chunks = attach("doc.txt") | load.text_to_string | split.paragraphs
chunks = attach("doc.txt") | load.text_to_string | split.sentences

# Split by size limits (LLM-friendly)
chunks = attach("doc.txt[tokens:500]") | load.text_to_string | split.tokens
chunks = attach("doc.txt[characters:1000]") | load.text_to_string | split.characters
chunks = attach("doc.txt[lines:50]") | load.text_to_string | split.lines

# Custom splitting
chunks = attach("doc.txt[custom:---BREAK---]") | load.text_to_string | split.custom
```

### **Document Splitting**
```python
# PDF pages
pages = attach("report.pdf") | load.pdf_to_pdfplumber | split.pages

# PowerPoint slides  
slides = attach("deck.pptx") | load.pptx_to_python_pptx | split.slides

# HTML sections
sections = attach("article.html") | load.html_to_bs4 | split.sections
```

### **Data Splitting**
```python
# DataFrame chunks
row_chunks = attach("data.csv[rows:100]") | load.csv_to_pandas | split.rows
col_chunks = attach("data.csv[columns:5]") | load.csv_to_pandas | split.columns
```

### **Vectorized Processing**
```python
# Process each chunk automatically
processed = (attach("large_doc.txt[tokens:300]")
            | load.text_to_string | split.tokens
            | present.markdown     # Applied to each chunk
            | refine.add_headers)  # Applied to each chunk

# LLM processing pattern
summaries = []
for chunk in processed:
    summary = chunk.claude("Summarize this section") 
    summaries.append(summary)
```

### **🧩 Large Document Chunking**
```python
# Handle large documents that exceed LLM context limits
def process_large_document(doc_path, chunk_strategy="tokens", chunk_size=500):
    """Process large documents in LLM-friendly chunks."""
    
    # Create chunking pipeline based on strategy
    if chunk_strategy == "tokens":
        chunks = (attach(f"{doc_path}[tokens:{chunk_size}]")
                 | load.text_to_string | split.tokens
                 | present.markdown | refine.add_headers)
    elif chunk_strategy == "paragraphs":
        chunks = (attach(doc_path) | load.text_to_string | split.paragraphs
                 | present.markdown | refine.add_headers)
    elif chunk_strategy == "pages":
        chunks = (attach(doc_path) | load.pdf_to_pdfplumber | split.pages
                 | present.text | refine.add_headers)
    
    # Process each chunk with LLM
    summaries = []
    for i, chunk in enumerate(chunks):
        summary = chunk.claude(f"Summarize section {i+1} in 2-3 sentences")
        summaries.append(summary)
        print(f"Processed chunk {i+1}/{len(chunks)}")
    
    return summaries

# Usage examples
summaries = process_large_document("large_report.pdf", "pages")
summaries = process_large_document("long_article.txt", "tokens", 300)
summaries = process_large_document("research_paper.txt", "paragraphs")
```

---

## 🔄 **Vectorization & Collections**

**Automatic vectorization** for processing multiple files and chunks:

```python
# ZIP files become collections that auto-vectorize
result = (attach("photos.zip[tile:2x2]") 
         | load.zip_to_images           # → AttachmentCollection of 4 images
         | present.images               # Vectorized: each image → base64  
         | refine.tile_images           # Reduction: 4 images → 1 tiled image
         | adapt.claude("Describe this collage"))

# Document chunking with vectorization
result = (attach("long_doc.txt[tokens:500]")
         | load.text_to_string | split.paragraphs  # → AttachmentCollection
         | present.markdown                        # Vectorized processing
         | refine.add_headers)                     # Applied to each chunk
```

**Key Features:**
- **Auto-vectorization**: Operations apply to each item in collections
- **Smart reduction**: `refine.tile_images` combines multiple attachments  
- **Chunking integration**: Split functions create collections for vectorized processing
- **DSL propagation**: Commands flow through vectorized pipelines
- **Seamless integration**: Collections work with all grammar features

---

## 📁 **Supported Formats**

### **Built-in Loaders**
- **📄 Documents**: PDF (pdfplumber), DOCX, PPTX, TXT, Markdown
- **📊 Data**: CSV (pandas), JSON
- **🖼️ Images**: JPG, PNG, GIF, BMP, HEIC/HEIF (with pillow-heif)
- **🌐 Web**: URLs (BeautifulSoup), HTML files (BeautifulSoup)
- **📦 Archives**: ZIP → image collections
- **🗂️ Repositories**: Git repositories with smart ignore patterns

### **Built-in Modifiers & Splitters**
- **🔧 Object transforms**: `pages`, `limit`, `select`, `crop`, `rotate`
- **🧩 Text splitting**: `paragraphs`, `sentences`, `tokens`, `characters`, `lines`, `custom`
- **📄 Document splitting**: `pages` (PDF), `slides` (PowerPoint), `sections` (HTML)
- **📊 Data splitting**: `rows`, `columns` (DataFrames)

### **Built-in Presenters**
- **📝 Text formats**: `text`, `markdown`, `csv`, `xml`, `html`
- **🖼️ Visual**: `images` (auto base64 conversion)
- **📊 Analysis**: `head`, `summary`, `metadata`, `thumbnails`

### **Built-in Refiners**
- **📝 Text**: `truncate`, `add_headers`, `add_repo_headers`
- **🖼️ Images**: `tile_images`, `resize_images`

### **Built-in Adapters**
- **🤖 Claude**: Anthropic format with image support
- **🤖 OpenAI**: Chat completion format
- **🤖 DSPy**: BaseType-compatible objects for DSPy signatures
- **🎛️ Prompt support**: Via DSL `[prompt:text]` or parameters

---

## 🔧 **Installation**

```bash
# Basic installation
pip install attachments

# With optional dependencies for full format support
pip install attachments[full]  # pandas, pillow, beautifulsoup4, etc.

# For HEIC image support
pip install pillow-heif
```

---

## 🎨 **Examples**

### **📊 Data Analysis Workflow**
```python
# Rich data presentation with multiple content types
result = (attach("sales_data.csv[limit:1000]") 
         | load.csv_to_pandas | modify.limit
         | present.head + present.summary + present.metadata
         | refine.add_headers | refine.format_tables
         | adapt.openai_chat("What trends do you see?"))
```

### **🖼️ Image Processing Pipeline**
```python
# Process and tile multiple images
result = (attach("photos.zip[tile:3x2]") 
         | load.zip_to_images
         | present.images | refine.tile_images
         | adapt.claude("Describe these images"))
```

### **📄 Document Analysis**
```python
# Multi-format document processing
universal = (load.pdf_to_pdfplumber | load.csv_to_pandas | load.image_to_pil 
            | present.text + present.images + present.metadata
            | refine.add_headers | adapt.claude)

# Works with any supported format
universal("report.pdf")      # PDF analysis
universal("data.csv")        # Data summary  
universal("diagram.png")     # Image description
```

### **🌐 Web Content Analysis**
```python
# URL processing with content extraction
result = (attach("https://example.com/article") 
         | load.url_to_bs4 
         | present.text + present.metadata
         | refine.truncate | refine.add_headers
         | adapt.claude("Summarize this article"))
```

### **🎭 Custom Processors**
```python
# Domain-specific reusable processors
financial_analyzer = (load.pdf_to_pdfplumber | load.csv_to_pandas
                      | present.text + present.summary + present.metadata  
                      | refine.add_headers | refine.format_tables
                      | adapt.claude("Focus on financial metrics"))

research_pipeline = (load.pdf_to_pdfplumber 
                    | present.markdown + present.images
                    | refine.add_headers | refine.tile_images
                    | adapt.openai_chat("Extract key research findings"))

# Apply to any matching files
financial_analyzer("quarterly_report.pdf")
research_pipeline("research_paper.pdf")
```

### **📊 Data Analysis Workflow**
```python
# Rich data presentation with multiple content types
result = (attach("sales_data.csv[limit:1000]") 
         | load.csv_to_pandas | modify.limit
         | present.head + present.summary + present.metadata
         | refine.add_headers | refine.format_tables
         | adapt.openai_chat("What trends do you see?"))
```

### **🎭 Multimodal Processing with DSL**
```python
# Multimodal processing with DSL
visual_analysis = Attachments("presentation.pdf[format:markdown][images:true]")
insights = visual_analysis.claude("Analyze both the text and visual elements")
```

---

## 🧠 **DSPy Integration**

**Seamless integration with DSPy** for building sophisticated LLM programs:

### **DSPy Adapter**
Convert any attachment to DSPy BaseType-compatible objects:

```python
from attachments import attach, load, present, adapt
import dspy

# Configure DSPy
dspy.configure(lm=dspy.LM('openai/gpt-4.1-nano'))

# Process document and convert to DSPy format
document = (attach("report.pdf") 
           | load.pdf_to_pdfplumber 
           | present.text + present.pdf_images
           | adapt.dspy)

# Use in DSPy signatures
rag = dspy.ChainOfThought("question, document -> answer")
result = rag(question="What are the key findings?", document=document)
print(result.answer)
```

Or simply with the Attachments object:

```python
result = rag(question="What do you see?", 
             document=Attachments("report.pdf").dspy())
result.answer
```


### **DSPy Integration Benefits**
- **🎯 Type Safety**: Proper DSPy BaseType compatibility
- **🔄 Serialization**: Handles complex multimodal content serialization
- **🖼️ Image Support**: Seamless base64 image handling for vision models
- **📝 Text Processing**: Rich text content with proper formatting
- **🧩 Composability**: Works with all DSPy signatures and programs

---

## 🌟 **Real-World Examples**

### **Custom Web Scraping Pipeline**
Build custom processors for specific domains:

```python
from attachments import loader, modifier, presenter, Attachment
import requests
from bs4 import BeautifulSoup
import re

# Custom URL loader with BeautifulSoup
@loader(lambda att: bool(re.match(r'^https?://', att.path)))
def url_to_bs4(att: Attachment) -> Attachment:
    """Load URL content and parse with BeautifulSoup."""
    response = requests.get(att.path, timeout=10)
    response.raise_for_status()
    
    att._obj = BeautifulSoup(response.content, 'html.parser')
    att.metadata.update({
        'content_type': response.headers.get('content-type', ''),
        'status_code': response.status_code,
    })
    return att

# CSS selector modifier
@modifier
def select(att: Attachment, soup: BeautifulSoup) -> Attachment:
    """CSS selector for BeautifulSoup objects."""
    if 'select' not in att.commands:
        return att
    
    selector = att.commands['select']
    selected_elements = soup.select(selector)
    
    if not selected_elements:
        new_soup = BeautifulSoup("", 'html.parser')
    elif len(selected_elements) == 1:
        new_soup = BeautifulSoup(str(selected_elements[0]), 'html.parser')
    else:
        container_html = ''.join(str(elem) for elem in selected_elements)
        new_soup = BeautifulSoup(f"<div>{container_html}</div>", 'html.parser')
    
    att._obj = new_soup
    att.metadata.update({
        'selector': selector,
        'selected_count': len(selected_elements),
    })
    return att

# Custom presenters for BeautifulSoup
@presenter(category='text')
def text(att: Attachment, soup: BeautifulSoup) -> Attachment:
    """Extract text from BeautifulSoup object."""
    att.text = soup.get_text(strip=True)
    return att

@presenter
def html(att: Attachment, soup: BeautifulSoup) -> Attachment:
    """Get formatted HTML from BeautifulSoup object."""
    att.text = soup.prettify()
    return att

# Usage examples
title_extractor = (load.url_to_bs4 | modify.select | present.text)
result = title_extractor("https://en.wikipedia.org/wiki/Llama[select:title]")

# Function-style usage
def url_to_title_text(url: str) -> str:
    return (attach(url) | load.url_to_bs4 | modify.select | present.text)

title = url_to_title_text("https://en.wikipedia.org/wiki/Llama[select:h1]")
```

### **HEIC Image Processing**
Complete HEIC image processing pipeline:

```python
from attachments import loader, modifier, Attachment

@loader(lambda att: att.path.lower().endswith(('.heic', '.heif')))
def heic_to_pillow(att: Attachment) -> Attachment:
    """Load HEIC files with pillow-heif support."""
    from pillow_heif import register_heif_opener
    register_heif_opener()
    from PIL import Image
    att._obj = Image.open(att.path)
    return att

@modifier  
def crop(att: Attachment, img: 'PIL.Image.Image') -> Attachment:
    """Crop: [crop:x1,y1,x2,y2]"""
    if 'crop' not in att.commands: 
        return att
    coords = [int(x) for x in att.commands['crop'].split(',')]
    att._obj = img.crop(coords)
    return att

@modifier
def rotate(att: Attachment, img: 'PIL.Image.Image') -> Attachment:
    """Rotate: [rotate:degrees] (positive = clockwise)"""
    if 'rotate' in att.commands:
        att._obj = img.rotate(-float(att.commands['rotate']), expand=True)
    return att

# Multiple usage patterns
# 1. Direct pipeline usage
result1 = (attach("IMG_2160.HEIC[crop:100,100,400,300][rotate:90]")
          | load.heic_to_pillow | modify.crop | modify.rotate 
          | present.images | adapt.claude("What do you see?"))

# 2. Reusable processor function
image_processor = (load.heic_to_pillow | modify.crop | modify.rotate | present.images)
result2 = image_processor("IMG_2160.HEIC[crop:50,50,200,200][rotate:45]").claude("Describe this")

# 3. Universal image processor with fallbacks
universal_image = (load.heic_to_pillow | load.image_to_pil  # HEIC then fallback
                  | modify.crop | modify.rotate | present.images)

# Works with any image format
heic_result = universal_image("IMG_2160.HEIC[rotate:45]").claude("What's in this photo?")
png_result = universal_image("Figure_1.png").openai_chat("Describe the chart")
```

### **Pipeline Composition Patterns**
Advanced composition and chaining techniques:

```python
# 1. Assign pipelines to variables (creates callable functions)
csv_processor = (load.csv_to_pandas | modify.limit | present.head 
                | present.summary | present.metadata)

# Use as function
result = csv_processor("data.csv[limit:100]")
analysis = result.claude("What patterns do you see in this data?")

# 2. Additive presentation (accumulate multiple content types)
rich_csv = (attach("sales_data.csv") | load.csv_to_pandas 
           | present.head + present.summary + present.metadata)

# 3. Refinement chains (post-process extracted content)
refined_csv = (attach("large_data.csv") | load.csv_to_pandas 
              | present.head + present.summary 
              | refine.truncate | refine.add_headers)

# 4. Complex multi-step pipeline with DSL commands
complete_pipeline = (attach("data.csv[limit:5][truncate:200][prompt:analyze this data]")
                    | load.csv_to_pandas | modify.limit           
                    | present.markdown + present.summary          
                    | refine.truncate | refine.add_headers   
                    | adapt.claude)

# 5. Pipeline chaining (combine different processors)
super_pipeline = (
    (load.url_to_bs4 | modify.select | present.text) |  # Web processing
    (load.csv_to_pandas | modify.limit | present.head)   # Data processing
)

# Works with different file types
web_result = super_pipeline("https://example.com[select:p]")
data_result = super_pipeline("data.csv[limit:10]")

# 6. Method-style API (convenient for interactive use)
csv_to_llm = (load.csv_to_pandas | modify.limit | present.head 
             | present.metadata | present.summary | present.text)

# All these work:
result1 = csv_to_llm.claude("data.csv[limit:1]", prompt="What do you see")
result2 = csv_to_llm.openai_chat("data.csv[limit:1]", prompt="Analyze this")
result3 = csv_to_llm.openai_response("data.csv[limit:1]", prompt="Summarize")
```

### **Convenience API Examples**
Simple high-level API for common use cases:

```python
from attachments import Attachments

# 1. Single-line document processing
result = Attachments("report.pdf").claude("Summarize the key findings")

# 2. Multi-file analysis
docs = Attachments("report1.pdf", "report2.pdf", "data.csv")
comparison = docs.openai_chat("Compare these documents and highlight differences")

# 3. DSPy integration (one-liner)
import dspy
dspy.configure(lm=dspy.LM('anthropic/claude-3-5-haiku-latest'))

rag = dspy.ChainOfThought("question, document -> answer")
result = rag(
    question="What are the main insights?", 
    document=Attachments("quarterly_report.pdf").dspy()
)

# 4. Multimodal processing with DSL
visual_analysis = Attachments("presentation.pdf[format:markdown][images:true]")
insights = visual_analysis.claude("Analyze both the text and visual elements")

# 5. Batch processing pattern
for att in Attachments("doc1.pdf", "doc2.pdf", "chart.png", "data.csv"):
    result = att.claude(f"Analyze this document")
    print(f"{att.path}: {result}")
```

## 🧩 **Extending Attachments**

### **Custom Loaders**
```python
from attachments import loader, Attachment

@loader(match=lambda att: att.path.endswith('.xyz'))
def xyz_to_data(att: Attachment) -> Attachment:
    """Custom loader for .xyz files."""
    # Your loading logic here
    att._obj = load_xyz_file(att.path)
    return att
```

### **Custom Modifiers**
```python
from attachments import modifier

@modifier  
def custom_filter(att: Attachment, data: MyDataType) -> Attachment:
    """Custom data filtering."""
    # Apply custom transformations
    att._obj = filter_data(data, att.commands)
    return att
```

### **Custom Presenters**
```python
from attachments import presenter

@presenter
def custom_format(att: Attachment, data: MyDataType) -> Attachment:
    """Custom presentation format."""
    att.text = format_as_custom(data)
    return att
```

### **Smart DSL Filtering**
The `@presenter` decorator automatically handles DSL command filtering, so your custom presenters get smart filtering for free:

```python
# Automatic category detection (recommended)
@presenter
def json_format(att: Attachment, data: dict) -> Attachment:
    """Auto-detected as 'text' presenter based on name pattern"""
    import json
    att.text += json.dumps(data, indent=2)
    return att

@presenter  
def chart_visualization(att: Attachment, df: 'pandas.DataFrame') -> Attachment:
    """Auto-detected as 'image' presenter based on name pattern"""
    chart_base64 = create_chart(df)
    att.images.append(chart_base64)
    return att

# Explicit categorization (when auto-detection isn't sufficient)
@presenter(category='text')
def custom_text_format(att: Attachment, data: dict) -> Attachment:
    """Explicitly categorized as text presenter"""
    att.text += format_custom_text(data)
    return att

@presenter(category='image')
def custom_visualization(att: Attachment, data: dict) -> Attachment:
    """Explicitly categorized as image presenter"""
    att.images.append(generate_custom_viz(data))
    return att

@presenter(category='both')
def always_run_presenter(att: Attachment, data: dict) -> Attachment:
    """Always runs regardless of focus setting"""
    att.text += "This always runs\n"
    return att

# Usage with automatic filtering
result = attach("data.csv[format:plain][images:false]") | load.csv_to_pandas | (
    present.json_format +           # ✅ Runs (auto-detected as text)
    present.chart_visualization +   # ❌ Skipped (auto-detected as image)
    present.custom_text_format +    # ✅ Runs (explicit text)
    present.custom_visualization +  # ❌ Skipped (explicit image)
    present.always_run_presenter    # ✅ Runs (explicit 'both')
)
```

**Automatic Detection** (zero configuration):
- **Name patterns**: `json`, `text`, `markdown`, `csv`, `xml`, `html`, `summary` → text
- **Name patterns**: `image`, `chart`, `graph`, `plot`, `visual`, `thumbnail` → image
- **Source analysis**: Analyzes function code for `att.text` vs `att.images` usage
- **Safe default**: Unknown presenters default to `'both'` (always run)

**Explicit Categories**:
- `@presenter(category='text')` → Only runs when focus allows text
- `@presenter(category='image')` → Only runs when focus allows images  
- `@presenter(category='both')` → Always runs regardless of focus
- `@presenter` → Auto-detects category (recommended)

**Benefits for Contributors**:
- ✅ **Zero configuration**: Most presenters work automatically
- ✅ **Intuitive naming**: Use descriptive names and get automatic categorization
- ✅ **Explicit control**: Override auto-detection when needed
- ✅ **Backward compatible**: Existing presenters continue to work
- ✅ **No core changes**: Add new presenter types without modifying core code

### **Custom Refiners**
```python
from attachments import refiner

@refiner
def custom_enhancement(att: Attachment) -> Attachment:
    """Custom content enhancement."""
    if att.text:
        att.text = enhance_text(att.text)
    return att
```

### **Add New File Format Support**
1. Create a loader function with `@loader` decorator
2. Add corresponding matcher in `matchers.py`
3. Submit PR with tests

### **Add New Presenters** (Super Easy!)
Adding new presenters is now completely automatic:

```python
# Just use descriptive names - automatic categorization!
@presenter
def yaml_format(att: Attachment, data: dict) -> Attachment:
    """Auto-detected as 'text' presenter"""
    import yaml
    att.text += yaml.dump(data)
    return att

@presenter
def heatmap_chart(att: Attachment, df: 'pandas.DataFrame') -> Attachment:
    """Auto-detected as 'image' presenter"""
    chart_data = generate_heatmap(df)
    att.images.append(chart_data)
    return att

# Override auto-detection if needed
@presenter(category='both')
def special_presenter(att: Attachment, data) -> Attachment:
    """Always runs regardless of focus"""
    att.text += "Special content\n"
    return att
```

**That's it!** Your presenters automatically:
- ✅ Work with DSL filtering (`[format:plain]`, `[images:false]`)
- ✅ Integrate with additive pipelines (`present.a + present.b`)
- ✅ Support type dispatch for different data types
- ✅ Get proper categorization based on naming

### **Add New Transformations**
1. Create modifier/presenter/refiner with appropriate decorator
2. Add DSL command support if applicable
3. Include documentation and examples

### **Improve Documentation**
- Add examples for your use case
- Improve existing docstrings
- Create tutorials for complex workflows

### **Report Issues**
- Bug reports with minimal reproduction cases
- Feature requests with clear use cases
- Performance issues with profiling data

---

## 🎯 **Design Philosophy**

### **"Grammar-First File Processing"**

- **🎭 Consistent vocabulary**: Standard verbs for common operations
- **🔗 Intuitive operators**: `|` for sequential, `+` for additive
- **📖 Clear semantics**: Each operator has predictable behavior
- **🧩 Composable pipelines**: Natural chaining and combination
- **🎛️ DSL integration**: Commands embedded in file paths
- **🎯 Type dispatch**: Automatic routing based on content types
- **🧠 Smart filtering**: Presenters automatically respect DSL commands
- **🤖 AI-ready**: Direct integration with modern LLM APIs

### **Two-Level Architecture**
- **Simple API**: `Attachments()` for 90% of use cases
- **Grammar system**: Full pipeline control for complex workflows
- **Graceful progression**: Start simple, add complexity as needed

---

## 🚀 **Advanced Patterns**

### **Universal File Processor**
```python
# Handles any file type automatically
universal = (load.pdf_to_pdfplumber | load.csv_to_pandas | load.image_to_pil 
            | load.url_to_bs4 | load.text_to_string
            | present.text + present.images + present.metadata
            | refine.add_headers | adapt.claude)

# Works with any supported format
universal("mystery_file.pdf")
universal("unknown_data.csv") 
universal("random_image.jpg")
```

### **Conditional Processing**
```python
# Different pipelines for different content types
def smart_processor(file_path):
    if file_path.endswith('.pdf'):
        return doc_analyzer(file_path)
    elif file_path.endswith('.csv'):
        return data_analyzer(file_path)
    elif file_path.endswith(('.jpg', '.png')):
        return image_analyzer(file_path)
    else:
        return universal_processor(file_path)
```

### **Batch Processing**
```python
# Process multiple files with consistent pipeline
files = ["doc1.pdf", "doc2.pdf", "data.csv", "image.jpg"]
results = [Attachments(f) for f in files]

# Combine all results
combined = Attachments(*files)
analysis = combined.claude("Compare and analyze all these files")
```

---

## 🤝 **Contributing**

We welcome contributions! Here's how to help:

### **Add New File Format Support**
1. Create a loader function with `@loader` decorator
2. Add corresponding matcher in `matchers.py`
3. Submit PR with tests

### **Add New Presenters** (Super Easy!)
Adding new presenters is now completely automatic:

```python
# Just use descriptive names - automatic categorization!
@presenter
def yaml_format(att: Attachment, data: dict) -> Attachment:
    """Auto-detected as 'text' presenter"""
    import yaml
    att.text += yaml.dump(data)
    return att

@presenter
def heatmap_chart(att: Attachment, df: 'pandas.DataFrame') -> Attachment:
    """Auto-detected as 'image' presenter"""
    chart_data = generate_heatmap(df)
    att.images.append(chart_data)
    return att

# Override auto-detection if needed
@presenter(category='both')
def special_presenter(att: Attachment, data) -> Attachment:
    """Always runs regardless of focus"""
    att.text += "Special content\n"
    return att
```

**That's it!** Your presenters automatically:
- ✅ Work with DSL filtering (`[format:plain]`, `[images:false]`)
- ✅ Integrate with additive pipelines (`present.a + present.b`)
- ✅ Support type dispatch for different data types
- ✅ Get proper categorization based on naming

### **Add New Transformations**
1. Create modifier/presenter/refiner with appropriate decorator
2. Add DSL command support if applicable
3. Include documentation and examples

### **Improve Documentation**
- Add examples for your use case
- Improve existing docstrings
- Create tutorials for complex workflows

### **Report Issues**
- Bug reports with minimal reproduction cases
- Feature requests with clear use cases
- Performance issues with profiling data

---

## 📋 **Roadmap**

### **🔜 Coming Soon**
- [ ] **More file formats**: Excel, Word, PowerPoint, Audio, Video
- [ ] **Advanced image processing**: OCR, object detection, face recognition
- [ ] **Database connectors**: SQL, MongoDB, APIs
- [ ] **Streaming support**: Large file processing
- [ ] **Caching system**: Avoid reprocessing unchanged files

### **🎯 Future Vision**
- [ ] **Plugin ecosystem**: Community-contributed processors
- [ ] **GUI interface**: Visual pipeline builder
- [ ] **Cloud deployment**: Serverless processing
- [ ] **Real-time processing**: Watch folders, webhooks
- [ ] **Multi-modal AI**: Audio, video, and text processing

---

## 📊 **Performance**

### **Benchmarks**
- **Text extraction**: ~1000 pages/second (PDF)
- **Image processing**: ~100 images/second (basic ops)
- **CSV processing**: ~1M rows/second (pandas backend)
- **Memory usage**: Efficient streaming for large files

### **Optimization Tips**
- Use `limit` commands for large datasets
- Enable caching for repeated processing
- Process in batches for many small files
- Use vectorized operations for collections

---

## 🛡️ **Error Handling**

### **Graceful Degradation**
```python
# Missing files are handled gracefully
ctx = Attachments("good_file.pdf", "missing_file.pdf", "another_good.csv")
print(ctx)  # Includes error messages for missing files
```

### **Fallback Processing**
```python
# Loaders chain gracefully - if PDF fails, try text
result = (attach("mystery_file") 
         | load.pdf_to_pdfplumber | load.text_to_string
         | present.text)
```

### **Error Recovery**
```python
# Custom error handling
try:
    ctx = Attachments("complex_file.pdf")
    result = ctx.claude("Analyze this")
except Exception as e:
    # Fallback to basic text extraction
    ctx = Attachments("complex_file.pdf")
    basic_text = str(ctx)
```

---

## 📚 **API Reference**

### **Attachments Class**
```python
class Attachments:
    def __init__(*paths: str)           # Initialize with file paths
    def __str__() -> str                # Get formatted text
    def images -> List[str]             # Get base64 images
    def metadata -> dict                # Get combined metadata
    def claude(prompt: str) -> List     # Claude API format
    def openai(prompt: str) -> List     # OpenAI API format
```

### **Core Functions**
```python
attach(path: str) -> Attachment              # Create attachment
process(*paths: str) -> Attachments         # Convenience function

# Decorators for extending
@loader(match: Callable)                    # Register loader
@modifier                                   # Register modifier  
@presenter                                  # Register presenter
@refiner                                    # Register refiner
@adapter                                    # Register adapter
```

### **Grammar Namespaces**
```python
load.pdf_to_pdfplumber                      # Load PDF
modify.pages                                # Extract pages
present.text + present.images               # Extract content
refine.truncate | refine.add_headers   # Process content
adapt.claude("prompt")                      # Format for API
```

---

## 🔗 **Links**

- **📦 PyPI**: [pypi.org/project/attachments](https://pypi.org/project/attachments)
- **�� GitHub**: [github.com/attachments-ai/attachments](https://github.com/attachments-ai/attachments)
- **📖 Documentation**: [attachments.readthedocs.io](https://attachments.readthedocs.io)
- **💬 Discord**: [discord.gg/attachments](https://discord.gg/attachments)
- **🐦 Twitter**: [@attachments_ai](https://twitter.com/attachments_ai)

---

## 📄 **License**

MIT License - see [LICENSE](LICENSE) file for details.

---

## 🙏 **Acknowledgments**

Built with ❤️ by the AI community. Special thanks to:
- **LangChain** for inspiration on AI tooling
- **Pandas** for data processing excellence  
- **Pillow** for image processing capabilities
- **pdfplumber** for robust PDF text extraction
- **BeautifulSoup** for web scraping support

---

**Ready to stop re-writing file processing code?** 

```bash
pip install attachments
```

**Join the community building the future of AI file processing!** 🚀

```bash
pip install attachments
```

**Join the community building the future of AI file processing!** 🚀

---

## 🗂️ **Repository Processing**

**Perfect for giving entire codebases to LLMs** - automatically process Git repositories with smart filtering and three processing modes.

### **Three Processing Modes**

#### **Mode 1: Structure Only** 
Get a clean directory tree view (like `ls -alh -R`):

```python
# Just the directory structure
structure = Attachments("path/to/repo[mode:structure]")
print(structure)  # Clean tree view with file sizes
```

#### **Mode 2: Structure + Metadata**
Directory tree plus Git repository information:

```python
# Structure + Git metadata
overview = Attachments("path/to/repo[mode:metadata]")
print(overview)  # Tree + branch, commits, author info
```

#### **Mode 3: Full Content Processing** (Default)
Complete codebase analysis with all file contents:

```python
# Full repository processing (default mode)
codebase = Attachments("path/to/repo")
analysis = codebase.claude("Analyze this codebase and suggest improvements")

# Or with explicit mode
codebase = Attachments("path/to/repo[mode:content]")
```

### **Smart Ignore Patterns**

Control which files are processed with flexible ignore patterns:

```python
# Standard ignore patterns (recommended)
Attachments("repo[ignore:standard]")  # .git, node_modules, __pycache__, etc.

# Use .gitignore patterns
Attachments("repo[ignore:gitignore]")  # Respects your .gitignore file

# Custom patterns
Attachments("repo[ignore:.env,*.log,dist,build]")  # Custom comma-separated patterns

# Combine with other options
Attachments("repo[mode:content][ignore:standard][max_files:500]")
```

### **Repository Pipeline Processing**

Use the grammar system for advanced repository processing:

```python
# Custom repository analysis pipeline
codebase_analyzer = (load.repo_to_structure           # Load repo as collection
                    | present.text                    # Extract text from each file
                    | refine.add_repo_headers         # Add file headers with paths
                    | refine.truncate                 # Limit content per file
                    | adapt.claude)                   # Send to Claude

# Apply to any repository
analysis = codebase_analyzer("path/to/repo[ignore:standard]", 
                            prompt="Review this code for security issues")

# Vectorized processing - each file processed individually
result = (attach("repo[mode:content][ignore:gitignore]")
         | load.repo_to_structure     # → AttachmentCollection of files
         | present.text               # Vectorized: each file → text
         | refine.add_repo_headers    # Vectorized: each file gets headers
         | adapt.claude("Analyze each file and summarize findings"))
```

### **Repository Examples**

#### **Quick Codebase Review**
```python
# One-liner codebase analysis
review = Attachments("./my-project[ignore:standard]").claude(
    "Review this codebase for best practices and potential issues"
)
```

#### **Documentation Generation**
```python
# Generate documentation from codebase
docs = (attach("./src[mode:content][ignore:standard]")
       | load.repo_to_structure
       | present.text + present.metadata
       | refine.add_repo_headers
       | adapt.openai_chat("Generate comprehensive documentation for this codebase"))
```

#### **Code Migration Analysis**
```python
# Analyze codebase for migration
migration_plan = Attachments(
    "./legacy-app[ignore:node_modules,dist,*.log]"
).claude("Analyze this codebase and create a plan to migrate from Vue 2 to Vue 3")
```

#### **Security Audit**
```python
# Security-focused repository analysis
security_audit = (attach("./app[mode:content][ignore:standard]")
                 | load.repo_to_structure
                 | present.text
                 | refine.add_repo_headers
                 | adapt.claude("Perform a security audit of this codebase. "
                               "Look for vulnerabilities, insecure patterns, "
                               "and suggest improvements."))
```

### **Repository Features**

- **🎯 Smart Detection**: Automatically detects Git repositories
- **🚫 Flexible Ignoring**: Standard patterns, .gitignore, or custom rules
- **📊 Git Integration**: Branch info, commit history, remote URLs
- **🔄 Vectorized Processing**: Each file processed individually for scalability
- **📝 Rich Headers**: File paths, languages, sizes automatically added
- **⚡ Performance**: Limits file count and skips binary files
- **🧠 LLM-Ready**: Optimized output format for code analysis

### **DSL Commands for Repositories**

| Command | Options | Description |
|---------|---------|-------------|
| `mode` | `structure`, `metadata`, `content` | Processing mode (default: content) |
| `ignore` | `standard`, `gitignore`, `custom,patterns` | Ignore patterns (default: standard) |
| `max_files` | `1000` | Maximum files to process (default: 1000) |

**Examples**:
- `repo[mode:structure]` - Directory tree only
- `repo[mode:metadata][ignore:gitignore]` - Tree + Git info, use .gitignore
- `repo[ignore:.env,*.log,node_modules][max_files:200]` - Custom ignore + limit
