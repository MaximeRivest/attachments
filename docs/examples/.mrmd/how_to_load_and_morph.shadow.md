---
language: python
kernel: .venv
---

# URL Morphing Tutorial

This tutorial demonstrates how to use the intelligent URL morphing system to process files from URLs without hardcoded file type detection.

```python
from attachments import attach, load, modify, present
```

## What is URL Morphing?

URL morphing is a smart system that:
1. Downloads content from URLs
2. Intelligently detects the file type using multiple strategies
3. Transforms the attachment so existing loaders can process it

This enables seamless processing of any file type from URLs without maintaining hardcoded lists.

## Basic Morphing Pattern

The standard pattern is: `url_to_response → morph_to_detected_type → specific_loader`

```python
# Download and morph a PDF from URL
pdf_attachment = (attach("https://github.com/MaximeRivest/attachments/raw/main/src/attachments/data/sample.pdf") |
                 load.url_to_response |           # Step 1: Download content
                 modify.morph_to_detected_type |  # Step 2: Detect file type intelligently  
                 load.pdf_to_pdfplumber |         # Step 3: Load with appropriate loader
                 present.text)                    # Step 4: Extract content
```

```output
CropBox missing from /Page, defaulting to MediaBox
```

Let's see what we got:

```python
len(pdf_attachment.text)
```

```output
458
```

Here's the extracted PDF content:

```python
print(pdf_attachment.text[:200])
```

```output
PDF Document: sample.pdf
========================

[Page 1]
Hello PDF!


DOCUMENT ANALYSIS: This appears to be a scanned PDF with little to no extractable text.

- Pages processed: 1
- Pages with text
```

Perfect! The PDF was properly detected and loaded. Let's examine how the detection worked:

```python
pdf_attachment.path
```

```output
'sample.pdf'
```

The original URL was transformed to a clean filename. Let's see the detection metadata:

```python
{
    'detected_extension': pdf_attachment.metadata.get('detected_extension'),
    'detection_method': pdf_attachment.metadata.get('detection_method'),
    'content_type': pdf_attachment.metadata.get('response_content_type')
}
```

```output
{'detected_extension': '.pdf',
 'detection_method': 'enhanced_matcher_based',
 'content_type': 'application/octet-stream'}
```

## How Detection Works

The morphing system uses three strategies to detect file types:
1. **File extension** from the URL path
2. **Content-Type header** from the HTTP response
3. **Magic number signatures** from the file content

This triple-check approach ensures reliable detection even when URLs don't have clear extensions.

## Working with Different File Types

Let's try morphing with different file formats:

```python
# PowerPoint presentation
pptx_result = (attach("https://github.com/MaximeRivest/attachments/raw/main/src/attachments/data/sample_multipage.pptx") |
               load.url_to_response |
               modify.morph_to_detected_type |
               load.pptx_to_python_pptx |
               present.text)
```

PowerPoint content length:

```python
len(pptx_result.text)
```

```output
1427
```

Detected file type:

```python
pptx_result.path
```

```output
'sample_multipage.pptx'
```

```python
# Markdown file
md_result = (attach("https://raw.githubusercontent.com/MaximeRivest/attachments/main/README.md") |
             load.url_to_response |
             modify.morph_to_detected_type |
             load.text_to_string |
             present.text)
```

Markdown content length:

```python
len(md_result.text)
```

```output
29883
```

Detected file type:

```python
md_result.path
```

```output
'README.md'
```

## Why Morphing is Essential

Without morphing, URL processing fails because loaders use file extensions to determine if they should handle a file. URLs don't match these patterns.

Let's see what happens without morphing:

```python
# This will fail - PDF loader won't recognize the URL
failed_attempt = (attach("https://github.com/MaximeRivest/attachments/raw/main/src/attachments/data/sample.pdf") |
                 load.url_to_response |           # Downloads content
                 load.pdf_to_pdfplumber |         # But matcher fails - path is still a URL!
                 present.text)
```

Without morphing, the content isn't processed correctly:

```python
len(failed_attempt.text)
```

```output
104
```

The result is just the response object representation:

```python
failed_attempt.text
```

```output
'https://github.com/MaximeRivest/attachments/raw/main/src/attachments/data/sample.pdf: <Response [200]>\n\n'
```

## Automatic Morphing in Pipelines

The universal pipeline automatically includes morphing for URLs, so you often don't need to specify it manually:

```python
from attachments import Attachments

# This automatically uses morphing
auto_result = Attachments("https://github.com/MaximeRivest/attachments/raw/main/src/attachments/data/sample.pdf")
auto_text = str(auto_result)
```

```output
CropBox missing from /Page, defaulting to MediaBox
```

Automatic processing result length:

```python
len(auto_text)
```

```output
798
```

First part of the automatically processed content:

```python
print(auto_text[:200])
```

```output
# PDF Document: /tmp/tmphnl64qqm.pdf

## Page 1

Hello PDF!


📄 **Document Analysis**: This appears to be a scanned PDF with little to no extractable text.

- **Pages processed**: 1
- **Pages with tex
```

## Advanced: Understanding the Detection Process

Let's trace through how morphing detects a PDF file:

```python
# Create an attachment with PDF URL
pdf_url = attach("https://github.com/MaximeRivest/attachments/raw/main/src/attachments/data/sample.pdf")

# Step 1: Download
downloaded = pdf_url | load.url_to_response
print("After download:")
print(f"  Path: {downloaded.path}")
print(f"  Content-Type: {downloaded.metadata.get('content_type')}")
print(f"  Object type: {type(downloaded._obj)}")

# Step 2: Morph  
morphed = downloaded | modify.morph_to_detected_type
print("\nAfter morphing:")
print(f"  Path: {morphed.path}")
print(f"  Detected extension: {morphed.metadata.get('detected_extension')}")
print(f"  Detection method: {morphed.metadata.get('detection_method')}")
```

```output
After download:
  Path: https://github.com/MaximeRivest/attachments/raw/main/src/attachments/data/sample.pdf
  Content-Type: application/octet-stream
  Object type: <class 'requests.models.Response'>

After morphing:
  Path: sample.pdf
  Detected extension: .pdf
  Detection method: enhanced_matcher_based
```

## Best Practices

### 1. Use the Standard Pattern
For manual pipelines with URLs, always use: `url_to_response → morph_to_detected_type`

### 2. Let Enhanced Matchers Do Their Work
The system automatically checks file extensions, Content-Type headers, and magic numbers. No need for manual detection.

### 3. Trust the Detection
The morphing system is designed to be robust. It will fall back gracefully if detection is uncertain.

### 4. For Simple Cases, Use Automatic Processing
`Attachments()` or the universal pipeline handle morphing automatically.

## Summary

URL morphing enables seamless processing of any file type from URLs by:
- Downloading content intelligently
- Detecting file types using multiple strategies  
- Transforming attachments so existing loaders can process them
- Maintaining zero hardcoded file type lists

This creates an extensible system where adding new file types automatically enables URL support!
