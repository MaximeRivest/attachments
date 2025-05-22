# Attachments Library API Design Specification

## Overview

The Attachments library facilitates intuitive, composable pipeline operations to prepare context-rich attachments for large language models (LLMs). It achieves this through callable function groups: Loaders, Transformers, Renderers, and Deliverers—that interact seamlessly via pipeline operations.

## Pipeline Syntax

Pipeline syntax enables chaining and branching operations:

* **Chaining** (sequential): `|`
* **Branching** (parallel): `&`

Parentheses around functions are optional when no arguments are required, improving readability:

```python
path | at_l.load_pdf | at_t.pages(':2') | at_rt.pdf & at_ri.pdf | at_d.openai
```

## Plugin Types and Responsibilities

### 1. Loaders

* **Purpose**: Identify compatible file types and load content and metadata.
* **Decorator**: `@loader(match=<match_function>)`

  * The `match` function determines if the loader applies to a given input path or URL.

### 2. Transformers

* **Purpose**: Modify, filter, or extract specific content (e.g., selecting pages, translating).
* **Decorator**: `@transformer`

### 3. Renderers

* **Purpose**: Convert transformed content into specific formats (e.g., plain text, markdown, images).
* **Decorator**: `@renderer`

### 4. Deliverers

* **Purpose**: Package content for downstream APIs (OpenAI, Claude).
* **Decorator**: `@deliverer`

## Plugin Definition and Matching Logic

Each Loader explicitly defines a matching logic:

```python
@loader(match=lambda path: path.endswith('.csv'))
def csv_loader(path):
    return pd.read_csv(path)

@loader(match=lambda path: path.endswith('.pdf'))
def pdf_loader(path):
    return PyPDFLoader(path)
```

During pipeline execution, if a Loader’s `match` returns `False`, the pipeline automatically continues to the next compatible Loader.

## Example Pipelines

### Low-Level Usage

```python
from attachments.shorthand import *

"/path/sample.pdf" | at_l.load_pdf | at_t.pages(':2') | (at_rt.pdf | at_t.summarize_text) & at_ri.pdf | at_t.tile_image | at_d.openai
```

### Saving and Reusing Pipelines

```python
pdf_to_openai = (
    at_l.load_pdf |
    at_t.remove_pages |
    (at_rt.pdf | at_t.summarize_text) & at_ri.pdf |
    at_t.tile_image(always=False) |
    at_d.openai
)

pdf_to_openai("/path/sample.pdf[:2 & -5:, tiling=True]")
```

### Composable Pipelines

```python
pdf_pipeline = (
    at_l.load_pdf |
    at_t.pages |
    at_t.regex_filter |
    at_t.translate |
    (at_rt.pdf | at_t.summarize_text) & at_ri.pdf |
    at_t.tile_image(always=False)
)

pptx_md_pipeline = (
    at_l.load_pptx |
    at_t.pages |
    at_rt.pptx_md & at_ri.pptx |
    at_t.tile_image(always=False)
)

txt_pipeline = at_l.load_txt | at_rt.txt

attachments = Attachments([pdf_pipeline, pptx_md_pipeline, txt_pipeline])

all_attachments = attachments(
    "md:/path/sample.pdf[:2 & -5:, tiling=True]",
    "xml:/path/sample.pptx",
    "/path/sample.txt"
)

all_attachments.to_openai()
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

print(ctx)            # formatted summary
len(ctx.images)       # base64 images

# Sending to OpenAI
from openai import OpenAI

client = OpenAI()
resp = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=ctx.to_openai("Analyze the following documents:")
)
print(resp.choices[0].message.content)

# Sending to Anthropic
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
image_pipeline = at_l.load_image | at_t.rotate(90) | at_t.crop(100, 100, 400, 400) | at_t.tile_image(2, 2)
```

### Selective Text Extraction

```python
text_pipeline = at_l.load_html | at_t.css_select("#main-content") | at_rt.html
```

## Design Principles

* **Minimal DSL**: Standard Python syntax, avoiding unnecessary complexity.
* **Intuitive API**: Clear, predictable behavior through fluent chaining and branching.
* **Extensibility**: Simplified plugin creation using decorators, promoting ease of contribution.
* **IDE-Friendly**: Ensuring robust autocomplete and type-hint support.

## Development and Contribution Guidelines

To streamline plugin development and enforce quality:

* **Plugin Validation**: Each plugin decorator checks essential methods (`load`, `match`, `apply`, `render`) exist.
* **Testing Framework**: Provide `PluginContract` base class, which includes default tests for loaders, transformers, renderers, and deliverers.
* **Extensible Pattern**: New plugin contributions are easily integrated and tested through clear and documented interfaces.

## Target Audience

* **Beginners**: Immediate usability via the high-level `Attachments` interface.
* **Intermediate Users**: Simple pipeline reuse and composition.
* **Advanced Users**: Full customization and detailed plugin control.

## Summary

The Attachments library delivers a robust, intuitive, and easily extensible architecture for context attachment management, seamlessly bridging various file formats and downstream LLM APIs.
