# %% [md]
# # Complete Beginner Tutorial: Using the OpenAI Library in Python
#
# This tutorial is tailored for those new to interacting with Large Language Models (LLMs)
# programmatically, assuming no prior experience.
#
# Learning the OpenAI Python library is a worthwhile endeavor. While it might not always
# be my top recommendation for direct use, its foundational role in the ecosystem means
# that a vast number of other libraries depend on it. Furthermore, the library's design is
#  closely tied to the JSON format required by the OpenAI API. This JSON structure, for better
#  or worse (and I'd lean towards the latter), has become a de facto standard.
#%%
import logging
logging.getLogger("pypdf._reader").setLevel(logging.ERROR)

# %% [md]
# ## Without the attachments library
#
# First, ensure you have the `attachments` and `openai` libraries installed.
#
# ```bash
# uv pip install attachments openai python-dotenv
# ```
#
# Now, let's import the necessary modules.

# %% [md]
# Ensure you have an `.env` file with your `OPENAI_API_KEY` or set it as an environment variable
#%%
import os
from attachments import Attachments
import openai

# %% [md]
# We are loading attachments as this is a much easier way to pass files to openai.
# However, we will start doing it the vanilla way to show how it works. Some may
# even call it raw dogging it.
#
# We will first look at the object we must pass to the OpenAI API.
# In its simplest form, the object is a list of dictionaries.
# Each dictionary contains a `role` and a `content` key.
# The `content` key is a list of dictionaries.
# Each of those dictionaries contains a `type` key and the actual content.
#
# To pass an image, we use the `input_image` type.
# To pass text, we use the `input_text` type.
# So to ask an llm what is sees in an image, we would prepare the following:
#%%
image_data_url = "data:image/jpeg;base64,..."
openai_messages_content = [
    {
        "role": "user",
        "content": [
            {"type": "input_text", "text": "what is in this image?"},
            {
                "type": "input_image",
                "image_url": image_data_url
            }
        ]
    }
]
# %% [md]
# but the image must be encoded as a base64 string. this is a bit of a pain.
# we would need to do something like this:
#%%
import base64
from pathlib import Path

image_bytes = Path("/home/maxime/Projects/attachments/sample.jpg").read_bytes()
image_base64 = base64.b64encode(image_bytes).decode("utf-8")
image_data_url = f"data:image/jpeg;base64,{image_base64}"

#%% [md]
# Then we have all of the boilerplate to make the API call.
# For this we need to instantiate the OpenAI client. This will search for your API key
# in your environment variables. You can also pass it directly as a string, like this:
# `client = OpenAI(api_key="your_key_here")`
#```python
#client = openai.OpenAI()
#
#response = client.responses.create(
#    model="gpt-4.1-nano",
#    input=openai_messages_content
#)
#```
# %% [md]
# Putting it all together, we get the following:
#%%
import openai
import base64
from pathlib import Path

image_bytes = Path("/home/maxime/Pictures/20230803_130936.jpg").read_bytes()
image_base64 = base64.b64encode(image_bytes).decode("utf-8")
image_data_url = f"data:image/jpeg;base64,{image_base64}"

client = openai.OpenAI()

response = client.responses.create(
    model="gpt-4.1-nano",
    input=[
    {
        "role": "user",
        "content": [
            {"type": "input_text", "text": "what is in this image?"},
            {
                "type": "input_image",
                "image_url": image_data_url
            }
        ]
    }
]
)
response.__dict__

# %% [md]
# ## With the attachments library
#
# Here is the same example using the attachments library. 
#%%
import openai
from attachments import Attachments
client = openai.OpenAI()

response = client.responses.create(
    model="gpt-4.1-nano",
    input=[
    {
        "role": "user",
        "content": Attachments("/home/maxime/Pictures/20230803_130936.jpg").to_openai(
            prompt="what is in this picture?"
            )
    }
]
)
response.__dict__
# %% [md]
# It is already more concise and easier to manage but where attachments really shines is when
# you want to pass other file types, not just images.
# let's for instance try to pass this pdf:
#%%
pdf_url = "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"

import openai
from attachments import Attachments
client = openai.OpenAI()

response = client.responses.create(
    model="gpt-4.1-nano",
    input=[
    {
        "role": "user",
        "content": Attachments(pdf_url).to_openai(prompt="what is in this pdf and what is the color of the background?")
    }
]
)
response.__dict__
#%%[md]
# here is a quick look at what the Attachments looks like:
#%%
a = Attachments(pdf_url)
#%%

print(a.text)

#%%
from IPython.display import display, HTML
display(HTML(f'<img src="{a.images[0]}" style="max-width:900px;">'))


# %% [md]
# And it even works with multiple files.
#%%
a = Attachments("https://github.com/microsoft/markitdown/raw/refs/heads/main/packages/markitdown/tests/test_files/test.pdf",
                "https://github.com/microsoft/markitdown/raw/refs/heads/main/packages/markitdown/tests/test_files/test.pptx",
                "https://upload.wikimedia.org/wikipedia/commons/thumb/e/ea/BremenBotanikaZen.jpg/1280px-BremenBotanikaZen.jpg")
a
# %% [md]
# Now to send this to gpt-4.1 we can do the following:
#%%
response = client.responses.create(
    model="gpt-4.1-nano",
    input=[
    {
        "role": "user",
        "content": a.to_openai("what do you see in these three files?")
    }
]
)
response.output[0].content[0].text

#%% [md]
# let's focus on the powerpoint file.
#%%
response = client.responses.create(
    model="gpt-4.1-nano",
    input=[
    {
        "role": "user",
        "content": a[1].to_openai_content("what do you see in this pptx file?")
    }
]
)
response.output[0].content[0].text


# %% [md]
# Below we can see that we pass the attachments twice to gpt-4.1 once as a tiled (3x3) image and once as extracted text.
# this really helps the llm out. On once said it reduced the hallucinations from parsing only the image
# and on the other it provide the style and structure of the pdf, otherwise lacking in the text only version.
#%%
a[1].to_openai_content("what do you see in this pptx file?")
#%%
from IPython.display import display, HTML
display(HTML(f'<img src="{a[1].images[0]}" style="max-width:600px;">'))
