# Attachments
## Quickstart
A Python library designed to seamlessly handle various file types (local or URLs), process them, and present them in formats suitable for Large Language Models (LLMs).

It is meant to be very minimal.

most user will not have to learn anything more then that: `Attachments("path/to/file.pdf")`

```bash
>  pip install attachments
```

```python
from attachments import Attachments

# This example assumes you have 'sample.pdf' and 'sample.pptx'
# in an 'examples' directory relative to where you run this script.
# You can create this directory and place sample files from the project's
# tests/test_data if you have cloned the repository.

a = Attachments("examples/sample.pdf",
                "examples/sample.pptx",
                "https://upload.wikimedia.org/wikipedia/commons/thumb/e/ea/BremenBotanikaZen.jpg/1280px-BremenBotanikaZen.jpg")
print(a)# will print a string representation of the pdf, pptx and image that can be used in a prompt
```

```xml
<attachments>
  <attachment id="pdf1" type="pdf">
    <meta name="num_pages" value="1" />
    <content>
Hello PDF!
    </content>
  </attachment>
  <attachment id="pptx2" type="pptx">
    <meta name="num_slides" value="3" />
    <content>
--- Slide 1 ---
Slide 1 Title This is the first slide. Content for page 1.

--- Slide 2 ---
Slide 2 Title This is the second slide. Content for page 2.

--- Slide 3 ---
Slide 3 Title This is the third slide. Content for page 3.
    </content>
  </attachment>
  <attachment id="jpeg3" type="jpeg">
    <meta name="dimensions" value="1280x960" />
    <meta name="original_format" value="JPEG" />
    <meta name="original_mode" value="RGB" />
    <meta name="output_format_target" value="jpeg" />
    <meta name="output_quality_target" value="90" />
    <meta name="applied_operations" value="{}" />
    <content>
[Image: tmpXXXXXXX.jpg (original: JPEG RGB) -&gt; processed to 1280x960 for output as jpeg]
    </content>
  </attachment>
</attachments>
```

(Note: The exact filename like `tmpXXXXXXX.jpg` in the image content will vary as it's based on a temporary file created during processing.)

The ambition of `attachments` is to provide a robust reader, processor, and renderer for a wide array of common file types, simplifying the process of providing complex, multi-modal context to LLMs. The power comes from doing a best effort media -> text + image prompt and thus most of the value of `attachments` is not visible in long tutorial and lots of things to learn but in rather in it's simplicity and ability to get out of your way and let you pass files/data/information to LLMs.

## Key Features

*   **Versatile File Handling**: Process a variety of file types including PDFs, PPTX, HTML, and common image formats.
*   **Local and URL Support**: Accepts local file paths and URLs as input.
*   **Content Extraction**: Extracts text from documents and rich metadata from all supported types.
*   **Advanced Image Processing**:
    *   On-the-fly transformations via path string commands: resizing (e.g., `image.jpg[resize:500x300]`, `image.png[resize:200xauto]`), rotation (`image.heic[rotate:90]`), and format conversion (`image.webp[format:png]`).
    *   Configurable output quality for JPEG/WEBP.
*   **Rich Jupyter/IPython Display**: Automatic rich Markdown rendering when an `Attachments` object is the last item in a cell, featuring:
    *   A summary of all attachments with detailed metadata.
    *   A multi-column image gallery for visual previews of image attachments.
*   **Powerful Indexing**:
    *   Select specific pages from PDFs or slides from PPTX files (e.g., `"file.pdf[1,3-5,N]"`, `"presentation.pptx[:3,-1:]"`).
    *   `Attachments` objects themselves are indexable and sliceable (e.g., `subset = attachments[0:2]`).
*   **LLM-Ready Outputs**:
    *   Default XML rendering (`str(attachments)`) provides a structured representation suitable for LLM prompts, including detailed metadata and textual content.
    *   `.images` property: Conveniently access a list of base64-encoded image strings (e.g., `data:image/jpeg;base64,...`), ready for multi-modal LLM APIs.
*   **Broad Image Format Support**: Handles JPEG, PNG, GIF, BMP, WEBP, TIFF, and modern formats like HEIC/HEIF (requires `libheif`).

## Installation

```bash
pip install attachments
```
For full HEIC/HEIF image support, you may need to install `libheif` on your system:
*   macOS: `brew install libheif`
*   Debian/Ubuntu: `sudo apt-get install libheif-examples`

## Usage

### Basic Initialization
Create an `Attachments` object by passing one or more local file paths or URLs. Image processing commands can be appended to image paths.

```python
from attachments import Attachments

# Initialize with various local files, URLs, and image processing commands
a = Attachments(
    "docs/report.pdf",
    "images/diagram.png[resize:400xauto]",
    "https://www.example.com/article.html",
    "photos/vacation.heic[rotate:90,format:jpeg,quality:80]"
)

# The library will download URLs, process files, and extract content.
```

### Default XML Output for LLMs
Simply converting an `Attachments` object to a string (or using it in an f-string) renders it as XML, which is useful for many LLM prompts.

```python
prompt = f"""
Analyze the following documents:
{a}
"""
print(prompt)

# Output (simplified):
# Analyze the following documents:
# <attachments>
#   <attachment id="pdf1" type="pdf" original_path_str="docs/report.pdf" file_path="docs/report.pdf">
#     <meta name="num_pages" value="10" />
#     <meta name="indices_processed" value="[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]" />
#     <content>
#     ... extracted text from PDF ...
#     </content>
#   </attachment>
#   <attachment id="png2" type="png" original_path_str="images/diagram.png[resize:400xauto]" file_path="images/diagram.png">
#     <meta name="dimensions" value="400x..." />
#     <meta name="original_format" value="PNG" />
#     <meta name="applied_operations" value="{'resize': (400, None)}" />
#     <meta name="output_format_target" value="jpeg" />
#     <content>
#     [Image: diagram.png (original: PNG ...) -> processed to 400x... for output as jpeg]
#     </content>
#   </attachment>
#   ... other attachments ...
# </attachments>
```

### Rich Display in Jupyter/IPython
If an `Attachments` object is the last expression in a Jupyter Notebook or IPython console cell, it will automatically render a rich Markdown summary:

```python
# In a Jupyter cell:
from attachments import Attachments
a = Attachments("report.pdf", "image.png[resize:150x150]", "chart.jpg")
a # This will display the rich summary and image gallery
```
This output includes a main summary of all attachments (ID, type, source, extracted metadata/text snippets) and a separate "Image Previews" section with a multi-column gallery of image thumbnails.

### Accessing Processed Data and Images

**1. Parsed Data:**
Each processed attachment's data is stored in the `attachments_data` list:
```python
for item in a.attachments_data:
    print(f"ID: {item['id']}, Type: {item['type']}")
    if 'text' in item:
        print(f"  Text snippet: {item['text'][:100]}...")
    if item['type'] in ['jpeg', 'png', 'heic']: # Image types
        print(f"  Dimensions: {item['width']}x{item['height']}")
        print(f"  Original Format: {item['original_format']}")
```

**2. Base64 Images for LLMs:**
The `.images` property provides a list of base64-encoded strings for all processed images, ready for use with multi-modal LLM APIs.
```python
base64_image_list = a.images
if base64_image_list:
    print(f"First image data URI: {base64_image_list[0][:50]}...") 
    # Output: First image data URI: data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD...
```

### Indexing Attachments
You can get a new `Attachments` object containing a subset of the original attachments using integer or slice indexing:
```python
first_attachment = a[0]
first_two_attachments = a[0:2]

print(f"Selected attachment: {first_attachment}")
```

### Page/Slide Selection
Specify pages for PDFs or slides for PPTX files using bracket notation in the path string:
```python
# Process only page 1 and pages 3 through 5 of a PDF
specific_pages_pdf = Attachments("long_document.pdf[1,3-5]")

# Process the first three slides and the last slide of a presentation
specific_slides_pptx = Attachments("presentation.pptx[:3,N]") 
# 'N' refers to the last page/slide. Negative indexing like [-1:] also works.
```

## Supported File Types
*   **Documents**: PDF (`.pdf`), PowerPoint (`.pptx`)
*   **Web**: HTML (`.html`, URLs)
*   **Images**: JPEG (`.jpg`, `.jpeg`), PNG (`.png`), GIF (`.gif`), BMP (`.bmp`), WEBP (`.webp`), TIFF (`.tiff`), HEIC (`.heic`), HEIF (`.heif`)

## Running Tests
To run the test suite:
1. Clone the repository.
2. Ensure you have `pytest` installed (`pip install pytest`).
3. Navigate to the root directory of the project and run:
   ```bash
   pytest
   ```

## License
(To be added - e.g., MIT License)


