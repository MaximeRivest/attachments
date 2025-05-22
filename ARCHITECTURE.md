# Attachments Library Architecture

## Overview

The Attachments library uses a modular, type-safe architecture based on the `opus_notes` prototype. The design emphasizes:

- **Modularity**: Each component has a single responsibility
- **Type Safety**: Dispatch based on actual Python types
- **Extensibility**: Easy to add new file types and operations
- **Composability**: Operations can be chained and combined

## Module Structure

```
src/attachments/
├── __init__.py              # High-level Attachments interface (user-facing)
├── core/
│   ├── __init__.py          # Core exports
│   ├── attachment.py        # Attachment container class
│   ├── namespaces.py        # load, modify, present, adapt namespaces  
│   ├── decorators.py        # @loader, @modifier, @presenter, @adapter
│   └── dispatch.py          # Type-based dispatch logic
├── loaders/
│   ├── __init__.py          # Auto-register all loaders
│   ├── pdf.py              # PDF loading with PyMuPDF
│   ├── csv.py              # CSV loading with pandas
│   ├── image.py            # Image loading with PIL
│   ├── docx.py             # Word document loading (future)
│   ├── xlsx.py             # Excel loading (future)
│   └── base.py             # Base loader patterns
├── modifiers/
│   ├── __init__.py          # Auto-register all modifiers
│   ├── pages.py            # Page extraction for documents
│   ├── sample.py           # Data sampling for large datasets
│   ├── resize.py           # Image resizing and transforms
│   ├── rotate.py           # Image rotation (future)
│   └── base.py             # Base modifier patterns
├── presenters/
│   ├── __init__.py          # Auto-register all presenters
│   ├── text.py             # Text extraction
│   ├── images.py           # Image generation (render as images)
│   ├── markdown.py         # Markdown formatting
│   ├── html.py             # HTML formatting (future)
│   └── base.py             # Base presenter patterns
├── adapters/
│   ├── __init__.py          # Auto-register all adapters
│   ├── openai.py           # OpenAI API formatting
│   ├── claude.py           # Claude API formatting
│   ├── gemini.py           # Google Gemini formatting (future)
│   └── base.py             # Base adapter patterns
└── utils/
    ├── __init__.py
    ├── parsing.py           # Path expression parsing
    └── types.py             # Common type definitions
```

## Component Types

### 1. Loaders
- **Purpose**: Load files into Python objects
- **Input**: File path or URL (string)
- **Output**: Attachment with loaded content
- **Example**: `load.pdf("doc.pdf")` → Attachment with fitz.Document

### 2. Modifiers  
- **Purpose**: Transform or filter content
- **Input**: Attachment
- **Output**: Attachment with modified content
- **Example**: `modify.pages(att, "1-3")` → Attachment with selected pages

### 3. Presenters
- **Purpose**: Convert content to specific formats
- **Input**: Attachment  
- **Output**: Attachment with presented content (text, images, etc.)
- **Example**: `present.text(att)` → Attachment with extracted text

### 4. Adapters
- **Purpose**: Format content for specific APIs
- **Input**: Attachment
- **Output**: API-specific format (dict/list)
- **Example**: `adapt.openai(att, prompt)` → OpenAI message format

## Type Dispatch System

Each component uses Python's type system for safe dispatch:

```python
@modifier
def pages(pdf_doc: fitz.Document, page_spec: str) -> fitz.Document:
    # Only applies to PyMuPDF documents
    
@presenter  
def text(pdf_doc: fitz.Document) -> str:
    # PDF-specific text extraction
    
@presenter
def text(df: pd.DataFrame) -> str:  
    # DataFrame-specific text extraction
```

## Registration and Discovery

Components auto-register themselves using decorators:

```python
# In loaders/pdf.py
@loader(lambda path: path.endswith('.pdf'))
def pdf(path: str) -> fitz.Document:
    return fitz.open(path)

# In presenters/text.py  
@presenter
def text(pdf_doc: fitz.Document) -> str:
    return extract_text_from_pdf(pdf_doc)
```

## Pipeline Composition

Operations compose naturally:

```python
# Step by step
att = load.pdf("doc.pdf[pages: 1-3]")
att = modify.pages(att)
text_att = present.text(att)
openai_format = adapt.openai(text_att, "Analyze this")

# Future: Pipeline syntax
result = (load.pdf("doc.pdf[pages: 1-3]") 
          | modify.pages() 
          | present.text() 
          | adapt.openai("Analyze this"))
```

## Benefits

1. **Easy Extension**: Drop new components in appropriate directories
2. **Type Safety**: Wrong types caught at dispatch time, not runtime
3. **Separation of Concerns**: Each module has clear responsibility
4. **Testability**: Each component can be unit tested in isolation
5. **Performance**: Only load components that are actually used
6. **IDE Support**: Full autocomplete and type hints

## Future Extensions

This architecture makes it trivial to add:
- New file types (PowerPoint, Excel, HTML, etc.)
- New presentation formats (JSON, XML, etc.)  
- New API adapters (Gemini, Cohere, etc.)
- New content modifiers (translation, summarization, etc.)

Each new component is just a decorated function in the right directory! 