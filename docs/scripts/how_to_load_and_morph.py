# %% [markdown]
# # URL Morphing Tutorial
#
# This tutorial demonstrates how to use the intelligent URL morphing system to process files from URLs without hardcoded file type detection.
#
# 
# %%
from attachments import attach, load, modify, present

# %% [markdown]
# ## What is URL Morphing?
#
# URL morphing is a smart system that:
# 1. Downloads content from URLs
# 2. Intelligently detects the file type using multiple strategies
# 3. Transforms the attachment so existing loaders can process it
#
# This enables seamless processing of any file type from URLs without maintaining hardcoded lists.
#
# ## Basic Morphing Pattern
#
# The standard pattern is: `url_to_response → morph_to_detected_type → specific_loader`
#
# %%
# Download and morph a PDF from URL
pdf_attachment = (attach("https://github.com/MaximeRivest/attachments/raw/main/src/attachments/data/sample.pdf") |
                 load.url_to_response |           # Step 1: Download content
                 modify.morph_to_detected_type |  # Step 2: Detect file type intelligently  
                 load.pdf_to_pdfplumber |         # Step 3: Load with appropriate loader
                 present.text)                    # Step 4: Extract content

# %% [markdown]
# Let's see what we got:
# %%
len(pdf_attachment.text)

# %% [markdown]
# Here's the extracted PDF content:
# %%
pdf_attachment.text[:200]

# %% [markdown]
# Perfect! The PDF was properly detected and loaded. Let's examine how the detection worked:
# %%
pdf_attachment.path

# %% [markdown]
# The original URL was transformed to a clean filename. Let's see the detection metadata:
# %%
{
    'detected_extension': pdf_attachment.metadata.get('detected_extension'),
    'detection_method': pdf_attachment.metadata.get('detection_method'),
    'content_type': pdf_attachment.metadata.get('response_content_type')
}

# %% [markdown]
# ## How Detection Works
#
# The morphing system uses three strategies to detect file types:
# 1. **File extension** from the URL path
# 2. **Content-Type header** from the HTTP response
# 3. **Magic number signatures** from the file content
#
# This triple-check approach ensures reliable detection even when URLs don't have clear extensions.
#
# ## Working with Different File Types
#
# Let's try morphing with different file formats:
#
# %%
# PowerPoint presentation
pptx_result = (attach("https://github.com/MaximeRivest/attachments/raw/main/src/attachments/data/sample_multipage.pptx") |
               load.url_to_response |
               modify.morph_to_detected_type |
               load.pptx_to_python_pptx |
               present.text)

# %% [markdown]
# PowerPoint content length:
# %%
len(pptx_result.text)

# %% [markdown]
# Detected file type:
# %%
pptx_result.path

# %%
# Markdown file
md_result = (attach("https://raw.githubusercontent.com/MaximeRivest/attachments/main/README.md") |
             load.url_to_response |
             modify.morph_to_detected_type |
             load.text_to_string |
             present.text)

# %% [markdown]
# Markdown content length:
# %%
len(md_result.text)

# %% [markdown]
# Detected file type:
# %%
md_result.path

# %% [markdown]
# ## Why Morphing is Essential
#
# Without morphing, URL processing fails because loaders use file extensions to determine if they should handle a file. URLs don't match these patterns.
#
# Let's see what happens without morphing:
# %%
# This will fail - PDF loader won't recognize the URL
failed_attempt = (attach("https://github.com/MaximeRivest/attachments/raw/main/src/attachments/data/sample.pdf") |
                 load.url_to_response |           # Downloads content
                 load.pdf_to_pdfplumber |         # But matcher fails - path is still a URL!
                 present.text)

# %% [markdown]
# Without morphing, the content isn't processed correctly:
# %%
len(failed_attempt.text)

# %% [markdown]
# The result is just the response object representation:
# %%
failed_attempt.text

# %% [markdown]
# ## Automatic Morphing in Pipelines
#
# The universal pipeline automatically includes morphing for URLs, so you often don't need to specify it manually:
# %%
from attachments import Attachments

# This automatically uses morphing
auto_result = Attachments("https://github.com/MaximeRivest/attachments/raw/main/src/attachments/data/sample.pdf")
auto_text = str(auto_result)

# %% [markdown]
# Automatic processing result length:
# %%
len(auto_text)

# %% [markdown]
# First part of the automatically processed content:
# %%
auto_text[:200]

# %% [markdown]
# ## Advanced: Understanding the Detection Process
#
# Let's trace through how morphing detects a PDF file:
# %%
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

# %% [markdown]
# ## Best Practices
#
# ### 1. Use the Standard Pattern
# For manual pipelines with URLs, always use: `url_to_response → morph_to_detected_type`
#
# ### 2. Let Enhanced Matchers Do Their Work
# The system automatically checks file extensions, Content-Type headers, and magic numbers. No need for manual detection.
#
# ### 3. Trust the Detection
# The morphing system is designed to be robust. It will fall back gracefully if detection is uncertain.
#
# ### 4. For Simple Cases, Use Automatic Processing
# `Attachments()` or the universal pipeline handle morphing automatically.
#
# ## Summary
#
# URL morphing enables seamless processing of any file type from URLs by:
# - Downloading content intelligently
# - Detecting file types using multiple strategies  
# - Transforming attachments so existing loaders can process them
# - Maintaining zero hardcoded file type lists
#
# This creates an extensible system where adding new file types automatically enables URL support!
#