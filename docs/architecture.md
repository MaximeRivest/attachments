# Attachments Architecture Guide

> **The modular, extensible architecture behind the Python funnel for LLM context**

## Overview

Attachments transforms **any file into LLM-ready context** through a simple but powerful architecture. At its core, it's a **grammar of composable verbs** that work consistently across all file types.

### The Big Picture

The Attachments architecture was designed to support a single goal: create the `Attachments` object without losing my mind while doing it. `Attachments`' role is simple—take any string that represents a path or URL and return an object that has `.text` ready to f-string into a prompt and base64 images (in a list) ready to be sent to an LLM. The difficulty comes from the fact that Attachments does everything from a simple string. Under the hood, it has to decide a lot of things, and there are inevitably lots of possible pipelines because Attachments' goal is to process **any** string and URL. Oh, and `Attachments` must also elegantly deliver its output to any LLM library (or non-LLM library). To achieve this, we designed a grammar of file processing (inspired by dplyr and ggplot2). This consists of 6 composable verbs, each with a very specific role. We also designed a DSL (Domain Specific Language) that allows users to specify how they want their files to be processed. We could have used dictionaries, but this DSL is entirely optional. When using the verbs directly to compose your own pipeline, you do not need to use the DSL—you can just pass your parameters to the functions directly.

**One API, Any File:**
```python
# Simple API - works for any file type
ctx = Attachments("document.pdf", "data.csv", "image.jpg")
print(ctx.text)      # All content as text
print(ctx.images)    # All images as base64
ctx.claude("Analyze this content")  # Ready for AI
```

**Grammar API - Full Control:**
```python
# Composable verbs for complex workflows
insights = (attach("report.pdf")
           | load.pdf_to_pdfplumber    # File → Object
           | split.pages               # Object → Collection  
           | present.markdown          # Extract content
           | refine.add_headers        # Polish content
           | adapt.claude("Analyze"))  # Format for AI
```

**Pipeline Operators:**
- **`|` (pipe)**: Sequential processing - each step **overwrites/transforms** the attachment
- **`+` (plus)**: Additive composition - **combines** multiple presenters' outputs
  ```python
  # Sequential: each step transforms the result
  result = attach("doc.pdf") | load.pdf_to_pdfplumber | present.markdown
  
  # Additive: combines text + images + metadata into one attachment
  content = attach("doc.pdf") | load.pdf_to_pdfplumber | (present.text + present.images + present.metadata)
  ```

### The Grammar of File Processing

**Six Composable Verbs** (inspired by dplyr):

| Verb | Purpose | Example | Result |
|------|---------|---------|--------|
| `load.*` | File → Object | `load.pdf_to_pdfplumber` | PDF → pdfplumber.PDF |
| `modify.*` | Object → Object | `modify.pages` | Extract pages 1-5 |
| `split.*` | Object → Collection | `split.paragraphs` | 1 doc → N chunks |
| `present.*` | Object → text/images/video(future)/audio(future) | `present.markdown` | Object → text/images |
| `refine.*` | text/images/video(future)/audio(future) → text/images/video(future)/audio(future) | `refine.add_headers` | Add structure |
| `adapt.*` | text/images/video(future)/audio(future) → external API format | `adapt.claude()` | → Claude messages |

**Why This Works:**
- **Consistency**: Same pattern for PDFs, CSVs, images, URLs
- **Composability**: Verbs chain naturally with `|` and `+` or stack (the pipe is not mandatory)
- **Extensibility**: Add new file types by implementing the verbs

### DSL Commands: Declarative Control

**Embedded in file paths** for non-programmers, for llms using attachments as tool (? :) ):
```python
"document.pdf[pages:1-5]"           # Extract specific pages
"image.jpg[rotate:90][crop:100,100,400,300]"  # Transform image
"data.csv[limit:1000][summary:true]"          # Limit and summarize
"url[select:h1][format:markdown]"             # CSS selector + format
```

Commands modify how verbs behave without changing the grammar structure.

### Architecture: Five Stages + Split

**Linear Pipeline:**
```
attach("file.pdf[pages:1-5]")
  ↓ LOAD     → pdfplumber.PDF object
  ↓ MODIFY   → pages 1-5 selected  
  ↓ PRESENT  → .text + .images extracted
  ↓ REFINE   → headers added, content polished
  ↓ ADAPT    → Claude API format
```

**Split Branch - Vectorized Processing:**
```
attach("report.pdf")
  ↓ LOAD     → pdfplumber.PDF
  ↓ SPLIT    → [page1, page2, page3, ...]  # AttachmentCollection
  ↓ PRESENT  → [text1, text2, text3, ...]  # Vectorized
  ↓ ADAPT    → Combined AI messages
```

**Key Insight**: Split enables **granular analysis** instead of just **holistic summaries**.

### The Attachment Data Container

**Core Structure** (`src/attachments/core.py`):
```python
class Attachment:
    # Input
    attachy: str = "file.pdf[pages:1-5]"  # Original with DSL
    path: str = "file.pdf"                # Parsed path
    commands: Dict = {"pages": "1-5"}     # Parsed commands
    
    # Processing
    _obj: Any = None                      # Loaded object (PDF, DataFrame, etc.)
    
    # Output (LLM-ready)
    text: str = ""                        # Extracted text
    images: List[str] = []                # Base64 images
    metadata: Dict = {}                   # Processing info
```

**Content flows through the pipeline**, getting richer at each stage.

### Registration System: How It All Connects

**Decorators register functions** (`src/attachments/core.py`):
```python
@loader(match=lambda att: att.path.endswith('.pdf'))
def pdf_to_pdfplumber(att): ...

@modifier  
def pages(att, pdf_obj): ...

@presenter
def markdown(att, obj): ...

@splitter
def paragraphs(att, text): ...
```

**Namespaces provide access** (`src/attachments/__init__.py`):
```python
load = SmartVerbNamespace(_loaders)      # load.pdf_to_pdfplumber
modify = SmartVerbNamespace(_modifiers)  # modify.pages  
present = SmartVerbNamespace(_presenters) # present.markdown
split = SmartVerbNamespace(_splitters)   # split.paragraphs
```

**Type dispatch connects them**:
- Loaders use match functions: `att.path.endswith('.pdf')`
- Others use type hints: `pdf_obj: 'pdfplumber.PDF'`

### Why This Architecture?

**For Users:**
- **Simple**: `Attachments("file.pdf")` just works
- **Powerful**: Grammar system for complex workflows
- **Consistent**: Same patterns across all file types

**For Contributors:**
- **Modular**: Add one verb at a time
- **Extensible**: New file types via decorators
- **Testable**: Each component isolated

**For the Ecosystem:**
- **Composable**: Verbs work together naturally
- **Discoverable**: IDE autocomplete for all functions
- **Maintainable**: Clear separation of concerns

---

## Core Architecture

The core architecture centers on one simple data container (`Attachment`) and six registries that hold functions. Each registry serves a specific purpose in the pipeline, and the registration system uses decorators to automatically organize functions by type. The `VerbNamespace` classes provide clean access to registered functions, while type dispatch ensures the right function gets called for each object type.

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
        self.text: str = ""              # Extracted text
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

The namespace system solves a practical problem: how do you organize 50+ functions across 6 different categories and make them discoverable? The solution is `SmartVerbNamespace` objects that provide clean access (`load.pdf_to_pdfplumber`) while supporting IDE autocomplete (sometimes, this is not resolved for some language servers and ideas -.-). Functions are automatically registered into namespaces when their modules are imported, and type dispatch ensures the right function gets called.

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
| `load.*` | File → Object | `pdf_to_pdfplumber`, `csv_to_pandas`, `image_to_pil`, `html_to_bs4` | 10+ |
| `modify.*` | Object → Object | `pages`, `limit`, `crop`, `rotate`, `select`, `watermark` | 8 |
| `split.*` | Object → Collection | `paragraphs`, `sentences`, `tokens`, `pages`, `slides` | 12 |
| `present.*` | Object → text/images/video(future)/audio(future) | `markdown`, `images`, `csv`, `html`, `metadata` | 10+ |
| `refine.*` | text/images/video(future)/audio(future) → text/images/video(future)/audio(future) | `add_headers`, `truncate`, `tile_images`, `resize_images` | 7 |
| `adapt.*` | text/images/video(future)/audio(future) → external API format | `claude`, `openai_chat`, `openai_responses`, `dspy` | 6 |

**Why This Works:**
- **Consistency**: Same pattern for PDFs, CSVs, images, URLs
- **Composability**: Verbs chain naturally with `|` and `+` or stack (the pipe is not mandatory)
- **Extensibility**: Add new file types by implementing the verbs

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

The five-stage pipeline exists because file processing has natural stages that need to happen in order. You can't extract text before loading the file, and you can't format for APIs before extracting content. Each stage has a clear input/output contract, which makes the system predictable and allows stages to be developed independently.

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

The split system exists because sometimes you need granular analysis instead of holistic summaries. Instead of asking "what's in this document?", you can ask "what insights can I extract from each section?" The split functions in `src/attachments/split.py` transform single attachments into `AttachmentCollection` objects, enabling vectorized processing where operations automatically apply to each chunk.

### Overview

**Location**: `src/attachments/split.py`

The Split system **expands** single attachments into `AttachmentCollection` objects for **vectorized processing** and **LLM-friendly chunking**.

```
Single Attachment → AttachmentCollection (Multiple Chunks)
```

### Split Functions

**Text Splitting:**
- `paragraphs`: Split on double newlines
- `sentences`: Split on sentence boundaries (`.!?`)
- `tokens`: Split by approximate token count (~4 chars/token)
- `characters`: Split by character count
- `lines`: Split by line count
- `custom`: Split by custom separator from DSL commands

**Document Splitting:**
- `pages`: Extract pages from PDFs/presentations
- `slides`: Extract slides from PowerPoint
- `sections`: Split HTML by headings

**Data Splitting:**
- `rows`: Split DataFrames by row chunks
- `columns`: Split DataFrames by column chunks

### Split Architecture

**Registration Pattern:**
```python
@splitter
def paragraphs(att: Attachment, text: str) -> AttachmentCollection:
    """Split text content into paragraphs."""
    content = att.text if att.text else text
    paragraphs = re.split(r'\n\s*\n', content.strip())
    
    chunks = []
    for i, paragraph in enumerate(paragraphs):
        chunk = Attachment(f"{att.path}#paragraph-{i+1}")
        chunk.text = paragraph
        chunk.metadata = {
            **att.metadata,
            'chunk_type': 'paragraph',
            'chunk_index': i,
            'original_path': att.path
        }
        chunks.append(chunk)
    
    return AttachmentCollection(chunks)
```

**Key Differences from Modifiers:**
- **Input**: `(att: Attachment, content: str)` or `(att: Attachment, obj: ObjectType)`
- **Output**: `AttachmentCollection` (multiple chunks)
- **Registry**: `_splitters` (separate from modifiers)
- **Purpose**: Expand single attachment into multiple chunks

---

## Vectorization & Collections

The `AttachmentCollection` class solves the problem of applying operations to multiple chunks efficiently. When you split a document, you get a collection that automatically vectorizes operations—`chunks | present.markdown` extracts markdown from every chunk, while `chunks | adapt.claude()` intelligently combines everything for the AI. The `_is_reducer()` method determines whether an operation should vectorize (apply to each item) or reduce (combine items).

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

The match system centralizes file type detection logic in reusable predicates. Instead of scattering `att.path.endswith('.pdf')` checks throughout the codebase, match functions in `src/attachments/matchers.py` provide consistent, testable logic for determining which loaders handle which files. This includes complex cases like distinguishing between downloadable URLs and web pages.

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

Each component type has specific patterns and challenges. Loaders deal with import errors and file corruption, presenters handle type dispatch and content extraction, modifiers read DSL commands and transform objects. Understanding these patterns helps when extending the system or debugging issues.

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
    if 'pages' not in att.commands:
        return att
    
    pages_spec = att.commands['pages']
    # Parse page ranges: "1,3-5,-1"
    # Extract specified pages
    return att
```

**Type Safety:**
- Type hints ensure modifiers only apply to compatible objects
- Runtime type checking prevents errors
- Graceful skipping when commands don't apply

**DSL Command Usage:**
- Modifiers read DSL commands from `att.commands` (parsed earlier by `Attachment._parse_attachy()`)
- Other component types also read DSL commands: presenters (`format`, `images`), splitters (`tokens`, `characters`), refiners (`truncate`, `tile`), loaders (`ignore`, `files`), and adapters (`prompt`)

---

## Extension System

The extension system is designed around the principle that adding a new component should feel natural, not like fighting the framework. The decorator-based registration means your function automatically gets type dispatch, error handling, namespace organization, and IDE support. The key insight is that once you implement one verb for a file type, it immediately works with all the other verbs.

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

## High-Level API Design

The `Attachments` class in `src/attachments/highest_level_api.py` is where all the complexity gets hidden behind a simple interface. It automatically detects file types, selects appropriate processors, handles errors gracefully, and formats output for LLM consumption. The `_auto_process()` method tries specialized processors first, then falls back to a universal pipeline that works for any file type.

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

The processor system provides pre-built, battle-tested pipelines for common file types. Located in `src/attachments/pipelines/`, these processors handle the edge cases and optimizations that come from real-world usage. The `find_primary_processor()` function automatically selects the best processor for each file type, while named processors allow specialized workflows.

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

File processing fails in predictable ways: missing dependencies, corrupted files, network issues. The error handling system in `src/attachments/core.py` provides helpful error messages with installation instructions, graceful fallbacks to simpler processing methods, and automatic cleanup of temporary resources. The goal is software that bends rather than breaks.

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

## Contributing New Components

The architecture is designed to make contributing feel natural. Each component type follows consistent patterns, gets automatic integration with the existing infrastructure, and benefits from shared functionality like error handling and type dispatch. The key is understanding which verb category your function belongs to and following the established patterns.

### Quick Start Checklist

**Adding a New Loader:**
- [ ] Create loader function with `@loader` decorator
- [ ] Add match function for file type detection
- [ ] Handle import errors gracefully
- [ ] Set `att._obj` to the loaded object (type dispatch happens automatically)
- [ ] Test with various file formats

**Adding a New Presenter:**
- [ ] Create presenter function with `@presenter` decorator
- [ ] Add type hints for the object parameter (enables type dispatch)
- [ ] Use `att.text +=` to preserve existing content (supports `+` additive operator)
- [ ] Add relevant metadata to `att.metadata`
- [ ] Handle exceptions gracefully

**Adding a New Modifier:**
- [ ] Create modifier function with `@modifier` decorator
- [ ] Add type hints for the object parameter (enables type dispatch)
- [ ] Read DSL commands from `att.commands` if needed
- [ ] Modify `att._obj` in place and return the attachment
- [ ] Handle edge cases gracefully

**Adding a New Splitter:**
- [ ] Create splitter function with `@splitter` decorator
- [ ] Add type hints for the content parameter (text or object)
- [ ] Return `AttachmentCollection` with multiple chunks
- [ ] Copy metadata and commands to each chunk
- [ ] Add chunk-specific metadata (index, type, etc.)

**Adding a New Adapter:**
- [ ] Create adapter function with `@adapter` decorator
- [ ] Handle both `Attachment` and `AttachmentCollection` inputs
- [ ] Use `_handle_collection()` helper to convert collections
- [ ] Format according to target API specification
- [ ] Include proper error handling for missing dependencies

**Key Operator Behaviors:**
- **`|` (pipe) operator**: Overwrites/replaces content - each step transforms the attachment
- **`+` (plus) operator**: Additive composition - combines multiple presenters
  - Presenters **must use `att.text +=`** to append content (not `att.text =`)
  - Example: `present.text + present.images + present.metadata` combines all outputs
  - Loaders and refiners can use `att.text =` since they're not typically used with `+`

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

---

## Advanced Topics

> [!NOTE]
> This section is a work in progress.

### Custom Pipeline Composition

The pipeline system supports sophisticated composition patterns that enable reusable, modular processing workflows. Based on the codebase patterns in `src/attachments/core.py` and `src/attachments/pipelines/`, here are the key composition techniques:

#### **Reusable Pipeline Functions**
```python
# Create callable pipeline functions by assigning to variables
csv_analyzer = (load.csv_to_pandas 
               | modify.limit 
               | present.head + present.summary + present.metadata
               | refine.add_headers)

# Use as function with any CSV file
result = csv_analyzer("sales_data.csv[limit:100]")
analysis = result.claude("What patterns do you see?")

# Apply to multiple files
for file in ["q1.csv", "q2.csv", "q3.csv"]:
    quarterly_data = csv_analyzer(file)
    insights = quarterly_data.openai_chat("Summarize key metrics")
```

#### **Conditional Pipeline Branching**
```python
# Smart pipeline that adapts based on file type
universal_processor = (
    load.pdf_to_pdfplumber |     # Try PDF first
    load.csv_to_pandas |         # Then CSV
    load.image_to_pil |          # Then images
    load.text_to_string          # Finally text fallback
)

# Different presentation based on content type
def smart_presenter(att):
    if hasattr(att._obj, 'columns'):  # DataFrame
        return present.head + present.summary
    elif hasattr(att._obj, 'size'):  # PIL Image
        return present.images + present.metadata
    else:  # Text or other
        return present.markdown + present.metadata

# Combine into adaptive pipeline
adaptive = universal_processor | smart_presenter | refine.add_headers
```

#### **Pipeline Composition with Fallbacks**
```python
# Primary pipeline with fallback chain (from src/attachments/core.py)
robust_pdf = Pipeline(
    steps=[load.pdf_to_pdfplumber, present.markdown, refine.add_headers],
    fallback_pipelines=[
        Pipeline([load.text_to_string, present.text]),  # Text fallback
        Pipeline([load.image_to_pil, present.images])   # Image fallback
    ]
)

# If PDF processing fails, automatically tries text then image processing
result = robust_pdf("document.pdf")
```

#### **Vectorized Collection Processing**
```python
# Split documents into chunks for granular analysis
chunked_analysis = (attach("large_document.pdf")
                   | load.pdf_to_pdfplumber
                   | split.pages                    # → AttachmentCollection
                   | present.markdown               # Vectorized: each page
                   | refine.add_headers             # Vectorized: each page
                   | adapt.claude("Analyze each page separately"))

# Process ZIP archives with vectorization
image_batch = (attach("photos.zip")
              | load.zip_to_images               # → AttachmentCollection
              | present.images                   # Vectorized: each image
              | refine.tile_images)              # Reducer: combine into grid
```

#### **Method-Style Pipeline API**
```python
# Pipelines automatically expose adapter methods (from highest_level_api.py)
document_processor = (load.pdf_to_pdfplumber 
                     | present.markdown + present.images
                     | refine.add_headers)

# All these work automatically:
claude_result = document_processor.claude("report.pdf", "Summarize key points")
openai_result = document_processor.openai_chat("report.pdf", "Extract action items")
dspy_result = document_processor.dspy("report.pdf")
```

### Performance Optimization

The codebase implements several performance optimization strategies, particularly for memory management and large file handling:

#### **Lazy Loading and Memory Management**

**Size-Based Early Exit** (from `src/attachments/loaders/repositories/`):
```python
# Repositories check total size before processing files
size_limit_mb = 500
size_limit_bytes = size_limit_mb * 1024 * 1024

# Early exit prevents memory issues during file collection
if total_size > size_limit_bytes:
    if not force_process:
        # Return size warning instead of processing
        return create_size_warning_attachment(att, total_size, file_count)
```

**Efficient File Collection** (from `src/attachments/loaders/repositories/utils.py`):
```python
# Binary file detection prevents loading problematic files
def is_likely_binary(file_path: str) -> bool:
    problematic_extensions = {
        '.exe', '.dll', '.so', '.dylib', '.bin', '.obj', '.o',
        '.pyc', '.pyo', '.pyd', '.class', '.woff', '.woff2'
    }
    
    # Check first 1024 bytes for null bytes (binary indicator)
    with open(file_path, 'rb') as f:
        chunk = f.read(1024)
        if b'\x00' in chunk:
            return True
```

**Namespace Caching** (from `src/attachments/highest_level_api.py`):
```python
# Global cache prevents repeated namespace imports
_cached_namespaces = None

def _get_cached_namespaces():
    global _cached_namespaces
    if _cached_namespaces is None:
        _cached_namespaces = _get_namespaces()
    return _cached_namespaces
```

#### **Image Processing Optimization**

**Efficient Image Tiling** (from `src/attachments/refine.py`):
```python
# Resize to smallest common dimensions for memory efficiency
min_width = min(img.size[0] for img in tile_images_subset)
min_height = min(img.size[1] for img in tile_images_subset)

# Don't make images too small
min_width = max(min_width, 100)
min_height = max(min_height, 100)

resized_images = [img.resize((min_width, min_height)) for img in tile_images_subset]
```

**Smart Truncation** (from `src/attachments/highest_level_api.py`):
```python
# Apply truncation only for very long text
if hasattr(processed, 'text') and processed.text and len(processed.text) > 5000:
    processed = processed | refine.truncate(3000)
```

#### **Performance Best Practices**

1. **Use DSL Commands for Filtering**:
   ```python
   # Efficient: Filter at load time
   small_data = Attachments("large_file.csv[limit:1000]")
   
   # Less efficient: Load everything then filter
   all_data = Attachments("large_file.csv") | modify.limit
   ```

2. **Leverage Repository Ignore Patterns**:
   ```python
   # Efficient: Skip unnecessary files
   codebase = Attachments("./project[ignore:standard]")
   
   # Inefficient: Process all files including build artifacts
   codebase = Attachments("./project")
   ```

3. **Use Appropriate Processing Modes**:
   ```python
   # Structure only (fast)
   structure = Attachments("./large-repo[mode:structure]")
   
   # Full content processing (slower)
   content = Attachments("./large-repo[mode:content]")
   ```

### Debugging and Introspection

The architecture provides several debugging and introspection capabilities:

#### **Pipeline Tracking**

**Automatic Pipeline History** (from `src/attachments/core.py`):
```python
# Each attachment tracks its processing pipeline
att = attach("document.pdf")
result = att | load.pdf_to_pdfplumber | present.markdown | refine.add_headers

print(result.pipeline)  # ['pdf_to_pdfplumber', 'markdown', 'add_headers']
```

**Detailed Repr for Debugging**:
```python
# Attachment.__repr__ shows processing state
att = Attachment("document.pdf")
print(repr(att))
# Attachment(path='document.pdf', text=1234 chars, images=[2 imgs: data:image/png;base64,iVBOR...], pipeline=['pdf_to_pdfplumber', 'markdown'])
```

#### **Error Handling and Fallbacks**

**Graceful Error Recovery** (from `src/attachments/core.py`):
```python
def _execute_steps(self, result: 'Attachment', steps: List[Callable]) -> Any:
    for step in steps:
        try:
            result = step(result)
        except Exception as e:
            # Log error but continue pipeline
            result.metadata['errors'] = result.metadata.get('errors', [])
            result.metadata['errors'].append(f"{step.__name__}: {str(e)}")
    return result
```

**Helpful Error Messages** (from `src/attachments/core.py`):
```python
def _create_helpful_error_attachment(att: Attachment, import_error: ImportError, loader_name: str):
    dependency_map = {
        'pdf_to_pdfplumber': 'pip install pdfplumber',
        'csv_to_pandas': 'pip install pandas',
        'image_to_pil': 'pip install Pillow',
    }
    
    install_cmd = dependency_map.get(loader_name, 'pip install attachments[all]')
    att.text = f"⚠️ Missing dependency for {att.path}\n\nInstall: {install_cmd}"
```

#### **Processor Discovery and Introspection**

**List Available Processors** (from `src/attachments/pipelines/__init__.py`):
```python
from attachments.pipelines import list_available_processors

# Get all registered processors
processors = list_available_processors()
print(processors['primary_processors'])    # Auto-selected processors
print(processors['named_processors'])      # Specialized processors

# Find processors for specific files
from attachments.pipelines import _processor_registry
matching = _processor_registry.list_processors_for_file(attach("document.pdf"))
```

**Registry Inspection**:
```python
from attachments.core import _loaders, _presenters, _modifiers

# Inspect registered components
print("Available loaders:", list(_loaders.keys()))
print("Available presenters:", list(_presenters.keys()))
print("Available modifiers:", list(_modifiers.keys()))

# Check type dispatch for presenters
for name, handlers in _presenters.items():
    print(f"{name}: {[h[0] for h in handlers]}")  # Show type annotations
```

#### **Debugging Utilities**

**Metadata Inspection**:
```python
# Check processing metadata
result = Attachments("document.pdf")
print(result.attachments[0].metadata)
# Shows: file info, processing steps, errors, performance metrics

# Check for processing errors
if 'errors' in result.attachments[0].metadata:
    print("Processing errors:", result.attachments[0].metadata['errors'])
```

**Pipeline State Inspection**:
```python
# Create pipeline and inspect state at each step
att = attach("document.pdf")

# Step by step debugging
loaded = att | load.pdf_to_pdfplumber
print(f"After loading: {type(loaded._obj)}")

presented = loaded | present.markdown
print(f"After presenting: {len(presented.text)} chars")

refined = presented | refine.add_headers
print(f"After refining: {refined.text[:100]}...")
```

### Integration Patterns

The architecture supports integration with major LLM libraries and frameworks:

#### **OpenAI Integration**

**Chat Completions API** (from `src/attachments/adapt.py`):
```python
from openai import OpenAI
from attachments import Attachments

# Direct integration
client = OpenAI()
doc = Attachments("report.pdf")

# Method 1: Using adapter
messages = doc.openai_chat("Analyze this document")
response = client.chat.completions.create(
    model="gpt-4-turbo",
    messages=messages
)

# Method 2: Using pipeline
response = (attach("report.pdf")
           | load.pdf_to_pdfplumber
           | present.markdown + present.images
           | adapt.openai_chat("Analyze this document"))
```

**Responses API** (newer OpenAI format):
```python
# OpenAI Responses API format
response_input = doc.openai_responses("Analyze this document")
response = client.responses.create(
    input=response_input,
    model="gpt-4-turbo"
)
```

#### **Anthropic Claude Integration**

**Message Format** (from `src/attachments/adapt.py`):
```python
import anthropic
from attachments import Attachments

# Direct integration
client = anthropic.Anthropic()
doc = Attachments("presentation.pptx")

# Claude format with image support
messages = doc.claude("Analyze these slides")
response = client.messages.create(
    model="claude-3-5-sonnet-20241022",
    max_tokens=4000,
    messages=messages
)

# Pipeline approach
analysis = (attach("presentation.pptx")
           | load.pptx_to_python_pptx
           | present.markdown + present.images
           | adapt.claude("What are the key insights?"))
```

#### **DSPy Integration**

**Seamless DSPy Compatibility** (from `src/attachments/dspy.py`):
```python
import dspy
from attachments.dspy import Attachments  # Special DSPy-optimized import

# Configure DSPy
dspy.configure(lm=dspy.LM('openai/gpt-4-turbo'))

# Direct usage in DSPy signatures
rag = dspy.ChainOfThought("question, document -> answer")

# No .dspy() call needed with special import
doc = Attachments("research_paper.pdf")
result = rag(question="What are the main findings?", document=doc)

# Alternative: Regular import with explicit adapter
from attachments import Attachments
doc = Attachments("research_paper.pdf").dspy()
result = rag(question="What are the main findings?", document=doc)
```

**DSPy BaseType Compatibility**:
```python
# The DSPy adapter creates Pydantic models compatible with DSPy
dspy_obj = doc.dspy()
print(dspy_obj.model_dump())  # Pydantic serialization
print(dspy_obj.serialize_model())  # DSPy serialization
```

#### **Custom LLM Library Integration**

**Creating Custom Adapters**:
```python
from attachments.core import adapter, Attachment

@adapter
def custom_llm(att: Attachment, prompt: str = "") -> dict:
    """Adapter for custom LLM library."""
    return {
        'prompt': prompt,
        'content': att.text,
        'images': att.images,
        'metadata': att.metadata,
        'format': 'custom_format_v1'
    }

# Use immediately after registration
result = Attachments("document.pdf").custom_llm("Analyze this")
```

#### **Langchain Integration Pattern**

```python
# Example integration with Langchain (not built-in)
from langchain.schema import Document
from attachments import Attachments

def attachments_to_langchain(attachments_obj):
    """Convert Attachments to Langchain Documents."""
    documents = []
    for att in attachments_obj.attachments:
        doc = Document(
            page_content=att.text,
            metadata={
                **att.metadata,
                'source': att.path,
                'images': att.images
            }
        )
        documents.append(doc)
    return documents

# Usage
docs = Attachments("document.pdf", "data.csv")
langchain_docs = attachments_to_langchain(docs)
```

#### **Streaming and Async Patterns**

```python
# Async processing pattern
import asyncio
from attachments import Attachments

async def process_documents_async(file_paths):
    """Process multiple documents asynchronously."""
    tasks = []
    for path in file_paths:
        task = asyncio.create_task(process_single_doc(path))
        tasks.append(task)
    
    results = await asyncio.gather(*tasks)
    return results

async def process_single_doc(path):
    """Process single document (run in thread pool for CPU-bound work)."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: Attachments(path))

# Usage
results = asyncio.run(process_documents_async(["doc1.pdf", "doc2.pdf"]))
```

---

## Conclusion

The Attachments architecture is designed to be **simple for users** but **powerful for contributors**. The five-stage pipeline provides clear separation of concerns, while the registration system makes it easy to add new capabilities.

Key architectural strengths:
- **Modularity**: Each component has a single, clear responsibility
- **Extensibility**: New file types and transformations via simple decorators
- **Composability**: Components can be mixed and matched

Whether you're using the simple `Attachments("file.pdf")` API or building complex pipelines, the architecture scales to meet your needs while maintaining consistency and reliability.

---

*This document is a living guide. As the architecture evolves, we'll update it to reflect new patterns and best practices. Contributions and feedback are welcome!* 