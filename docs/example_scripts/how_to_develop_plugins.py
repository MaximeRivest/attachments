# %% [md]
# # How to develop plugins

# This guide will walk you through creating your own plugins for the `attachments` library. Plugins allow you to extend the library's functionality by adding support for new file types, transformations, rendering methods, or an entirely new way to package outputs for different APIs.

# ## Plugin Types

# The `attachments` library supports several types of plugins, each serving a distinct purpose in the processing pipeline:

# *   **`Loader`**: Responsible for taking a path (file path or URL) and loading its raw content into a Python object. For example, a `PDFLoader` might take "my_document.pdf" and return a `pypdf.PdfReader` object.
# *   **`Renderer`**: Takes a Python object (usually the output of a `Loader` or `Transform`) and converts it into a specific content type. There are different kinds of renderers:
#     *   `renderer_text`: Produces a string (e.g., extracting text from a PDF object).
#     *   `renderer_image`: Produces a list of base64 encoded image strings.
#     *   `renderer_audio`: Produces a list of base64 encoded audio strings.
# *   **`Transform`**: Modifies an object in place or functionally. Transforms are applied after loading and before rendering. They are triggered by tokens in the attachment string, like `photo.jpg[rotate:90]`. The `Rotate` transform is an example.
# *   **`Deliverer`**: Packages the final text, images, and audio content into the specific format expected by a downstream API (e.g., OpenAI, Anthropic).

# You can find the base classes for these in `src/attachments/core.py`: `Loader`, `Renderer`, `Transform`, and `Deliverer`.

# ## Creating and Registering a Plugin

# Let's create a simple `Renderer` that takes a string and "renders" it by converting it to uppercase.

# ```python
# # my_uppercase_renderer.py
# from attachments.plugin_api import register_plugin
# from attachments.core import Renderer # Import the base class
# from typing import Any, Dict

# @register_plugin(kind="renderer_text", priority=50) # Higher priority means it's tried sooner
# class UppercaseTextRenderer(Renderer):
#     content_type = "text"  # This renderer produces text

#     def match(self, obj: Any) -> bool:
#         # This renderer will only operate on string objects
#         return isinstance(obj, str)

#     def render(self, obj: Any, meta: Dict[str, Any]) -> str:
#         # The actual rendering logic
#         if isinstance(obj, str):
#             return obj.upper()
#         return "" # Should ideally not be reached if match() is specific enough
# ```

# ### Key Points:
# *   **Base Class**: Your plugin should inherit from one of the base classes (`Loader`, `Renderer`, `Transform`, `Deliverer`).
# *   **`@register_plugin`**: This decorator from `attachments.plugin_api` is crucial.
#     *   `kind`: Specifies the type of plugin. For our `UppercaseTextRenderer`, it's `"renderer_text"`. Other kinds include `"loader"`, `"renderer_image"`, `"transform"`, etc.
#     *   `priority`: An integer that determines the order in which plugins of the same kind are tried. Higher numbers are tried first. The default is 100.
# *   **Required Methods**:
#     *   `Loader`: `match(cls, path: str)` and `load(self, path: str)`.
#     *   `Renderer`: `content_type` (class attribute), `match(self, obj: Any)`, and `render(self, obj: Any, meta: Dict[str, Any])`.
#     *   `Transform`: `name` (class attribute for the DSL token) and `apply(self, obj: Any, arg: str | None)`.
#     *   `Deliverer`: `name` (class attribute) and `package(self, text, images, audio, prompt)`.

# ## Handling Optional Dependencies with `@requires`

# Often, plugins will depend on external libraries (e.g., `Pillow` for image processing, `pytesseract` for OCR). If a user doesn't have these libraries installed, your plugin shouldn't cause the entire `attachments` library to fail. The `@requires` decorator handles this gracefully.

# ```python
# # my_ocr_renderer.py
# from attachments.plugin_api import register_plugin, requires
# from attachments.core import Renderer
# from typing import Any, Dict

# # This plugin requires 'pytesseract' and 'PIL' (Pillow)
# @register_plugin("renderer_text", priority=60)
# @requires("pytesseract", "PIL", pip_names={"PIL": "Pillow", "pytesseract": "pytesseract"})
# class AdvancedImageOCR(Renderer):
#     content_type = "text"
#     # For selftest (see below)
#     _sample_obj = "path/to/dummy_image.png" # Path to a sample image for testing, or a PIL.Image object

#     def match(self, obj: Any) -> bool:
#         # This would typically check if obj is a PIL Image or something similar
#         try:
#             from PIL import Image
#             return isinstance(obj, Image.Image)
#         except ImportError:
#             return False # If PIL isn't even there, it can't match

#     def render(self, obj: Any, meta: Dict[str, Any]) -> str:
#         import pytesseract # Import here, as @requires ensures it's available
#         from PIL import Image

#         if not isinstance(obj, Image.Image):
#             return ""
#         return pytesseract.image_to_string(obj)

# ```
# ### How `@requires` Works:
# *   It checks if all listed modules can be imported.
# *   If any module is missing, the plugin class is replaced by a `MissingDependencyProxy`.
# *   The `@register_plugin` decorator will then silently skip registering this proxy.
# *   A warning is logged indicating which plugin was disabled and why (e.g., "Module 'pytesseract' not found. Try `pip install pytesseract`.").
# *   `pip_names`: This dictionary helps provide correct installation instructions if the PyPI package name differs from the import module name (e.g., module `PIL` is installed via `pip install Pillow`).

# ### Diagnostics and `@requires`
# The diagnostics layer we recently added ties into this. If a plugin is skipped due to missing dependencies, and an `Attachment` object fails to render a certain content type (e.g., "image") because all relevant renderers were disabled, the `attachment.debug()` method will provide a clear explanation:

# ```python
# from attachments import Attachment
# # Assume MyImageSnapshotRenderer requires 'playwright' but it's not installed.
# # a = Attachment("https://example.com[snapshot:true]") # if snapshot was a transform leading to a webpage object
# # If a webpage object was loaded, but the snapshot renderer (image) was disabled:
# # print(a.debug())
# ```
# Example output from `a.debug()`:
# ```
# Attachment: https://example.com
#   No renderer produced image. Tried:
#     ❌ MyImageSnapshotRenderer  (Module 'playwright' not found. Try `pip install playwright`.)
#     ❌ SomeOtherImageRenderer (predicate_mismatch)
# ```
# This tells the user exactly why they didn't get an image and how to fix it. Your plugin's `_attachments_disabled_msg` (set by `@requires`) becomes part of this diagnostic output.

# ## Plugin Quality: `PluginContract` and `selftest`

# To ensure plugins are well-behaved and follow basic expectations, the library includes a `PluginContract` (in `src/attachments/testing.py`). While not strictly enforced for external plugins automatically, it's good practice for your plugin to be compatible with its conventions.

# Many built-in plugins implement a `selftest(self, tmp_path)` method. This method is used by `pytest` (see `tests/test_all_plugins_contract.py`) to perform basic checks:
# *   **Loaders**: Can it `match` and `load` its `_sample_path` (an extension string like "pdf", "csv", for which `_create_sample_file_for_selftest` in `testing.py` will create a dummy file)?
# *   **Renderers**: Can it `match` and `render` its `_sample_obj` (a dummy Python object it expects)? Does the output type match its `content_type`?
# *   **Transforms**: Can it `apply` to its `_sample_obj`?
# *   **Deliverers**: Can it `package` various combinations of text, images, and audio?

# If your plugin uses `@requires`, the `selftest` will be automatically skipped if dependencies are missing.

# Consider adding `_sample_path` (for loaders, a string like "txt", "myext") or `_sample_obj` (for renderers/transforms, an actual minimal Python object) to your plugin class to facilitate testing.

# ```python
# # my_custom_loader.py
# from attachments.plugin_api import register_plugin, requires
# from attachments.core import Loader
# from attachments.testing import PluginContract # Can inherit for selftest
# from typing import Any

# @register_plugin("loader", priority=10)
# class MyCustomFormatLoader(Loader, PluginContract): # Inherit PluginContract
#     _sample_path = "myext" # The file extension this loader handles

#     @classmethod
#     def match(cls, path: str) -> bool:
#         return path.endswith(".myext")

#     def load(self, path: str) -> Any:
#         # In a real scenario, you'd read the file content
#         with open(path, 'r') as f:
#             content = f.read()
#         return {"path": path, "content": content, "type": "MyCustomObject"}

# # To make its selftest work, you might need to add "myext" handling to
# # _create_sample_file_for_selftest in src/attachments/testing.py,
# # or provide a _sample_obj if it made more sense for your loader's selftest.
# ```

# ## Plugin Discovery: `ATTACHMENTS_PLUGIN_PATH`

# By default, `attachments` discovers plugins within its own `attachments.plugins` directory. To load plugins from other locations (e.g., from your own project or a separate package):
# 1.  Place your plugin Python file (e.g., `my_cool_plugin.py`) in a directory.
# 2.  Set the environment variable `ATTACHMENTS_PLUGIN_PATH` to the absolute path of this directory (or the specific file).
#     ```bash
#     export ATTACHMENTS_PLUGIN_PATH=/path/to/my/plugins_directory
#     ```
#     Or, you can point to multiple paths separated by `os.pathsep` (e.g., `:` on Linux/macOS, `;` on Windows).
# 3.  When `import attachments` is next executed, it will attempt to discover and register plugins from this path.

# This mechanism allows for easy extensibility without modifying the core `attachments` library.

# ## Example: Running the Uppercase Renderer
# If you save the `my_uppercase_renderer.py` from above and set `ATTACHMENTS_PLUGIN_PATH` to its directory:

# ```python
# # test_uppercase_plugin.py
# import os
# # Make sure to set ATTACHMENTS_PLUGIN_PATH before the first import of attachments
# # For this example, let's assume my_uppercase_renderer.py is in ./my_plugins/
# plugin_dir = os.path.abspath("./my_plugins")
# os.environ["ATTACHMENTS_PLUGIN_PATH"] = plugin_dir

# from attachments import Attachment # First import after setting env var

# # Create an Attachment with a simple string object directly.
# # Normally, a loader would produce an object. Here, we simulate it.
# class MyStringWrapper:
#     def __init__(self, value):
#         self.value = value
#     def __str__(self): # Important for how Attachment might try to get text by default
#         return self.value

# # We need a dummy loader that can produce a plain string for our renderer to match
# from attachments.plugin_api import register_plugin
# from attachments.core import Loader

# @register_plugin("loader", priority=200) # High priority for this example
# class StringObjectLoader(Loader):
#     @classmethod
#     def match(cls, path: str) -> bool:
#         # Match a specific dummy path for this test
#         return path == "load_string_for_uppercase"
    
#     def load(self, path: str) -> Any:
#         return "hello world" # Return a raw string

# # Now, let's test it
# # The ATTACHMENTS_PLUGIN_PATH should have picked up StringObjectLoader AND UppercaseTextRenderer
# try:
#     att = Attachment("load_string_for_uppercase")
#     # UppercaseTextRenderer (priority 50) should be chosen over default StringTextRenderer (priority 0)
#     # if it matches. StringTextRenderer would also match a string.
#     # Check its .text attribute
#     print(f"Original object: '{att.obj}'") # Should be "hello world"
#     print(f"Rendered text: '{att.text}'")  # Expected: "HELLO WORLD"

#     # If UppercaseTextRenderer wasn't picked up, att.text would be "hello world" (from StringTextRenderer)
#     # or an error if no text renderer matched.
#     assert att.text == "HELLO WORLD"

# except Exception as e:
#     print(f"An error occurred: {e}")
#     print("Please ensure my_uppercase_renderer.py and StringObjectLoader (above) are discoverable via ATTACHMENTS_PLUGIN_PATH.")
#     # You might also want to print att.debug() here if it failed.
#     # if 'att' in locals():
#     #     print(att.debug())

# ```

# This comprehensive guide should help you get started with developing and integrating your own plugins into the `attachments` ecosystem!

# %%
