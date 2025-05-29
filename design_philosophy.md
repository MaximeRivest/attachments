## **The Complete Attachments Design Principles**

Based on studying the entire architecture, here are the **10 Core Design Principles** that drive every decision:

---

## **1. Grammar-Based Composability**
> *"File processing as a composable language, not a collection of random functions"*

**Philosophy**: Inspired by dplyr and ggplot2, file processing is modeled as a **grammar of 6 composable verbs** that work consistently across all file types.

**Implementation**:
- **`load.*`**: File → Object
- **`modify.*`**: Object → Object  
- **`split.*`**: Object → Collection
- **`present.*`**: Object → text/images/metadata
- **`refine.*`**: Content → Polished Content
- **`adapt.*`**: Content → API Format

**Composition Operators**:
- **`|` (pipe)**: Sequential transformation
- **`+` (plus)**: Additive combination
- **Natural chaining**: `attach("doc.pdf") | load.pdf_to_pdfplumber | present.markdown`

**Why This Matters**: Same pattern works for PDFs, CSVs, images, URLs. Learn once, apply everywhere.

---

## **2. Content Fidelity First**
> *"User input is sacred - preserve 100% by default"*

**Philosophy**: LLMs need complete context to give accurate answers. We preserve all user content by default and make limitations explicit user choices.

**Implementation**:
- **No silent truncations** - If content is limited, user explicitly requested it
- **No arbitrary limits** - We don't decide what's "too much" for user's use case
- **Full extraction** - When user asks for PDF, they get whole PDF (all pages, all text, all images)
- **Explicit control** - `[truncate:5000]` vs automatic hidden truncation

**Examples**:
```python
# Full content by default
full_doc = Attachments("report.pdf")  # ALL pages, ALL content

# Explicit user choice
limited_doc = Attachments("report.pdf[pages:1-5][truncate:1000]")
```

**Why This Matters**: Users know their use case better than we do. Provide everything, let them decide.

---

## **3. Type-Intelligent Dispatch**
> *"Smart routing based on what the content actually is"*

**Philosophy**: The system should automatically route content through the right processing pipeline based on file types, object types, and content characteristics.

**Implementation**:
- **Match functions**: `lambda att: att.path.endswith('.pdf')`
- **Type dispatch**: Multiple handlers per object type with automatic selection
- **Fallback chains**: Specialized → Generic → Text fallback
- **Runtime intelligence**: Detect file types, content formats, processing capabilities

**Examples**:
```python
# Same interface, different processing paths
Attachments("document.pdf")      # → PDF pipeline
Attachments("data.csv")          # → Pandas pipeline  
Attachments("image.jpg")         # → PIL pipeline
Attachments("https://site.com")  # → Web scraping pipeline
```

**Why This Matters**: Users shouldn't need to know implementation details. The system should "just work."

---

## **4. Dual-Level API Design**
> *"Simple for 90% of cases, powerful for complex workflows"*

**Philosophy**: Provide a zero-learning-curve API for common tasks while enabling sophisticated workflows for power users.

**API Levels**:
```python
# Level 1: Simple API (90% of use cases)
ctx = Attachments("document.pdf", "data.csv") 
result = ctx.claude("Analyze this")

# Level 2: Grammar API (complex workflows)
analysis = (attach("report.pdf")
           | load.pdf_to_pdfplumber
           | split.pages
           | present.markdown + present.images  
           | refine.add_headers
           | adapt.claude("Analyze each page"))
```

**Graceful Progression**: Start simple, add complexity only when needed.

**Why This Matters**: Accessibility for beginners, power for experts. No artificial limitations.

---

## **5. User Agency Through DSL**
> *"Explicit control over processing behavior, embedded naturally"*

**Philosophy**: Users should be able to declaratively specify how they want their files processed without learning a complex API.

**DSL Commands**:
```python
"document.pdf[pages:1-5]"                    # Page selection
"image.jpg[rotate:90][crop:100,100,400,300]" # Image transformations
"data.csv[limit:1000][format:summary]"       # Data processing
"url[select:h1,p][format:markdown]"          # Web scraping
```

**Characteristics**:
- **Embedded in file paths** - Natural for non-programmers and LLMs
- **Optional** - Grammar API works without DSL
- **Declarative** - What you want, not how to get it
- **Composable** - Multiple commands can be chained

**Why This Matters**: Users get control without complexity. LLMs can use it as a tool.

---

## **6. Vectorized Processing Intelligence**
> *"Granular analysis, not just holistic summaries"*

**Philosophy**: Sometimes you need to analyze each section, page, or chunk individually rather than treating documents as monolithic blocks.

**Split System**:
```python
# Holistic processing
summary = Attachments("report.pdf").claude("Summarize this")

# Granular processing  
insights = (attach("report.pdf")
           | load.pdf_to_pdfplumber
           | split.pages              # → AttachmentCollection
           | present.markdown         # Vectorized: each page
           | adapt.claude("Analyze each page individually"))
```

**Intelligence**:
- **Automatic vectorization** - Operations apply to each item in collection
- **Smart reduction** - Some operations combine collections (`tile_images`, `claude()`)
- **Chunk-aware metadata** - Track original source, chunk index, relationships

**Why This Matters**: Enables fine-grained analysis that's impossible with holistic approaches.

---

## **7. Performance Through Intelligence**
> *"Smart optimization, not just brute force speed"*

**Philosophy**: Performance comes from intelligent decisions about what to process, when to load, and how to manage memory - not just making everything faster.

**Intelligence Strategies**:
- **Lazy loading** - Load only when needed
- **Size-based early exit** - Warn about large repositories before processing
- **Binary file detection** - Skip problematic files automatically
- **Smart caching** - Namespace and object caching where appropriate
- **Memory management** - Efficient image tiling, chunk processing

**Examples**:
```python
# Smart repository handling
codebase = Attachments("./project[ignore:standard]")  # Skip build artifacts

# Efficient data processing
data = Attachments("huge_file.csv[limit:1000]")       # Filter at load time
```

**Why This Matters**: Users get good performance without thinking about optimization.

---

## **8. Graceful Degradation** 
> *"Software that bends rather than breaks"*

**Philosophy**: File processing fails in predictable ways. The system should provide helpful fallbacks and error messages rather than crashing.

**Fallback Strategies**:
- **Loader chains**: Specialized → Generic → Text fallback
- **Error continuation**: Log errors but continue pipeline
- **Helpful messages**: Installation instructions for missing dependencies
- **Partial success**: Extract what's possible, report what failed

**Examples**:
```python
# Missing dependency handling
att.text = """
⚠️ Missing dependency for document.pdf

To process this file type, install:
  pip install pdfplumber

Or install all dependencies:
  pip install attachments[all]
"""
```

**Why This Matters**: Users get useful results even when things go wrong.

---

## **9. Extensibility Without Complexity**
> *"Adding new capabilities should feel natural, not like fighting the framework"*

**Philosophy**: The system should be easily extensible without requiring deep architectural knowledge or boilerplate code.

**Registration System**:
```python
# Add new file type support
@loader(match=lambda att: att.path.endswith('.xyz'))
def xyz_to_custom(att: Attachment) -> Attachment:
    # Implementation
    return att

# Immediately available everywhere
load.xyz_to_custom  # Automatic namespace integration
Attachments("file.xyz")  # Works in simple API
```

**Automatic Integration**:
- **Decorator-based registration** - No manual registry management
- **Type dispatch** - Automatic routing based on type hints  
- **Namespace organization** - Functions automatically appear in appropriate namespaces
- **IDE support** - Autocomplete works automatically

**Why This Matters**: Contributors can focus on functionality, not infrastructure.

---

## **10. Developer Experience Focus**
> *"APIs should feel intuitive and provide helpful feedback"*

**Philosophy**: The system should guide users toward success with clear patterns, helpful errors, and discoverable functionality.

**Experience Features**:
- **Consistent patterns** - Same interface across all file types
- **IDE autocomplete** - Smart namespace discovery
- **Pipeline tracking** - Debug what happened to your content
- **Helpful errors** - Clear messages with actionable solutions
- **Introspection tools** - Understand what's available and why

**Examples**:
```python
# Clear pipeline history
result.pipeline  # ['pdf_to_pdfplumber', 'markdown', 'add_headers']

# Helpful debugging
print(repr(result))  # Shows content lengths, processing steps, errors

# Discovery tools
from attachments.core import _loaders
print(list(_loaders.keys()))  # See what's available
```

**Why This Matters**: Users spend time solving their problems, not fighting the library.

---
