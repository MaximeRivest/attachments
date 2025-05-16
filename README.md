> **Warning:**  
> **WIP:** The examples below are not yet implemented.

# Attachments

A Python library designed to seamlessly handle various file types and present them to large language models (LLMs) in a unified format combining images and text.

The ambition of `attachments` is to provide a reader and renderer for 80%+ of all file types that a user may wish to provide to an llm. So that the user simply provide a path (local or url) and the library will handle the rest.

## Installation

```bash
pip install attachments
```

## Usage

```python
from attachments import Attachments

print(f"""Hey ChatGPT,

        here are my attachments: 
            {Attachments('path/to/attachments.pptx',
             'path/to/attachments.pdf')}
             """)

# Output:
# <attachments>
#   <attachment id="pptx1" type="pptx">
#     ... rendered pptx content ...
#   </attachment>
#   <attachment id="pdf1" type="pdf">
#     ... rendered pdf content ...
#   </attachment>
# </attachments>
``` 

a list also works:

```python
attachments = Attachments(["path/to/attachments.pptx", "path/to/attachments.pdf"])
```

for specifying things like page numbers, etc. you can use index:

```python
attachments = Attachments(["path/to/attachments.pptx[:10, -3:]", "path/to/attachments.pdf[:-10, -10:]"])
```

String interpolation also works:

```python
f"See all my attachments: {attachments}"
```

this will render the attachments and interpolate the result into the string.


