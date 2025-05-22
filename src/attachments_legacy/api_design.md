# Attachments API Design

## Overview

The Attachments library enables intuitive pipeline operations for preparing context attachments for LLMs. Plugins (Loaders, Transformers, Renderers, and Deliverers) are callable, composable, and predictable within pipelines. This document clarifies the pipeline operations and usage scenarios.

## Pipeline Syntax

The pipeline syntax supports:

* **Chaining** (sequential execution): `|`
* **Branching** (parallel execution): `&`

## Plugin Types and Roles

* **Loader**: Loads file content and metadata.
* **Transformer**: Modifies or extracts content (e.g., pages, text selection, translation).
* **Renderer**: Formats the transformed content into specific media types (text, markdown, image tiles).
* **Deliverer**: Converts and packages the output specifically for downstream APIs (OpenAI, Claude).

## Example Pipelines

### Low-Level Usage

```python
from attachments.shorthand import *

"/path/to/sample.pdf" | \
    at_l.load_pdf() | \
    at_t.pages(":2") | \
    (at_rt.pdf() | at_t.summarize_text()) & at_ri.pdf() | \
    at_t.tile_image() | \
    at_d.openai()
```

### Save and Reuse Pipelines

```python
pdf_to_openai = at_l.load_pdf() | \
    at_t.remove_pages() | \
    (at_rt.pdf() | at_t.summarize_text()) & at_ri.pdf() | \
    at_t.tile_image(always=False) | \
    at_d.openai()

pdf_to_openai("/path/sample.pdf[:2 & -5:, tiling=True]")
```

### Pipeline Composition

Pipelines can be composed and conditionally executed based on file matching:

```python
pdf_pipeline = at_l.load_pdf() | at_t.pages() | at_t.regex_filter() | at_t.translate() | \
    (at_rt.pdf() | at_t.summarize_text()) & at_ri.pdf() | at_t.tile_image(always=False)

pptx_md_pipeline = at_l.load_pptx() | at_t.pages() | \
    (at_rt.pptx_md() & at_ri.pptx()) | at_t.tile_image(always=False)

txt_pipeline = at_l.load_txt() | at_rt.txt()

attachments = Attachments(pipelines=[pdf_pipeline, pptx_md_pipeline, txt_pipeline])

all_attachments = attachments(
    "md:/path/sample.pdf[:2 & -5:, tiling=True]",
    "xml:/path/sample.pptx",
    "/path/sample.txt"
)

all_attachments.to_openai()
```

## Plugin Definition

Plugins are defined using Python decorators, ensuring simplicity and consistency:

```python
@loader
def csv_load(path):
    return pd.read_csv(path)

@transformer
def pages(content, indices=":"):
    return content.select_pages(indices)

@renderer
def summarize_text(content):
    return llm_summarizer(content)

@deliverer
def openai(content):
    return format_for_openai(content)
```

## User-Friendly High-Level Interface

```python
from attachments import Attachments

ctx = Attachments(
    "contract.docx",
    "slides.pptx[:3,N]",
    "https://data.csv[summary:true]",
    "diagram.png[rotate:90]"
)

print(ctx)           # formatted text summary
len(ctx.images)      # base64 image list

# Sending to OpenAI
from openai import OpenAI

client = OpenAI()
resp = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=ctx.to_openai("Analyze the following documents:")
)
print(resp.choices[0].message.content)

# Sending to Anthropic (Claude)
import anthropic

msg = anthropic.Anthropic().messages.create(
    model="claude-3-5-haiku-20241022",
    max_tokens=8192,
    messages=ctx.to_claude("Analyze these slides:")
)
print(msg.content)
```

## Advanced Operations

### Image Manipulation

```python
image_pipeline = at_l.load_image() | at_t.rotate(90) | at_t.crop(100, 100, 400, 400) | at_t.tile_image(2, 2)
```

### Selective Text Extraction

```python
text_pipeline = at_l.load_html() | at_t.css_select("#main-content") | at_rt.html()
```

## Target Audience

* Beginners: Can use high-level `Attachments` class directly.
* Intermediate: Define and reuse pipelines easily.
* Advanced: Customize plugins and pipeline compositions deeply.

## Design Principles

* Minimal DSL: Leverage standard Python syntax.
* Intuitive API: Predictable behavior and fluent pipeline interactions.
* Extensibility: Easy plugin definition via decorators.
* IDE-friendly: Autocomplete support for plugins.

## Summary

The Attachments library offers a clean, intuitive, and flexible way to prepare and deliver content attachments to LLM frameworks, supporting diverse file types, transformations, and delivery methods with minimal cognitive overhead for users of all skill levels.
