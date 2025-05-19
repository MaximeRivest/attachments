# %% [md]
# # Using `attachments` with the OpenAI API
#
# This tutorial demonstrates how to use the `attachments` library to process local or remote files
# and prepare their content for use with the OpenAI API, particularly for multimodal models
# like GPT-4 with Vision or for text-based analysis.

# %% [md]
# ## 1. Setup and Imports
#
# First, ensure you have the `attachments` and `openai` libraries installed.
#
# ```bash
# uv pip install attachments openai python-dotenv
# ```
#
# Now, let's import the necessary modules.

# %%
# Ensure you have an .env file with your OPENAI_API_KEY or set it as an environment variable
import os
from attachments import Attachments
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv() # Load environment variables from .env file

# %% [md]
# ## 2. Initialize Attachments
#
# We'll create an `Attachments` object. You can use URLs or local file paths.
# For this example, let's use a publicly available PDF and an image.

# %%
# Example using online resources
pdf_url = "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"
image_url = "https://upload.wikimedia.org/wikipedia/commons/thumb/e/ea/BremenBotanikaZen.jpg/1280px-BremenBotanikaZen.jpg"

# You can also use local paths, e.g.:
# pdf_local_path = "path/to/your/document.pdf"
# image_local_path = "path/to/your/image.jpg"
# attachments_obj = Attachments(pdf_local_path, image_local_path, verbose=True)

attachments_obj = Attachments(pdf_url, image_url, verbose=True) # Renamed to avoid conflict

# %% [md]
# ## 3. Inspecting Attachments
#
# The `Attachments` object processes the files. Its string representation (`str(attachments_obj)`)
# provides an XML-like format suitable for LLM prompts. For vision models,
# the `.images` property provides base64 encoded image data URLs.

# %%
# Get the string representation for text-based analysis or context
llm_context_string = str(attachments_obj)
print("--- LLM Context String (sample) ---")
# Print a sample, as it can be very long
print(llm_context_string[:500] + "..." if len(llm_context_string) > 500 else llm_context_string)

# %%
# Access image data for vision models
# .images will contain a list of data URLs (e.g., "data:image/jpeg;base64,...")
if attachments_obj.images:
    print(f"\n--- Found {len(attachments_obj.images)} image(s) ---")
    # print("First image data URL (sample):", attachments_obj.images[0][:100] + "...") # Print a sample of the data URL
else:
    print("\n--- No images found or processed ---")

# %% [md]
# ## 4. Preparing Content for OpenAI API
#
# Let's construct a message for the OpenAI API. We'll demonstrate a multimodal example
# using GPT-4o (or another vision-capable model).

# %%
client = OpenAI() # Assumes OPENAI_API_KEY is set in your environment via .env or system variable

# %% [md]
# ### 4.1. Multimodal Prompt (Text and Images)
#
# We'll combine the textual context from `str(attachments_obj)` with any images found.

# %%
# Prepare the content list for the OpenAI API
openai_messages_content = []

# Add text part: a general instruction and the context from attachments_obj
prompt_text = f'''
Analyze the following documents and images. Provide a brief summary of the PDF content
and describe the image.

Document context:
{llm_context_string}
'''
openai_messages_content.append({"type": "text", "text": prompt_text})

# Add image parts
for image_data_url in attachments_obj.images:
    # OpenAI API expects image_url with "data:image/jpeg;base64,..." format for base64 encoded images
    openai_messages_content.append({
        "type": "image_url",
        "image_url": {
            "url": image_data_url,
            "detail": "low" # Use "high" for more detail, "low" for faster processing
        }
    })

# %% [md]
# ### 4.2. Making the API Call (Example)
#
# Now, let's construct the full message and show how you would make the API call.
# **Note:** Running this cell will make an API call to OpenAI if your API key is configured.

# %%
if not os.getenv("OPENAI_API_KEY"):
    print("OPENAI_API_KEY not found in environment variables. Skipping API call.")
    print("Please create a .env file with OPENAI_API_KEY='your_key_here' or set it as an environment variable.")
else:
    print("Attempting to call OpenAI API (multimodal)...")
    try:
        response = client.chat.completions.create(
            model="gpt-4o", # Or your preferred vision-capable model like "gpt-4-turbo"
            messages=[
                {
                    "role": "user",
                    "content": openai_messages_content
                }
            ],
            max_tokens=500
        )
        print("\n--- OpenAI API Response (Multimodal) ---")
        print(response.choices[0].message.content)
    except Exception as e:
        print(f"Error calling OpenAI API (multimodal): {e}")

# %% [md]
# ## 5. Text-Only Analysis
#
# If you are using a text-only model (e.g., `gpt-3.5-turbo`), you would only pass the `llm_context_string`.

# %%
# Example for a text-only model
text_only_prompt = f'''
Based on the following document content, please answer specific questions or perform tasks.
For example, what is the main subject of the PDF?

Document context:
{llm_context_string}
'''

if not os.getenv("OPENAI_API_KEY"):
    print("OPENAI_API_KEY not found. Skipping text-only API call.")
else:
    print("\nAttempting text-only OpenAI API call...")
    try:
        response_text_only = client.chat.completions.create(
            model="gpt-3.5-turbo", # Or your preferred text model
            messages=[
                {
                    "role": "user",
                    "content": text_only_prompt
                }
            ],
            max_tokens=300
        )
        print("\n--- OpenAI Text-Only API Response ---")
        print(response_text_only.choices[0].message.content)
    except Exception as e:
        print(f"Error calling OpenAI API (text-only): {e}")

# %% [md]
# ## Conclusion
#
# This tutorial showed how to use the `attachments` library to load files/URLs,
# extract their content into formats suitable for LLMs, and construct prompts
# for the OpenAI API for both multimodal and text-only analysis.
#
# Remember to handle your API keys securely (e.g., using a `.env` file and `python-dotenv`)
# and manage costs associated with API calls. 