# Attachments
## Easiest way to give context to LLMs

Attachments has the ambition to be the general funnel for any files to be transformed into images+text for large language models context. For this to be true we, has a community, have to stop implementing this funnel (file -> images+text) each on our own. If you have a detector + parser + renderer contibute it! This will help you and us. Don't let your code alone in a dark corner of you computer.

## Very quickstart

```bash
>  pip install attachments
```

Most users will not have to learn anything more then that: `Attachments("path/to/file.pdf")`

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

## How to give attachments to anthropic llms?

```python
import anthropic
from attachments import Attachments

pptx_file = Attachments(
    "https://github.com/microsoft/markitdown/raw/refs/heads/main/packages/markitdown/tests/test_files/test.pptx")

prompt = f"""
Analyze the following documents:
{pptx_file}
"""

content = [
    {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": image.split(";")[0].split(":")[1], # this is ugly but it works
            "data": image.split(",")[1] # this is ugly but it works
        }
    }
    for image in pptx_file.images
] + [{"type": "text", "text": prompt}]

message = anthropic.Anthropic().messages.create(
    max_tokens=8192,
    model="claude-3-5-haiku-20241022",
    messages=[{"role": "user", "content": content}])
print(message.content)
```

## How to give a word document (with tables and images) to langchain?

I am not a fan of the object that langchain and anthropic make you create, but hey!, I don't make the rules...

```python
from langchain.chat_models import init_chat_model
from attachments import Attachments

docx_file = Attachments("https://github.com/microsoft/markitdown/raw/refs/heads/main/packages/markitdown/tests/test_files/test.docx")

llm = init_chat_model("anthropic:claude-3-5-sonnet-latest")

# Creation of a list of object as expected by langchain/anthropic
content = [{"type": "text", "text": f"Analyze the following documents: {docx_file}"}]

for image in docx_file.images
    media_type_i = image.split(";")[0].split(":")[1]
    media_data_i = image.split(",")[1]
    content.append({
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type_i, 
            "data": media_data_i 
        }
    })


message = {
    "role": "user",
    "content": content,
}

#Finally call the llm
response = llm.invoke([message])
print(response.text())
```

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
*   **Documents**: PDF (`.pdf`), PowerPoint (`.pptx`), Excel (`.xlsx`), Word (`.docx`), much more to come!
*   **Images**: JPEG (`.jpg`, `.jpeg`), PNG (`.png`), GIF (`.gif`), BMP (`.bmp`), WEBP (`.webp`), TIFF (`.tiff`), HEIC (`.heic`), HEIF (`.heif`)