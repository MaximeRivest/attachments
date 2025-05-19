# Attachments
## Easiest way to give context to LLMs

Attachments has the ambition to be the general funnel for any files to be transformed into images+text for large language models context. For this to be true we, has a community, have to stop implementing this funnel (file -> images+text) each on our own. If you have a detector + parser + renderer contibute it! This will help you and us. Don't let your code alone in a dark corner of you computer.

## Very quickstart

```python
from attachments import Attachments

a = Attachment("/the/path/or/url/to/your/to/the/content/you/want/to/give/the/llm.xlsx", "another.pdf", "another.pptx"...)

prompt_ready_context = str(a)
images_ready_for_llm = a.images
```

That is really just it!

You can print it `print(a)`, you can interpolate it `f"the content is {a}"` you can string it `str(a)`. This will give you something very good to give the llm so that the AI can consider you content. 

Nowadays, most genAI models comes with the ability to see images too. So you also have all attachments in images forms by using `a.images`.
This is a list of base64 encoded images, this is the fundamental format the most llm provider accept. 

The simplest way to use and think about attachments is that if you want to put you best foot forward and up you chances that the llm grok your content you should pass all of the text in `a` to the prompt and all of the images in `a.images` in the image input. We aim for making those two as 'prompt engineered' as possible. *Attachments* is young but already very powerful and used in production. The api will not change. Maybe advanced feature and syntax will be added but the core will stay the same. Mostly we will support more file types and we will have better rendering for better performance and with less extreneous tokens.

## How to give attachments to openai llms?

```python
from openai import OpenAI
from attachments import Attachments

pdf_attachment = Attachments("https://github.com/microsoft/markitdown/raw/refs/heads/main/packages/markitdown/tests/test_files/test.pdf")

prompt = f"""
Analyze the following documents:
{pdf_attachment}
"""

content = [{"type": "input_image","image_url": image} for image in pdf_attachment.images] + \
          [{"type": "input_text", "text": prompt}]

response = OpenAI().responses.create(model="gpt-4.1-nano", input=[{"role": "user", "content": content}])
response.output_text
```





A Python library designed to seamlessly handle various file types (local or URLs), process them, and present them in formats suitable for Large Language Models (LLMs).

It is meant to be very minimal.

most user will not have to learn anything more then that: `Attachments("path/to/file.pdf")`

```bash
>  pip install attachments
```

```python
from attachments import Attachments

a = Attachments("https://github.com/microsoft/markitdown/raw/refs/heads/main/packages/markitdown/tests/test_files/test.pdf",
                "https://github.com/microsoft/markitdown/raw/refs/heads/main/packages/markitdown/tests/test_files/test.pptx",
                "https://upload.wikimedia.org/wikipedia/commons/thumb/e/ea/BremenBotanikaZen.jpg/1280px-BremenBotanikaZen.jpg")
print(a)# will print a string representation of the pdf, pptx and image that can be used in a prompt
```

```xml
<attachments>
  <pdf_attachment_1>
  page 1:
Hello PDF!
  </pdf_attachment_1>
  <pptx_attachment_2>
--- Slide 1 ---
Slide 1 Title This is the first slide. Content for page 1.

--- Slide 2 ---
Slide 2 Title This is the second slide. Content for page 2.

--- Slide 3 ---
Slide 3 Title This is the third slide. Content for page 3.
  </pptx_attachment_2>
</attachments>
```

The ambition of `attachments` is to provide a robust reader, processor, and renderer for a wide array of common file types, simplifying the process of providing complex, multi-modal context to LLMs. The power comes from doing a best effort media -> text + image prompt and thus most of the value of `attachments` is not visible in long tutorial and lots of things to learn but in rather in it's simplicity and ability to get out of your way and let you pass files/data/information to LLMs.

## Key Features

*   **Versatile File Handling**: Process a variety of file types including PDFs, PPTX, HTML, common image formats, and audio files.
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
    *   `.audios` property: Provides a list of audio file data, each with a filename, a `BytesIO` file object, and content type, suitable for audio-processing APIs (e.g., OpenAI Whisper).
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

**3. Audio Files for LLMs:**
The `.audios` property returns a list of dictionaries, each prepared for audio API submission (e.g., to OpenAI Whisper). Each dictionary contains:
*   `'filename'`: The original filename (e.g., `'speech.mp3'`).
*   `'file_object'`: An `io.BytesIO` object containing the raw audio data. Its `.name` attribute is set to the filename.
*   `'content_type'`: The detected MIME type of the audio (e.g., `'audio/mpeg'`).

```python
audio_files_for_api = a.audios
if audio_files_for_api:
    first_audio = audio_files_for_api[0]
    print(f"Audio Filename: {first_audio['filename']}")
    print(f"Audio Content-Type: {first_audio['content_type']}")
    # The first_audio['file_object'] can be directly passed to APIs like openai.Audio.transcribe
    # For example: transcript = openai.Audio.transcribe("whisper-1", first_audio['file_object'])
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
*   **Audio**: FLAC (`.flac`), M4A (`.m4a`), MP3 (`.mp3`), MP4 audio (`.mp4`), MPEG audio (`.mpeg`, `.mpga`), Ogg audio (`.oga`, `.ogg`), WAV (`.wav`), WebM audio (`.webm`)
