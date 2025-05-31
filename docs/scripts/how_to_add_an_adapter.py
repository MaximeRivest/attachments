# %% [markdown]
# # How to add an adapter
# 
# ## What is an adapter?
# Adapters are functions organized in the `attachments.adapt` namespace.
# 
# The `@adapter` decorator is used to mark a function as an adapter and register it in the `attachments.adapt` namespace.
# This will also make it automatically available in `Attachments("path/to/file").name_of_the_adapter()`.
# You can pass additional parameters to the adapter function, but the first parameter is required to be the `input_obj`.
#
# ### Example of an adapter
# If we want to add an adapter called `mysupersdk` that allows us to use Attachments with mysupersdk, we can do the following:
# 
# ```python
# @adapter
# def mysupersdk(input_obj: Union[Attachment, AttachmentCollection], prompt: str = "") -> List[Dict[str, Any]]:
#     ...
# ```
#
# Notice that the output in this case can be anything (that is the point of adapters).
# In the case of `mysupersdk`, the output would be a list of dictionaries with string keys and any values.
#
# Throughout this tutorial we will use the `agno` library as an example. This means we will develop
# an adapter that allows us to use Attachments with agno. For agno, we may want to name the adapter `agno`.
#
# Like this:
# 
# ```python
# @adapter
# def agno(input_obj: Union[Attachment, AttachmentCollection], prompt: str = ""):
#     ...
# ```
# We are not quite sure yet what the output will be, but we will find out later.
# 
# ## How agno usually works
# 
# This is from agno's documentation: https://docs.agno.com/agents/multimodal. 
# 
# In agno, you create an Agent object, and then when calling the agent you can
# pass it an image using the Image object defined in the agno.media module.
# For audio, you can use the Audio object defined in the agno.media module, and for 
# video, you can use the Video object defined in the agno.media module. Video is supported
# by the Gemini models, and audio can be given to a few models including Gemini and OpenAI's
# gpt-4o-audio-preview.
#
# To keep things simple, we will only focus on images in this tutorial.
#
# ### Example of how to use agno
#
# In this example, we have a simple agent that would look at the provided image and
# search online for the latest news about it.
#%%
from agno.agent import Agent as agnoAgent
from agno.media import Image as agnoImage
from agno.models.openai import OpenAIChat
from agno.tools.duckduckgo import DuckDuckGoTools

agent = agnoAgent(
    model=OpenAIChat(id="gpt-4.1-nano"),
    tools=[DuckDuckGoTools()],
    markdown=True,
)

response = agent.run(
    "Tell me about this image and give me the latest news about it.",
    images=[
        agnoImage(
            url="https://upload.wikimedia.org/wikipedia/commons/0/0c/GoldenGateBridge-001.jpg"
        )
    ],
    stream=False  # No streaming
)
response.content

# %% [markdown]
# ## Our goal
#
# The goal is to create an adapter that allows us to use Attachments with agno.
# We would like it to work like this:
# 
# ```python
# response = agent.run(
#     **Attachments("https://upload.wikimedia.org/wikipedia/commons/0/0c/GoldenGateBridge-001.jpg").
#                       agno("Tell me about this image and give me the latest news about it."),
#     stream=False  # No streaming
# )
# response.content
# ```
#
# The main benefit of this would be that we would benefit from Attachments' capabilities to load
# a wide variety of files into images and text for us. Using this, we will be able to provide
# PDFs, PPTX, DOCX, SVG (as images), webpages (rendered and text), etc. to agno.
#
# %% [markdown]
# ## Exploring agno's Image Object for Attachment Adapter Development
# 
# Now that we understand how agno works, let's explore the Image object 
# to understand how to build our attachment adapter.
#
# ### Examining the Image Object Structure
# Let's create an Image object and examine its structure:
# %%
img = agnoImage(url="https://upload.wikimedia.org/wikipedia/commons/0/0c/GoldenGateBridge-001.jpg")
type(img)

# %% [markdown]
# Let's check what attributes the Image object has:
# %%
dir(img)

# %% [markdown]
# Now let's examine the Image object's fields to understand its structure:
# %%
img.model_fields.keys()

# %% [markdown]
# Perfect! We can see the Image object has fields like 'url', 'filepath', 'content', 'format', 'detail', and 'id'.
# Let's explore what these fields contain:
# %%
print("URL:", img.url)
print("Filepath:", img.filepath)
print("Content:", img.content)
print("Format:", img.format)
print("Detail:", img.detail)
print("ID:", img.id)

# %% [markdown]
# Great! So agno's Image object can be created with:
# - `url`: A URL pointing to an image
# - `filepath`: A local file path
# - `content`: Raw image bytes
# - `format`: Image format (png, jpeg, etc.)
# - `detail`: Level of detail for processing
# - `id`: Optional identifier
#
# Let's experiment with creating Image objects in different ways:

# %% [markdown]
# ## Experimenting with agno Image Creation
# 
# Let's try creating agno Images with different input methods to understand what works:

# %%
from agno.media import Image as AgnoImage
import base64

# Method 1: Create with URL
print("=== Method 1: URL ===")
img_url = AgnoImage(url="https://upload.wikimedia.org/wikipedia/commons/0/0c/GoldenGateBridge-001.jpg")
print("URL Image:", img_url)
print("Has URL:", bool(img_url.url))

# %% [markdown]
# %%
# Method 2: Create with raw bytes content
print("\n=== Method 2: Raw Bytes ===")
# Let's create a tiny 1x1 pixel PNG for testing
sample_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
content_bytes = base64.b64decode(sample_base64)
img_content = AgnoImage(content=content_bytes)
print("Content Image:", img_content)
print("Has content:", bool(img_content.content))

# %% [markdown]
# %%
# Method 3: What about data URLs? (base64 encoded images with data: prefix)
print("\n=== Method 3: Data URL ===")
data_url = f"data:image/png;base64,{sample_base64}"
img_data_url = AgnoImage(url=data_url)
print("Data URL Image:", img_data_url)
print("URL field contains:", img_data_url.url[:50] + "..." if len(img_data_url.url) > 50 else img_data_url.url)

# %% [markdown]
# Excellent! Now we understand that agno Images can handle:
# 1. **Regular URLs** - Direct links to images
# 2. **Raw bytes** - Binary image data
# 3. **Data URLs** - Base64-encoded images with data: prefix
#
# This is important because Attachments stores images as base64 strings, which we can convert to any of these formats.

# %% [markdown]
# ## Understanding Attachments Image Format
# 
# Now let's look at how Attachments stores images and see what we need to convert:

# %%
from attachments import Attachments

# %% [markdown]
# Create an attachment with an image:
#%%
sample_attachments = Attachments("https://upload.wikimedia.org/wikipedia/commons/0/0c/GoldenGateBridge-001.jpg")
# %% [markdown]
# Get the underlying Attachment object (this is what adapters work with):
# %%
sample_attachment = sample_attachments.attachments[0]  # Get the first (and only) attachment
sample_attachment

# %% [markdown]
# %%
# Let's examine what the attachment contains
print("Text content length:", len(sample_attachment.text))
# %% 
print("Number of images:", len(sample_attachment.images))
#%%
print("Text preview:", sample_attachment.text[:200] + "..." if len(sample_attachment.text) > 200 else sample_attachment.text)
# %%
from IPython.display import HTML
HTML(f"<img src='{sample_attachment.images[0]}'>")

# %% [markdown]
# %%
# Now let's look at how the image is stored
if sample_attachment.images:
    img_data = sample_attachment.images[0]
    print("Image data type:", type(img_data))
    print("Image data length:", len(img_data))
    print("Starts with 'data:image/':", img_data.startswith('data:image/'))
    print("First 50 characters:", img_data[:50])

# %% [markdown]
# Perfect! Now we can see that:
# - Attachments stores images as **data URL strings** (starting with 'data:image/')
# - These are base64-encoded images with proper MIME type prefixes
# - This format is **directly compatible** with agno's Image URL field!
#
# **Important Note**: This tutorial works with the underlying `Attachment` objects (lowercase 'a'), 
# not the high-level `Attachments` class. Adapters receive `Attachment` objects as input.

# %% [markdown]
# ## Testing the Conversion
# 
# Let's test if we can directly use Attachments image data with agno:

# %%
# Take the image data from Attachments
img_data = sample_attachment.images[0]

# Create an agno Image with it
agno_img = AgnoImage(url=img_data)
print("Agno Image created successfully:", agno_img)
print("Image URL field (first 100 chars):", agno_img.url[:100] + "...")

# %% [markdown]
# 🎉 **Success!** The conversion works perfectly. Attachments' data URL format is directly compatible with agno's Image objects.
#
# ## Multiple attachments
#
# It is very easy to move from a single attachment to a collection of attachments.
# The object instantiated by Attachments will always have `.images` and `.text` attributes.
# In the case of multiple attachments, these will be pre-concatenated.
#
# So we can use the same API for both single and multiple attachments. 
#
# Here is a quick example of that:
# %%
att = Attachments("https://upload.wikimedia.org/wikipedia/commons/0/0c/GoldenGateBridge-001.jpg",
                  "https://upload.wikimedia.org/wikipedia/commons/2/2c/Llama_willu.jpg")
att
# %%
len(att.images)
# %%
print(att.text)
# %%
from IPython.display import HTML
HTML(f"<img src='{att.images[0]}' height='200'><img src='{att.images[1]}' height='200'>")
# %% [markdown]
# And so we can easily create a list of Agno Images:
# %%
[AgnoImage(url=img) for img in att.images]
# %% [markdown]
# Next, we need to understand what agno's `agent.run()` method expects. We will study that in the next section.
#
# ## Understanding agno's Agent.run() Method
# 
# Let's examine how agno agents expect to receive images and text. For this,
# we will look at the `agent.run` signature and understand what it expects.
#
# %%
from agno.agent import Agent as AgnoAgent
from agno.models.openai import OpenAIChat

# Create a simple agent to examine its interface
agent = AgnoAgent(
    model=OpenAIChat(id="gpt-4o-mini"),
    markdown=True,
)

# Let's see what parameters agent.run accepts
import inspect
sig = inspect.signature(agent.run)
print("agent.run() parameters:")
for param_name, param in sig.parameters.items():
    print(f"  {param_name}: {param.annotation if param.annotation != inspect.Parameter.empty else 'Any'}")

# %% [markdown]
# From the agno documentation and our exploration, `agent.run()` accepts:
# - **message** (str): The text prompt/question
# - **images** (List[Image]): List of agno Image objects  
# - **audio** (List[Audio]): List of agno Audio objects
# - **stream** (bool): Whether to stream the response
# - And other parameters...
#
# We will test this:
# %%
agent = AgnoAgent(
    model=OpenAIChat(id="gpt-4.1-nano"),
    markdown=True,
)
att = Attachments("https://upload.wikimedia.org/wikipedia/commons/0/0c/GoldenGateBridge-001.jpg",
                  "https://upload.wikimedia.org/wikipedia/commons/2/2c/Llama_willu.jpg")
res = agent.run(
    message="What do you see in this image?",
    images=[AgnoImage(url=img) for img in att.images],
    stream=False
)
res.content
# %% [markdown]
# Excellent! This confirms that agno expects a list of images.
#
# What if we also want the text part of the prompt, which is automatically added by Attachments?
#
# A basic way would be to simply add the text to the prompt, like this:
# %%
res = agent.run(
    message=f"Name the 2 things in the 2 images and tell me about the image metadata: {att.text}",
    images=[AgnoImage(url=img) for img in att.images],
    stream=False
)
res.content

# %% [markdown]
# This works, but it's a bit tedious to have to always connect the attachments both to the prompt and
# to the images.
#
# By creating a dictionary with the keys 'message' and 'images', we can pass it to the `agent.run()`
# method using the `**` operator.
# 
# Like this:
#
# %%
prompt = f"Name the 2 things in the 2 images and tell me about the image metadata:"
images = [AgnoImage(url=img) for img in att.images]

params = {
    "message": f"{prompt} {att.text}",
    "images": images,
}
res = res = agent.run(**params)
res.content

# %% [markdown]
# We could easily turn that into a function:
# %%
def convert_attachments_to_agno(attachment, prompt=""):
    """Convert Attachments to agno Image objects."""
    images = [AgnoImage(url=img) for img in attachment.images]
    return {
        "message": f"{prompt} {attachment.text}",
        "images": images,
    }

params = convert_attachments_to_agno(att, "What do you see in this image?")
res = agent.run(**params)
res.content
# %% [markdown]
# Great! Now all we have to do is mark it as an adapter:
# %%
from attachments.adapt import adapter
from typing import Union, Dict, Any
@adapter
def custom_agno(input_obj: Union[Attachment, AttachmentCollection], prompt: str = "") -> Dict[str, Any]:
    return convert_attachments_to_agno(input_obj, prompt)

att = Attachments("https://upload.wikimedia.org/wikipedia/commons/0/0c/GoldenGateBridge-001.jpg",
                  "https://upload.wikimedia.org/wikipedia/commons/2/2c/Llama_willu.jpg")

res = agent.run(**att.custom_agno("What do you see in this image?"))
res.content

# %% [markdown]
# Success! We are now ready to pass any path and any file type to agno using Attachments.
#
# Let's do a quick test with a PDF file:
# %%
att = Attachments("https://upload.wikimedia.org/wikipedia/commons/f/f0/Strange_stories_%28microform%29_%28IA_cihm_05072%29.pdf[1-4]")
res = agent.run(**att.custom_agno("Summarize this document"))
res.content

# %% [markdown]
# And that's exactly it!
#%%
from IPython.display import HTML
HTML(f"<img src='{att.images[0]}'>")
# %% [markdown]
# ## Conclusion
#
# We have now created an adapter that allows us to use Attachments with agno.
#
# This is a simple example, but it shows the power of adapters.
#
# ## ps
# Agno is already supported as an adapter, so you can use Attachments("path/to/file").agno()
