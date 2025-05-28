# Attachments Architecture Guide

> **The modular, extensible architecture behind the Python funnel for LLM context**

> **🚧 Work in Progress** - This document is actively being developed and refined.
> 
> **🤖 AI + Human Generated** - This documentation was collaboratively created by AI and human contributors to ensure accuracy and completeness.

## Table of Contents

1. [Overview](#overview)
2. [Core Architecture](#core-architecture)
3. [The Five-Stage Pipeline](#the-five-stage-pipeline)
4. [The Split/Chunking System](#the-splitchunking-system)
5. [Vectorization & Collections](#vectorization--collections)
6. [Match System](#match-system)
7. [Component Deep Dive](#component-deep-dive)
8. [Extension System](#extension-system)
9. [DSL Grammar Engine](#dsl-grammar-engine)
10. [High-Level API Design](#high-level-api-design)
11. [Pipeline Processor System](#pipeline-processor-system)
12. [Error Handling & Fallbacks](#error-handling--fallbacks)
13. [Performance & Memory Management](#performance--memory-management)
14. [Contributing New Components](#contributing-new-components)
15. [Namespace System](#namespace-system)

---

## Overview

Attachments is built on a **modular, pipeline-based architecture** that transforms any file into LLM-ready context through five distinct stages. The system is designed for **extensibility**, **composability**, and **ease of use**.

### Design Principles

- **🔧 Modular**: Each component has a single responsibility
- **🔗 Composable**: Components can be chained and combined
- **📈 Extensible**: New file types and transformations via plugins
- **🎯 Declarative**: DSL grammar for non-programmers
- **🛡️ Robust**: Graceful fallbacks and error handling
- **⚡ Performance**: Lazy loading and efficient memory usage

### Architecture at a Glance

**The Five-Stage Data Transformation Pipeline + Split System:**

```
String → [LOAD] → [MODIFY] → [PRESENT] → [REFINE] → [ADAPT] → APIs
  ↓         ↓         ↓          ↓         ↓         ↓
Path     Object    Object    Content   Content   Format
+ DSL    (PDF)     (pages)   .text     .text     (Claude)
         (CSV)     (rows)    .images   .images   (OpenAI)
         (IMG)     (crop)    .metadata .metadata (DSPy)

           ↓ [SPLIT] ↓ [SPLIT] ↓ [SPLIT]
         
         Collection → Vectorized → Reduced
         (chunks)     (parallel)   (combined)
```

**Split Integration Points:**

- **Object-level**: `split.pages(pdf)` → page collection
- **Content-level**: `split.paragraphs(text)` → semantic chunks
- **Structure-level**: `split.sections(html)` → logical sections

**Split Example - Semantic Document Analysis:**
```python
# Traditional: entire document as one blob
result = attach("report.pdf") | load.pdf_to_pdfplumber | present.markdown

# Split-enabled: semantic analysis of each section
insights = (attach("report.pdf") 
           | load.pdf_to_pdfplumber 
           | split.pages                     # 1 PDF → individual pages
           | present.markdown                # Vectorized: each page → markdown
           | split.paragraphs                # Pages → semantic paragraphs  
           | refine.add_headers              # Vectorized: context for each chunk
           | adapt.claude("Extract key insights from this section"))

# Result: Detailed insights from each semantic unit, not just summary
```

**Split Example - Multi-Modal Presentation Analysis:**
```python
# Analyze each slide individually for detailed feedback
slide_analysis = (attach("deck.pptx")
                 | load.pptx_to_python_pptx
                 | split.slides              # 1 presentation → individual slides
                 | present.markdown + present.images  # Each slide: text + visuals
                 | adapt.claude("Analyze this slide's effectiveness and suggest improvements"))

# Result: Slide-by-slide detailed feedback instead of general overview
```

**Precise Data Flow Patterns:**

1. **LOAD**: `string` → `att._obj` (file path → structured object)
   - `"document.pdf"` → `pdfplumber.PDF` object
   - `"data.csv"` → `pandas.DataFrame` object  
   - `"image.jpg"` → `PIL.Image` object

2. **MODIFY**: `att._obj` → `att._obj` (object transformation)
   - PDF object → PDF object (specific pages selected)
   - DataFrame → DataFrame (rows limited, columns filtered)
   - Image → Image (cropped, rotated, resized)

3. **SPLIT**: `att` → `AttachmentCollection` (expansion to multiple chunks)
   - Single attachment → Multiple semantic/structural units
   - Enables granular analysis and vectorized processing
   - Can split by: pages, slides, paragraphs, sections, rows, columns
   - Focus: Meaningful decomposition for deeper insights

4. **PRESENT**: `att._obj` → `att.{text,images,audio,metadata}` (content extraction)
   - PDF object → `att.text` (markdown), `att.images` (base64 PNGs)
   - DataFrame → `att.text` (formatted table), `att.metadata` (shape info)
   - Image → `att.images` (base64 data URL), `att.metadata` (dimensions)

5. **REFINE**: `att.attributes` → `att.attributes` (content polishing)
   - `att.text` → `att.text` (headers added, truncated)
   - `att.images` → `att.images` (tiled, resized)
   - `att.metadata` → `att.metadata` (enriched)

6. **ADAPT**: `att.attributes` → `external format` (API formatting)
   - `att.{text,images}` → `[{"role": "user", "content": [...]}]` (OpenAI)
   - `att.{text,images}` → `[{"role": "user", "content": [...]}]` (Claude)
   - `att.{text,images}` → `DSPyAttachment` object (DSPy)

### Attachment Data Structure

**Core Attributes** (populated by presenters):
```python
class Attachment:
    # Input parsing
    attachy: str                    # Original input: "file.pdf[pages:1-5]"
    path: str                       # Extracted path: "file.pdf"  
    commands: Dict[str, str]        # Parsed DSL: {"pages": "1-5"}
    
    # Processing state
    _obj: Optional[Any]             # Loaded object (PDF, DataFrame, etc.)
    pipeline: List[str]             # Processing history
    
    # Content attributes (LLM-ready)
    text: str                       # Extracted text content
    images: List[str]               # Base64-encoded images (data URLs)
    audio: List[str]                # Audio content (future)
    metadata: Dict[str, Any]        # Processing metadata
```

**Content Population Examples:**
```python
# PDF processing
att.text = "# PDF Document\n\n## Page 1\n\nContent here..."
att.images = ["data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA..."]
att.metadata = {"pdf_pages_rendered": 3, "is_likely_scanned": False}

# Image processing  
att.text = "# Image: photo.jpg\n\n- **Size**: (1920, 1080)\n- **Format**: JPEG"
att.images = ["data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA..."]
att.metadata = {"image_format": "JPEG", "image_size": (1920, 1080)}

# Data processing
att.text = "## Data from data.csv\n\n| Name | Age |\n|------|-----|\n| John | 25 |"
att.metadata = {"csv_shape": (100, 5), "csv_columns": ["Name", "Age", ...]}
```

---

## Core Architecture

### The Attachment Class

**Location**: `src/attachments/core.py`

The `Attachment` class is the fundamental data container that flows through the entire pipeline:

```python
class Attachment:
    """Simple container for file processing."""
    
    def __init__(self, attachy: str = ""):
        self.attachy = attachy           # Original input with DSL commands
        self.path, self.commands = self._parse_attachy()  # Parsed path and DSL
        
        self._obj: Optional[Any] = None  # Loaded file object (PDF, DataFrame, etc.)
        self.text: str = ""              # Extracted text content
        self.images: List[str] = []      # Base64-encoded images
        self.audio: List[str] = []       # Audio content (future)
        self.metadata: Dict[str, Any] = {}  # Processing metadata
        
        self.pipeline: List[str] = []    # Processing history
```

**Key Features:**
- **DSL Parsing**: Automatically extracts commands like `[pages:1-5]` from input
- **Flexible Content**: Supports text, images, and metadata
- **Pipeline Tracking**: Records processing steps for debugging
- **Operator Overloading**: Supports `|` and `+` for pipeline composition

### The Pipeline System

**Location**: `src/attachments/core.py`

Two types of pipelines enable different composition patterns:

#### Sequential Pipeline (`|` operator)
```python
result = (attach("document.pdf") 
         | load.pdf_to_pdfplumber 
         | modify.pages 
         | present.markdown)
```

#### Additive Pipeline (`+` operator)  
```python
result = attachment | (present.text + present.images + present.metadata)
```

### Registration System

**Location**: `src/attachments/core.py`

A decorator-based system for registering components:

```python
# Global registries
_loaders = {}      # File format → object loaders
_modifiers = {}    # Object transformations  
_presenters = {}   # Content extraction
_refiners = {}     # Post-processing
_adapters = {}     # API format adapters
_splitters = {}    # Split functions that expand attachments into collections

# Registration decorators
@loader(match=lambda att: att.path.endswith('.pdf'))
def pdf_to_pdfplumber(att: Attachment) -> Attachment:
    # Implementation here
    pass

@modifier
def pages(att: Attachment, pdf: 'pdfplumber.PDF') -> Attachment:
    # Modifies att._obj, returns modified attachment
    pass

@presenter
def text(att: Attachment, obj: Any) -> Attachment:
    # Extracts content to att.text, returns attachment
    pass

@splitter  
def paragraphs(att: Attachment, text: str) -> AttachmentCollection:
    # Expands single attachment into multiple chunks
    pass

@refiner
def truncate(att: Attachment) -> Attachment:
    # Post-processes presented content
    pass

@adapter
def claude(att: Attachment, prompt: str = "") -> List[Dict]:
    # Formats for external APIs
    pass
```

**Key Differences:**
- **Loaders**: Require a `match` function to determine applicability
- **Modifiers/Presenters/Splitters**: Use type dispatch based on `att._obj` type
- **Refiners/Adapters**: Simple function registration without type dispatch

---

## Namespace System

### Overview

**Location**: `src/attachments/__init__.py`

The namespace system provides organized access to all registered functions through 6 main namespaces:

```python
# Create the namespace instances after functions are registered
load = SmartVerbNamespace(_loaders)      # File format → object loaders
modify = SmartVerbNamespace(_modifiers)  # Object transformations  
present = SmartVerbNamespace(_presenters) # Content extraction
adapt = SmartVerbNamespace(_adapters)    # API format adapters
refine = SmartVerbNamespace(_refiners)   # Post-processing
split = SmartVerbNamespace(_splitters)   # Split functions that expand attachments
```

### Namespace Functions

| Namespace | Purpose | Example Functions | Count |
|-----------|---------|-------------------|-------|
| `load.*` | File format → objects | `pdf_to_pdfplumber`, `csv_to_pandas`, `image_to_pil`, `html_to_bs4` | 10+ |
| `modify.*` | Transform objects | `pages`, `limit`, `crop`, `rotate`, `select`, `watermark` | 8 |
| `present.*` | Extract content | `text`, `markdown`, `images`, `csv`, `html`, `metadata` | 10+ |
| `adapt.*` | Format for APIs | `claude`, `openai_chat`, `openai_responses`, `dspy` | 6 |
| `refine.*` | Post-process | `add_headers`, `truncate`, `tile_images`, `resize_images` | 7 |
| `split.*` | Expand to collections | `paragraphs`, `sentences`, `tokens`, `pages`, `slides` | 12 |

### Usage Patterns

#### Pipeline Composition
```python
# Sequential processing with |
result = (attach("document.pdf") 
         | load.pdf_to_pdfplumber 
         | modify.pages 
         | present.markdown 
         | refine.add_headers
         | adapt.claude("Analyze this"))

# Additive composition with +
content = (attach("document.pdf")
          | load.pdf_to_pdfplumber
          | present.text + present.images + present.metadata)
```

#### Direct Function Calls
```python
# Load and process directly
att = attach("document.pdf")
att = load.pdf_to_pdfplumber(att)
att = present.markdown(att)
result = adapt.claude(att, "Summarize this")
```

#### Partial Application
```python
# Create reusable processors
pdf_processor = (load.pdf_to_pdfplumber 
                | modify.pages 
                | present.markdown 
                | refine.add_headers)

# Apply to multiple files
doc1 = pdf_processor("report1.pdf")
doc2 = pdf_processor("report2.pdf")
```

### SmartVerbNamespace Features

**Runtime Autocomplete**: IDE support through `__dir__()` implementation
```python
# These work in IDEs with autocomplete
load.pdf_to_pdfplumber
present.markdown
split.paragraphs
```

**Dynamic Registration**: New functions automatically appear in namespaces
```python
@loader(match=lambda att: att.path.endswith('.xyz'))
def xyz_to_custom(att): pass

# Immediately available
load.xyz_to_custom  # Works automatically
```

**Type Safety**: VerbFunction wrappers provide consistent interfaces
```python
# All these patterns work consistently
att | load.pdf_to_pdfplumber
load.pdf_to_pdfplumber(att)
load.pdf_to_pdfplumber("file.pdf")  # Auto-creates attachment
```

---

## The Five-Stage Pipeline

### 1. LOAD Stage
**Purpose**: Convert files into structured objects  
**Location**: `src/attachments/loaders/`

```
File Path → File Object
```

**Examples:**
- `pdf_to_pdfplumber`: PDF → pdfplumber.PDF
- `csv_to_pandas`: CSV → pandas.DataFrame  
- `image_to_pil`: Image → PIL.Image
- `url_to_bs4`: URL → BeautifulSoup

**Architecture:**
- **Match Functions**: Determine which loader handles each file type
- **Type Dispatch**: Multiple loaders can handle the same file type
- **Fallback Chain**: Graceful degradation when specialized loaders fail

### 2. MODIFY Stage  
**Purpose**: Transform loaded objects based on DSL commands  
**Location**: `src/attachments/modify.py`

```
File Object + DSL Commands → Modified Object
```

**Examples:**
- `pages`: Extract specific pages from PDFs/presentations
- `limit`: Limit rows in DataFrames
- `crop`: Crop images to specific regions
- `rotate`: Rotate images

**Architecture:**
- **Command Parsing**: Reads DSL commands from `attachment.commands`
- **Type Dispatch**: Different implementations for different object types
- **Chaining**: Multiple modifications can be applied sequentially

### 3. PRESENT Stage
**Purpose**: Extract content (text, images, metadata) from objects  
**Location**: `src/attachments/presenters/`

```
Modified Object → Text + Images + Metadata
```

**Categories:**
- **Text Presenters**: `text/` - Extract formatted text
- **Visual Presenters**: `visual/` - Extract and process images  
- **Data Presenters**: `data/` - Format structured data
- **Metadata Presenters**: `metadata/` - Extract file information

**Smart Filtering:**
- **Format Commands**: `[format:markdown]` selects appropriate presenter
- **Content Filtering**: `[images:false]` disables image extraction
- **Category Detection**: Auto-detects presenter type for DSL filtering

### 4. REFINE Stage
**Purpose**: Post-process and polish extracted content  
**Location**: `src/attachments/refine.py`

```
Raw Content → Polished Content
```

**Examples:**
- `add_headers`: Add file headers and structure
- `truncate`: Limit text length for token budgets
- `tile_images`: Combine multiple images into grids
- `clean_text`: Remove artifacts and normalize formatting

### 5. ADAPT Stage
**Purpose**: Format content for specific LLM APIs  
**Location**: `src/attachments/adapt.py`

```
Polished Content → API-Specific Format
```

**Adapters:**
- `claude()`: Anthropic Claude message format
- `openai_chat()`: OpenAI Chat Completions format
- `openai_responses()`: OpenAI Responses API format
- `dspy()`: DSPy BaseType-compatible objects

---

## The Split/Chunking System

### Overview

**Location**: `src/attachments/split.py`

The Split system **expands** single attachments into `AttachmentCollection` objects. This enables **vectorized processing** and **LLM-friendly chunking**.

```
Single Attachment → AttachmentCollection (Multiple Chunks)
```

### Split Categories

#### Text Splitting
**Purpose**: Break text into semantic or size-based chunks

```python
# Semantic splitting
chunks = attach("doc.txt") | load.text_to_string | split.paragraphs
chunks = attach("doc.txt") | load.text_to_string | split.sentences

# Size-based splitting (LLM-friendly)
chunks = attach("doc.txt[tokens:500]") | load.text_to_string | split.tokens
chunks = attach("doc.txt[characters:1000]") | load.text_to_string | split.characters
chunks = attach("doc.txt[lines:50]") | load.text_to_string | split.lines

# Custom splitting
chunks = attach("doc.txt[custom:---BREAK---]") | load.text_to_string | split.custom
```

**Available Splitters:**
- `paragraphs`: Split on double newlines
- `sentences`: Split on sentence boundaries (`.!?`)
- `tokens`: Split by approximate token count (~4 chars/token)
- `characters`: Split by character count
- `lines`: Split by line count
- `custom`: Split by custom separator from DSL commands

#### Document Splitting
**Purpose**: Break documents into structural units

```python
# PDF pages
pages = attach("report.pdf") | load.pdf_to_pdfplumber | split.pages

# PowerPoint slides  
slides = attach("deck.pptx") | load.pptx_to_python_pptx | split.slides

# HTML sections (by headings)
sections = attach("article.html") | load.html_to_bs4 | split.sections
```

#### Data Splitting
**Purpose**: Break large datasets into manageable chunks

```python
# DataFrame row chunks
row_chunks = attach("data.csv[rows:100]") | load.csv_to_pandas | split.rows

# DataFrame column chunks
col_chunks = attach("data.csv[columns:5]") | load.csv_to_pandas | split.columns
```

### Split Architecture

**Registration**: Split functions use the `@splitter` decorator and have their own `_splitters` registry:

```python
@splitter
def paragraphs(att: Attachment, text: str) -> AttachmentCollection:
    """Split text content into paragraphs."""
    content = att.text if att.text else text
    
    # Split on double newlines
    paragraphs = re.split(r'\n\s*\n', content.strip())
    
    chunks = []
    for i, paragraph in enumerate(paragraphs):
        chunk = Attachment(f"{att.path}#paragraph-{i+1}")
        chunk.text = paragraph
        chunk.commands = att.commands.copy()  # Propagate DSL commands
        chunk.metadata = {
            **att.metadata,
            'chunk_type': 'paragraph',
            'chunk_index': i,
            'total_chunks': len(paragraphs),
            'original_path': att.path
        }
        chunks.append(chunk)
    
    return AttachmentCollection(chunks)
```

**Architectural Pattern**: Split functions follow a distinct pattern:

- **Input**: `(att: Attachment, content: str)` or `(att: Attachment, obj: ObjectType)`
- **Output**: `AttachmentCollection` (multiple chunks)
- **Registry**: `_splitters` (separate from modifiers)
- **Namespace**: `split.*` functions
- **Type Dispatch**: Based on second parameter type annotation

**Key Differences from Modifiers**:
- **Modifiers**: `att._obj → modified att._obj` (transform in place)
- **Splitters**: `att → AttachmentCollection` (expand to multiple attachments)

This maintains architectural clarity and proper separation of concerns.

---

## Vectorization & Collections

### AttachmentCollection Architecture

**Location**: `src/attachments/core.py`

The `AttachmentCollection` class enables **automatic vectorization** - operations apply to each attachment in the collection:

```python
class AttachmentCollection:
    """A collection of attachments that supports vectorized operations."""
    
    def __or__(self, operation: Union[Callable, Pipeline]) -> Union['AttachmentCollection', 'Attachment']:
        """Apply operation - vectorize or reduce based on operation type."""
        
        if self._is_reducer(operation):
            # Apply to collection as whole (reduction)
            return operation(self)
        else:
            # Apply to each attachment (vectorization)
            results = []
            for att in self.attachments:
                result = operation(att)
                if result is not None:
                    results.append(result)
            return AttachmentCollection(results)
```

### Vectorization Examples

```python
# ZIP files become collections that auto-vectorize
images = (attach("photos.zip") 
         | load.zip_to_images          # → AttachmentCollection
         | present.images              # Vectorized: each image → base64
         | refine.tile_images)         # Reducer: combine into grid

# Document chunking with vectorization
chunks = (attach("doc.txt") 
         | load.text_to_string 
         | split.paragraphs            # → AttachmentCollection
         | present.markdown            # Vectorized: each chunk → markdown
         | refine.add_headers)         # Vectorized: each chunk gets headers
```

### Reducers vs Vectorizers

**Vectorizers** (default): Apply to each item in collection
- Most presenters (`present.text`, `present.images`)
- Most modifiers (`modify.pages`, `modify.crop`)
- Most refiners (`refine.add_headers`, `refine.truncate`)

**Reducers**: Combine collection into single result
- `refine.tile_images`: Combine images into grid
- All adapters (`claude()`, `openai_chat()`)
- Collection-specific refiners

**Detection Logic**:
```python
def _is_reducer(self, operation) -> bool:
    """Check if operation combines multiple attachments."""
    if hasattr(operation, 'name'):
        reducing_operations = {
            'tile_images', 'combine_images', 'merge_text', 
            'claude', 'openai_chat', 'openai_response'
        }
        return operation.name in reducing_operations
    return False
```

---

## Match System

### Overview

**Location**: `src/attachments/matchers.py`

The Match system provides **reusable predicates** for determining which loaders and processors handle specific file types. This centralizes file type detection logic.

### Match Functions

```python
# File extension matching
def pdf_match(att: 'Attachment') -> bool:
    return att.path.endswith('.pdf')

def image_match(att: 'Attachment') -> bool:
    return att.path.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.heic', '.heif'))

# Content-based matching
def webpage_match(att: 'Attachment') -> bool:
    """Check if attachment is a webpage URL (not downloadable file)."""
    if not att.path.startswith(('http://', 'https://')):
        return False
    
    # Exclude URLs that end with file extensions
    file_extensions = ['.pdf', '.pptx', '.docx', '.csv', '.jpg', ...]
    return not any(att.path.lower().endswith(ext) for ext in file_extensions)

# Complex logic matching
def git_repo_match(att: 'Attachment') -> bool:
    """Check if path is a Git repository."""
    abs_path = os.path.abspath(att.path)
    if not os.path.isdir(abs_path):
        return False
    git_dir = os.path.join(abs_path, '.git')
    return os.path.exists(git_dir)
```

### Usage in Loaders

```python
from ... import matchers

@loader(match=matchers.pdf_match)
def pdf_to_pdfplumber(att: Attachment) -> Attachment:
    """Load PDF using pdfplumber."""
    # Implementation...

@loader(match=matchers.image_match)  
def image_to_pil(att: Attachment) -> Attachment:
    """Load images using PIL."""
    # Implementation...
```

### Usage in Processors

```python
from ..matchers import pdf_match

@processor(match=pdf_match)
def pdf_to_llm(att):
    """Complete PDF processing pipeline."""
    return (att 
           | load.pdf_to_pdfplumber
           | present.markdown + present.images
           | refine.add_headers)
```

### Benefits

- **Reusability**: Same match logic across loaders and processors
- **Consistency**: Centralized file type detection
- **Maintainability**: Update file type logic in one place
- **Testability**: Match functions can be tested independently
- **Extensibility**: Easy to add new file type detection logic

---

## Component Deep Dive

### Loaders Architecture

**Directory Structure:**
```
src/attachments/loaders/
├── documents/     # PDF, DOCX, PPTX loaders
├── data/          # CSV, JSON, Excel loaders  
├── media/         # Image, audio, video loaders
├── web/           # URL, HTML loaders
└── repositories/ # Git repo, directory loaders
```

**Match Function Pattern:**
```python
@loader(match=lambda att: att.path.endswith('.pdf'))
def pdf_to_pdfplumber(att: Attachment) -> Attachment:
    """Load PDF using pdfplumber for text and table extraction."""
    # Implementation details...
```

**Error Handling:**
- **Import Errors**: Helpful messages for missing dependencies
- **File Errors**: Graceful handling of corrupted files
- **Fallback Chain**: Multiple loaders can handle the same file type

### Presenters Architecture

**Smart Category System:**
```python
@presenter(category='text')
def markdown(att: Attachment, obj: Any) -> Attachment:
    """Extract content as Markdown format."""
    # Implementation...

@presenter(category='image')  
def images(att: Attachment, pil_image: 'PIL.Image.Image') -> Attachment:
    """Extract and encode images as base64."""
    # Implementation...
```

**Type Dispatch:**
- Multiple presenters can handle the same object type
- DSL commands select appropriate presenter
- Fallback to default presenters when specialized ones fail

### Modifiers Architecture

**Command-Driven Processing:**
```python
@modifier
def pages(att: Attachment, pdf_obj: 'pdfplumber.PDF') -> Attachment:
    """Extract specific pages based on DSL commands."""
    pages_cmd = att.commands.get('pages')
    if pages_cmd:
        # Parse page ranges: "1,3-5,-1"
        # Extract specified pages
    return att
```

**Type Safety:**
- Type hints ensure modifiers only apply to compatible objects
- Runtime type checking prevents errors
- Graceful skipping when commands don't apply

---

## Extension System

### Creating New Loaders

**Step 1: Create the loader function**
```python
# my_custom_loader.py
from attachments.core import Attachment, loader

@loader(match=lambda att: att.path.endswith('.xyz'))
def xyz_to_custom(att: Attachment) -> Attachment:
    """Load XYZ files using custom parser."""
    try:
        import custom_xyz_parser
        
        # Load the file
        with open(att.path, 'rb') as f:
            xyz_obj = custom_xyz_parser.parse(f)
        
        # Store in attachment
        att._obj = xyz_obj
        return att
        
    except ImportError:
        att.text = "Custom XYZ parser not installed. Run: pip install custom-xyz-parser"
        return att
```

**Step 2: Import to register**
```python
# In your code
import my_custom_loader  # Registers the loader
from attachments import Attachments

# Now works automatically
ctx = Attachments("document.xyz")
```

### Creating New Presenters

```python
# my_custom_presenter.py
from attachments.core import Attachment, presenter

@presenter(category='text')
def custom_format(att: Attachment, xyz_obj: 'CustomXYZObject') -> Attachment:
    """Present XYZ content in custom format."""
    
    # Extract content from XYZ object
    content = xyz_obj.extract_content()
    
    # Format as needed
    formatted = f"# XYZ Document\n\n{content}"
    
    # Add to attachment (preserving existing content)
    att.text += formatted
    
    # Add metadata
    att.metadata['xyz_version'] = xyz_obj.version
    
    return att
```

### Creating Pipeline Processors

**For complete file-to-LLM workflows:**

```python
# my_processor.py
from attachments.pipelines import processor
from attachments import load, present, refine

@processor(match=lambda att: att.path.endswith('.xyz'))
def xyz_to_llm(att):
    """Complete XYZ file processor."""
    return (att 
           | load.xyz_to_custom
           | present.custom_format + present.metadata
           | refine.add_headers)

# Named processor for specialized use
@processor(match=lambda att: att.path.endswith('.xyz'), 
          name="academic_xyz")
def academic_xyz_to_llm(att):
    """Academic-focused XYZ processor."""
    return (att 
           | load.xyz_to_custom
           | present.academic_format + present.citations
           | refine.add_bibliography)
```

---

## Grammar of File Processing

### Overview

Attachments provides a **grammar of file processing** - a consistent set of verbs that compose naturally to solve common file-to-LLM challenges, inspired by dplyr's grammar of data manipulation.

### Core Verbs

**Data Verbs** (like dplyr):
- `load.*` - Import files into structured objects
- `modify.*` - Transform objects (filter, select, reshape)  
- `split.*` - Decompose into semantic units
- `present.*` - Extract content (text, images, metadata)
- `refine.*` - Polish and enhance content
- `adapt.*` - Format for external APIs

**Composition Patterns**:
```python
# Sequential composition with |
result = (attach("data.csv") 
         | load.csv_to_pandas 
         | modify.limit 
         | present.markdown)

# Additive composition with +  
content = attachment | (present.text + present.images + present.metadata)

# Grouping with split (like group_by)
insights = (attach("report.pdf")
           | load.pdf_to_pdfplumber
           | split.pages              # "group by" pages
           | present.markdown         # apply to each page
           | adapt.claude("analyze")) # reduce to insights
```

### Grammar Benefits

**Consistency**: Same verb patterns across all file types
```python
# Same pattern works for any file type
attach("file.pdf") | load.pdf_to_pdfplumber | present.markdown
attach("file.csv") | load.csv_to_pandas | present.markdown  
attach("file.jpg") | load.image_to_pil | present.markdown
```

**Composability**: Verbs combine naturally
```python
# Build complex pipelines from simple verbs
academic_processor = (load.pdf_to_pdfplumber 
                     | modify.pages 
                     | present.markdown + present.images
                     | refine.add_headers | refine.truncate
                     | adapt.claude)
```

**Extensibility**: Add new verbs that fit the grammar
```python
@loader(match=lambda att: att.path.endswith('.xyz'))
def xyz_to_custom(att): ...  # New verb follows same pattern

@presenter  
def academic_format(att, obj): ...  # Composes with existing verbs
```

### DSL Commands

**Declarative Syntax**: Simple commands modify verb behavior
```python
# Commands modify how verbs operate
"document.pdf[pages:1-5]"        # modify.pages uses 1-5
"image.jpg[rotate:90]"           # modify.rotate uses 90°  
"data.csv[limit:100]"            # modify.limit uses 100 rows
"url[select:h1][format:markdown]" # modify.select + present.markdown
```

**Command Processing**: Verbs read relevant commands
```python
@modifier
def pages(att: Attachment, pdf: 'pdfplumber.PDF') -> Attachment:
    pages_cmd = att.commands.get('pages', 'all')  # Read DSL command
    # Apply page selection based on command
    return att
```

---

## High-Level API Design

### The Attachments Class

**Location**: `src/attachments/highest_level_api.py`

**Design Goals:**
- **Zero Learning Curve**: `Attachments("file.pdf")` just works
- **Automatic Processing**: Smart pipeline selection
- **Consistent Interface**: Same API for any file type
- **Rich Output**: Text, images, and metadata ready for LLMs

**Auto-Processing Pipeline:**
```python
def _auto_process(self, att: Attachment):
    """Enhanced auto-processing with processor discovery."""
    
    # 1. Try specialized processors first
    processor_fn = find_primary_processor(att)
    if processor_fn:
        try:
            return processor_fn(att)
        except Exception:
            # Fall back to universal pipeline
            pass
    
    # 2. Universal fallback pipeline
    return self._universal_pipeline(att)
```

**Universal Pipeline:**
```python
def _universal_pipeline(self, att: Attachment):
    """Universal fallback pipeline for files without specialized processors."""
    
    # Smart loader chain
    loaded = (att 
             | load.url_to_file             # URLs first
             | load.pdf_to_pdfplumber       # Then file types
             | load.csv_to_pandas 
             | load.image_to_pil
             | load.text_to_string)         # Text as fallback
    
    # Smart presenter selection
    text_presenter = _get_smart_text_presenter(loaded)
    
    processed = (loaded
                | modify.pages  # Apply DSL commands
                | (text_presenter + present.images + present.metadata)
                | refine.tile_images | refine.add_headers)
    
    return processed
```

### API Adapter Integration

**Automatic Method Exposure:**
```python
def __getattr__(self, name: str):
    """Automatically expose all adapters as methods."""
    if name in _adapters:
        def adapter_method(*args, **kwargs):
            adapter_fn = _adapters[name]
            combined_att = self._to_single_attachment()
            return adapter_fn(combined_att, *args, **kwargs)
        return adapter_method
```

**Usage:**
```python
ctx = Attachments("document.pdf", "image.jpg")

# These work automatically:
claude_msg = ctx.claude("Analyze this content")
openai_msg = ctx.openai_chat("Summarize this")
dspy_obj = ctx.dspy()
```

---

## Pipeline Processor System

### Processor Registry

**Location**: `src/attachments/pipelines/__init__.py`

**Two Types of Processors:**

1. **Primary Processors**: Auto-selected for simple API
2. **Named Processors**: Explicit access for specialized workflows

```python
@processor(match=lambda att: att.path.endswith('.pdf'))
def pdf_to_llm(att):  # Primary - auto-selected
    return standard_pdf_pipeline(att)

@processor(match=lambda att: att.path.endswith('.pdf'), name="academic_pdf")
def academic_pdf_to_llm(att):  # Named - explicit access
    return academic_pdf_pipeline(att)
```

**Registry Architecture:**
```python
class ProcessorRegistry:
    def __init__(self):
        self._processors: List[ProcessorInfo] = []
        self._primary_processors: Dict[str, ProcessorInfo] = {}
        self._named_processors: Dict[str, ProcessorInfo] = {}
    
    def find_primary_processor(self, att: Attachment) -> Optional[ProcessorInfo]:
        """Find the primary processor for an attachment."""
        for proc_info in self._primary_processors.values():
            if proc_info.match_fn(att):
                return proc_info
        return None
```

### Processor Discovery

**Automatic Registration:**
```python
# Import all processor modules to register them
from . import pdf_processor
from . import image_processor  
from . import docx_processor
from . import pptx_processor
# ... etc
```

**Match Function Examples:**
```python
# File extension matching
match=lambda att: att.path.endswith('.pdf')

# Content-based matching
match=lambda att: att.path.startswith('http') and 'github.com' in att.path

# Complex logic
match=lambda att: (att.path.endswith('.txt') and 
                  att.commands.get('format') == 'academic')
```

---

## Error Handling & Fallbacks

### Graceful Degradation

**Loader Fallbacks:**
```python
try:
    loaded = (att 
             | load.specialized_loader    # Try specialized first
             | load.generic_loader        # Fall back to generic
             | load.text_to_string)       # Last resort: treat as text
except Exception as e:
    # Create error attachment with helpful message
    att.text = f"Could not process {att.path}: {str(e)}"
```

**Dependency Handling:**
```python
def _create_helpful_error_attachment(att: Attachment, import_error: ImportError, loader_name: str):
    """Create helpful error messages for missing dependencies."""
    
    # Map loader names to installation instructions
    dependency_map = {
        'pdf_to_pdfplumber': 'pip install pdfplumber',
        'csv_to_pandas': 'pip install pandas',
        'image_to_pil': 'pip install Pillow',
    }
    
    install_cmd = dependency_map.get(loader_name, 'pip install attachments[all]')
    
    att.text = f"""
⚠️ Missing dependency for {att.path}

To process this file type, install the required dependency:
  {install_cmd}

Or install all dependencies:
  pip install attachments[all]
"""
    return att
```

### Error Recovery

**Pipeline Resilience:**
```python
def _execute_steps(self, result: Attachment, steps: List[Callable]):
    """Execute pipeline steps with error recovery."""
    for step in steps:
        try:
            result = step(result)
        except Exception as e:
            # Log error but continue pipeline
            result.metadata['errors'] = result.metadata.get('errors', [])
            result.metadata['errors'].append(f"{step.__name__}: {str(e)}")
            # Continue with previous result
    return result
```

---

## Performance & Memory Management

### Lazy Loading

**Object Loading:**
```python
class Attachment:
    def __init__(self, attachy: str = ""):
        self._obj: Optional[Any] = None  # Not loaded until needed
        
    @property
    def obj(self):
        """Lazy load the file object when first accessed."""
        if self._obj is None:
            self._obj = self._load_object()
        return self._obj
```

**Image Processing:**
```python
@presenter
def images(att: Attachment, pil_image: 'PIL.Image.Image') -> Attachment:
    """Extract images with memory-efficient processing."""
    
    # Process images in chunks to avoid memory issues
    if hasattr(pil_image, 'n_frames') and pil_image.n_frames > 10:
        # For large multi-frame images, sample frames
        frames_to_process = min(10, pil_image.n_frames)
    
    # Convert to base64 with size limits
    max_size = (1024, 1024)  # Resize large images
    if pil_image.size[0] > max_size[0] or pil_image.size[1] > max_size[1]:
        pil_image = pil_image.resize(max_size, Image.Resampling.LANCZOS)
```

### Resource Cleanup

**Automatic Cleanup:**
```python
class Attachment:
    def cleanup(self):
        """Clean up temporary resources."""
        # Clean up temporary files
        if 'temp_pdf_path' in self.metadata:
            os.unlink(self.metadata['temp_pdf_path'])
        
        # Close file objects
        if hasattr(self._obj, 'close'):
            self._obj.close()
    
    def __del__(self):
        """Destructor ensures cleanup."""
        try:
            self.cleanup()
        except Exception:
            pass  # Ignore errors during cleanup
```

---

## Contributing New Components

### Quick Start Checklist

**Adding a New Loader:**
- [ ] Create loader function with `@loader` decorator
- [ ] Add match function for file type detection
- [ ] Handle import errors gracefully
- [ ] Add type hints for presenter dispatch
- [ ] Test with various file formats

**Adding a New Presenter:**
- [ ] Create presenter function with `@presenter` decorator
- [ ] Specify category (`text`, `image`, or auto-detect)
- [ ] Handle multiple object types if needed
- [ ] Preserve existing content (additive)
- [ ] Add relevant metadata

**Adding a New Modifier:**
- [ ] Create modifier function with `@modifier` decorator
- [ ] Read DSL commands from `att.commands`
- [ ] Add type dispatch for different object types
- [ ] Handle edge cases gracefully
- [ ] Document supported command syntax

**Adding a New Adapter:**
- [ ] Create adapter function with `@adapter` decorator
- [ ] Handle both single attachments and collections
- [ ] Format according to target API specification
- [ ] Include proper error handling
- [ ] Add usage examples

### Testing Your Components

```python
# Test your new component
from attachments import Attachments
import my_new_component  # Registers your component

# Test with simple API
ctx = Attachments("test_file.xyz")
print(str(ctx))  # Should use your loader/presenter

# Test with pipeline API
from attachments import attach, load, present
result = (attach("test_file.xyz")
         | load.xyz_to_custom
         | present.custom_format)
```

### Best Practices

1. **Error Handling**: Always handle missing dependencies gracefully
2. **Type Safety**: Use type hints for proper dispatch
3. **Documentation**: Include docstrings with examples
4. **Testing**: Test with edge cases and malformed files
5. **Performance**: Consider memory usage for large files
6. **Compatibility**: Support multiple versions of dependencies

---

## Advanced Topics

### Custom Pipeline Composition

[TODO: Add examples of complex pipeline composition]

### Performance Optimization

[TODO: Add profiling and optimization techniques]

### Debugging and Introspection

[TODO: Add debugging tools and techniques]

### Integration Patterns

[TODO: Add common integration patterns with other libraries]

---

## Conclusion

The Attachments architecture is designed to be **simple for users** but **powerful for contributors**. The five-stage pipeline provides clear separation of concerns, while the registration system makes it easy to add new capabilities.

Key architectural strengths:
- **Modularity**: Each component has a single, clear responsibility
- **Extensibility**: New file types and transformations via simple decorators
- **Composability**: Components can be mixed and matched
- **Robustness**: Graceful fallbacks and error handling throughout
- **Performance**: Lazy loading and efficient resource management

Whether you're using the simple `Attachments("file.pdf")` API or building complex pipelines, the architecture scales to meet your needs while maintaining consistency and reliability.

---

*This document is a living guide. As the architecture evolves, we'll update it to reflect new patterns and best practices. Contributions and feedback are welcome!* 