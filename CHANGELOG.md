# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.8.0] - 2025-01-23

### 🚀 Major Features

- **Enhanced URL Morphing Architecture**: Complete redesign of URL processing with intelligent file type detection
  - Replace hardcoded file extension lists with smart enhanced matchers
  - New `url_to_response` + `morph_to_detected_type` architecture for all URL processing
  - Enhanced matchers now check Content-Type headers, magic numbers, and file extensions automatically
  - Zero hardcoded file type lists across the entire codebase

### ✨ Improvements

- **Enhanced Attachment Class**: Added comprehensive helper methods for intelligent content analysis
  - `att.content_type` - Easy access to Content-Type headers from HTTP responses
  - `att.has_content` - Check if URL content is available
  - `att.get_magic_bytes(n)` - Cached magic number detection for binary file identification
  - `att.has_magic_signature(sigs)` - Test multiple binary signatures at once
  - `att.contains_in_content(patterns)` - Search for patterns in ZIP-based office formats
  - `att.is_likely_text()` - Intelligent text vs binary content detection
  - `att.get_text_sample(n)` - Safe text decoding with caching
  - `att.input_source` and `att.text_content` properties eliminate repetitive loader patterns

- **Enhanced @loader Decorator**: Automatic input source detection and preparation
  - Eliminates `getattr(att, '_file_content', None) or att.path` patterns from all loaders
  - Automatic handling of URL content vs file path inputs
  - Centralized error handling for missing dependencies

- **System-wide Processor Updates**: All file type processors now use the new morphing architecture
  - PDF, CSV, PPTX, DOCX, Excel, and Image processors updated
  - Consistent URL handling across all file types
  - Automatic detection works for any new loader without configuration

### 🐛 Bug Fixes

- **URL Display**: Fixed URLs showing temporary filenames instead of original URLs in headers
  - PDFs from URLs now show `https://example.com/doc.pdf` instead of `/tmp/tmpXXX.pdf`
  - Enhanced `display_url` metadata preservation across the processing pipeline

- **Binary Content Handling**: Improved binary content detection to prevent decode warnings
  - Better detection of binary vs text content from URLs
  - Prevents "replacement character" warnings when processing images and other binary files

### 📚 Documentation

- **URL Morphing Tutorial**: New comprehensive tutorial at `docs/scripts/how_to_load_and_morph.py`
  - Step-by-step progression from wrong approaches to best practices
  - Interactive Jupyter notebook version available
  - Demonstrates the evolution from hardcoded lists to intelligent detection

### 🔧 Technical Changes

- **Enhanced Matchers**: All matchers (`pdf_match`, `image_match`, etc.) now intelligently check:
  - File extensions: `att.path.endswith('.pdf')`
  - Content-Type headers: `'pdf' in att.metadata['content_type']`
  - Magic numbers: `att._file_content` starts with `b'%PDF'`
  - No configuration required - works automatically for URLs and files

- **Simplified Loaders**: 70% code reduction in loaders through automatic input preparation
  - PDF: `att._obj = pdfplumber.open(att.input_source)`
  - Office: `att._obj = Presentation(att.input_source)`
  - Images: `att._obj = Image.open(att.input_source)`
  - Text: `content = att.text_content`

### ⚠️ Breaking Changes

- **Deprecated `url_to_file`**: The old hardcoded `load.url_to_file` approach is deprecated
  - Replace with: `load.url_to_response | modify.morph_to_detected_type`
  - All processors have been updated automatically
  - Old approach will be removed in v1.0.0

### 🔄 Migration Guide

If you were using the old URL processing approach:

```python
# Old approach (deprecated)
att | load.url_to_file | load.pdf_to_pdfplumber

# New approach (recommended)  
att | load.url_to_response | modify.morph_to_detected_type | load.pdf_to_pdfplumber

# Or use processors (automatically uses new approach)
from attachments.pipelines import processors
result = processors.pdf_to_llm(attach("https://example.com/doc.pdf"))
```
