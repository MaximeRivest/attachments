# %% [md]
# Demonstrating the Attachments Library Architecture

# This script walks through the internal architectural stages of the `attachments` library 
# to provide a clearer understanding of how it processes files. We'll show how an input path
# goes through Input Handling, Detection, Parsing, (Contact Sheet Generation), and finally 
# to Rendering/Output Preparation.

# %% [md]
# ## 0. Setup

# First, let's import necessary modules and set up some dummy files for our demonstration.

# %% 
import os
import tempfile
import shutil # For cleaning up the temp directory
from attachments import Attachments # Assuming it's installed and importable
from attachments.detectors import Detector # To demonstrate detector separately
from attachments.parsers import ParserRegistry, TextParser # To show registry and fallback parser

# Create a temporary directory for our sample files
temp_dir_path = tempfile.mkdtemp()
print(f"Temporary directory created: {temp_dir_path}")

#%%
# Sample file 1: A simple text file
text_content = "This is a simple text file for demonstration."
text_file_path = os.path.join(temp_dir_path, "sample.txt")
with open(text_file_path, "w", encoding="utf-8") as f:
    f.write(text_content)
print(f"Created: {text_file_path}")

#%%
# Sample file 2: A file with an unknown extension to test fallback
unknown_ext_content = "This content is in a file with an unknown extension."
unknown_file_path = os.path.join(temp_dir_path, "sample.unknownext")
with open(unknown_file_path, "w", encoding="utf-8") as f:
    f.write(unknown_ext_content)
print(f"Created: {unknown_file_path}")

#%%
# Sample file 3: A local image path (replace with a real small image path if possible for full demo)
# For CI/portability, we'll create a tiny dummy PNG here. 
# In a real scenario, you'd use an actual image path like "path/to/your/image.png"
from PIL import Image
dummy_image_path = os.path.join(temp_dir_path, "dummy_image.png")
try:
    img = Image.new('RGB', (60, 30), color = 'red')
    img.save(dummy_image_path, 'PNG')
    print(f"Created dummy image: {dummy_image_path}")
except Exception as e:
    print(f"Could not create dummy image (Pillow/PIL needed): {e}")
    dummy_image_path = None # Fallback if Pillow is not available
#%%
# Sample URL (publicly accessible small image or document)
# Using a very small, reliable PNG for demonstration
sample_url = "https://www.google.com/images/branding/googlelogo/1x/googlelogo_color_42x16dp.png"


# %% [md]
# ## 1. Input Handling & Preprocessing

# This initial stage is crucial. The library needs a concrete local file to operate on and must parse any operational directives from the input strings.

# *   **URL Downloading**: If a path is a URL, it's downloaded to a temporary local file.
# *   **Path String Parsing**: Directives (e.g., `[resize:100x100]`) are separated from the main file path.

# Let's initialize `Attachments` with a mix of our inputs:
# - The sample URL.
# - The local dummy image with an operation string.
# - The simple text file.
# - The file with an unknown extension.

# %% 
paths_for_attachments = []
paths_for_attachments.append(sample_url) # The URL
if dummy_image_path:
    paths_for_attachments.append(f"{dummy_image_path}[rotate:180,resize:300x300]") # Local image with ops
paths_for_attachments.append(text_file_path) # Simple text file
paths_for_attachments.append(unknown_file_path) # Unknown extension file

for path in paths_for_attachments:
    print(f"Input path: {path}")
#%% [md]
# Initialize Attachments - this will trigger the whole pipeline internally.
# Using verbose=True to see potential warnings or processing steps if any are printed by the library
#%%
atts_instance = Attachments(*paths_for_attachments, verbose=True) 
#%% [md]
# The Attachments object stores the original paths it was given:
#%%
atts_instance.original_paths_with_indices

#%% [md]
# Let's manually demonstrate what _parse_path_string does for an input with operations:
#%%
atts_instance._parse_path_string(f"{dummy_image_path}[format:jpeg,quality:70]")


#%% [md]
# For the URL, a download to a temporary file happens internally within _process_paths.
# We can't easily show the temp path here without modifying the library or deep inspection,
# but we can see its original URL was recorded in the final attachment data.
# %% [md]
# ## 2. Detection
# After preprocessing, the `Detector` attempts to identify the file type. This is crucial for selecting the correct parser.
# We will inspect the `type` and `original_detected_type` fields in the `attachments_data`.

# %% 
print("\n--- Inspecting Detected Types from attachments_data ---")
if not atts_instance.attachments_data:
    print("No attachments were processed successfully, skipping Detection demonstration details.")
else:
    for item in atts_instance.attachments_data:
        item_id = item.get('id', 'N/A')
        original_path = item.get('original_path_str', 'N/A')
        final_type = item.get('type', 'N/A')
        original_detection = item.get('original_detected_type', 'Not specifically recorded or same as final type')
        
        print(f"\nAttachment ID: {item_id} (from: {original_path})")
        print(f"  - Final type used for parsing: '{final_type}'")
        if final_type == 'txt' and original_detection != 'Not specifically recorded or same as final type' and original_detection != 'txt':
            print(f"  - Originally detected as: '{original_detection}' (then fell back to 'txt')")
        elif final_type == 'txt' and original_path.endswith('.unknownext'):
             print(f"  - Likely fell back to 'txt' due to unknown extension or no specific parser.")
        elif final_type == 'png' and original_path == sample_url: # Example for Google logo
            print(f"  - Detected type for URL '{sample_url}' is '{final_type}'.")
        elif final_type == 'jpeg' and original_path.startswith(dummy_image_path if dummy_image_path else ""): # For our dummy image
            print(f"  - Detected type for local image '{dummy_image_path}' is initially png, then ops change output to '{final_type}'. Type field shows '{item.get('type')}' from parser output.")
            # Note: The 'type' here is what the ImageParser determines based on content/ops, might not be the raw *detected* type before parsing if ops change format.
            # The `original_format` field inside image attachment data is more indicative of initial detection for images.
            if 'original_format' in item:
                print(f"    Original image format (from Pillow): {item['original_format']}")

# Demonstrate Detector class separately for clarity
print("\n--- Demonstrating Detector class directly ---")
detector = Detector()
dummy_txt_type = detector.detect(text_file_path)
print(f"Detector.detect('{text_file_path}'): '{dummy_txt_type}'") # Expected: txt

if dummy_image_path:
    dummy_img_type = detector.detect(dummy_image_path)
    print(f"Detector.detect('{dummy_image_path}'): '{dummy_img_type}'") # Expected: png

unkn_type = detector.detect(unknown_file_path)
print(f"Detector.detect('{unknown_file_path}'): '{unkn_type}'") # Expected: None or fallback to txt depending on detector's internal logic if it tries basic sniffing

# For a URL, detector might get a hint from Content-Type if it were passed directly, 
# but Attachments class handles URL download and then detects the local temp file.

print("\n--- Stage 2 Demonstration Complete ---")

# %% [md]
# ## 3. Parsing

# Based on the detected type, the `ParserRegistry` provides the correct parser. Each parser extracts data (text, image objects, audio segments, metadata).

# %% 
print("\n--- Inspecting Parsed Content from attachments_data ---")
if not atts_instance.attachments_data:
    print("No attachments were processed, skipping Parsing demonstration details.")
else:
    for item in atts_instance.attachments_data:
        print(f"\nParsed data for: {item.get('id', item.get('original_path_str', 'N/A'))} (Type: {item.get('type')})")
        if "text" in item and item['text']:
            # Displaying only a snippet of text if it's long
            text_snippet = item['text'][:100].replace("\n", " ") + ("..." if len(item['text']) > 100 else "")
            print(f"  Text (snippet): '{text_snippet}'")
        if "image_object" in item:
            img_obj = item['image_object']
            print(f"  Image Object: Present (Type: {type(img_obj)}, Mode: {getattr(img_obj, 'mode', 'N/A')}, Size: {getattr(img_obj, 'size', 'N/A')})")
            if "operations_applied" in item and item["operations_applied"]:
                print(f"  Image Operations Applied: {item['operations_applied']}")
            if "output_format" in item:
                print(f"  Image Output Format: {item['output_format']}")
        if item.get('type') == 'txt' and item.get('original_path_str') == unknown_file_path:
            print(f"  Content of '{unknown_file_path}': '{item.get('text')}'")

print("\n--- Stage 3 Demonstration Complete ---")

# %% [md]
# ## 4. Contact Sheet Generation (Conceptual)

# For document types like PDF, PPTX, DOCX, a contact sheet (visual preview image) is generated and added as another attachment item.
# We are not using such a document in this basic script, but if we did, an image item corresponding to its contact sheet would appear in `atts_instance.attachments_data`.
# Example: If `doc.pdf` was an input, you might find an item with `type='jpeg'` and `id='contact_sheet_doc1'` (or similar).

# %% 
print("\n--- Stage 4: Contact Sheet Generation (Conceptual) ---")
print("No document types like PDF/PPTX were used in this script to demonstrate contact sheet generation directly.")
print("If they were, an additional image item for the contact sheet would be in atts_instance.attachments_data.")

print("\n--- Stage 4 Demonstration Complete ---")


# %% [md]
# ## 5. Rendering & Output Preparation

# Finally, the processed data can be rendered in various formats for LLM consumption or display.

# %% 
print("\n--- Demonstrating Output Methods ---")
if not atts_instance.attachments_data:
    print("No attachments processed, skipping most output demonstrations.")
else:
    # String representation (default XML)
    print("\n1. `str(atts_instance)` (XML Output Snippet):")
    xml_output = str(atts_instance)
    print(xml_output[:300] + "...") # Show a snippet

    # Base64 encoded images
    print("\n2. `atts_instance.images` (Snippets of Base64 Data URIs):")
    if atts_instance.images:
        for i, img_data_uri in enumerate(atts_instance.images):
            print(f"  Image {i+1} (snippet): {img_data_uri[:70]}...")
    else:
        print("  No images available in atts_instance.images")

    # LLM-specific content formatting
    print("\n3. `atts_instance.to_openai_content('Test prompt for OpenAI')`:")
    openai_content = atts_instance.to_openai_content("Test prompt for OpenAI")
    print(openai_content)

    # Claude content can also be generated (similar structure)
    # print("\n`atts_instance.to_claude_content('Test prompt for Claude')`:")
    # claude_content = atts_instance.to_claude_content("Test prompt for Claude")
    # print(claude_content)

    # Markdown representation for Jupyter/IPython
    print("\n4. `atts_instance._repr_markdown_()` (String Output):")
    markdown_repr = atts_instance._repr_markdown_()
    print(markdown_repr) # This will be rendered nicely in a Jupyter notebook

print("\n--- Stage 5 Demonstration Complete ---")

# %% [md]
# ## 6. Cleanup

# Remove the temporary directory and its contents.

# %% 
try:
    shutil.rmtree(temp_dir_path)
    print(f"\nSuccessfully removed temporary directory: {temp_dir_path}")
except Exception as e:
    print(f"\nError removing temporary directory {temp_dir_path}: {e}")

print("\n--- Architecture Demonstration Script Finished ---") 