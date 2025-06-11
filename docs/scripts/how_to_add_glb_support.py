# %% [markdown]
# # How to Add a new file type to Attachments
#
# This tutorial demonstrates how to build a complete pipeline for a new file type in the Attachments library,
# focusing on loading and presenting `.glb` 3D files.
# We'll use the [PyVista](https://pyvista.org/) library, a modern, Python 3.12-compatible alternative to `bpy`.
#
# **What we're building:**
# - A loader that can read `.glb` and `.blend` files into a PyVista mesh object.
# - A presenter that renders 3D models to images from multiple camera angles (a turntable).
#
# **Why this matters:**
# The tagline is "Turn _any_ file into model-ready text + images, in one line" - and glTF is a major 3D format.
# With PyVista, we can support these files without being tied to a specific Python version.
#
# First, let's install PyVista. We'll use `pyvista[all]` to get all the extras, including notebook support.
#
# ```bash
# uv pip install "pyvista[all]"
# ```
#
# ## Working with 3D files
#
# In general, at a minimum, we need to:
# 1. Load the file into an object
# 2. Present the object as text and images
#
# PyVista makes this incredibly simple.

# %% [markdown]
# ## 0 · Imports & sample paths
# We will use `pyvista` for 3D file handling and rendering, and `IPython.display` for showing the results.
# `attachments` provides the sample files.

# %%
import os
import tempfile
import base64
import io
import pyvista as pv
from IPython.display import HTML, display
from attachments.data import get_sample_path

# Get paths to our sample 3D files
GLB_PATH = get_sample_path("demo.glb")

# %% [markdown]
# ## 1 · Loading `.glb` and `.gltf`
# PyVista's `read` function automatically handles different file formats.
# We'll create a simple loading function.

# %%
def load_3d_file(path: str):
    """Load a .glb or .gltf file using PyVista."""
    return pv.read(path)

# %% [markdown]
# ## 2 · Producing a turn-table of PNGs
# We'll rotate the camera around the object and render snapshots into a temporary folder.
# Using `Plotter(off_screen=True)` allows for rendering without a visible window, which is perfect for scripts.

# %%
def render_turntable(mesh, n_views: int = 8, size: int = 512):
    """Render `n_views` rotations and return a list of PNG image bytes."""
    images_bytes = []

    plotter = pv.Plotter(off_screen=True, window_size=[size, size])
    plotter.add_mesh(mesh, color='lightblue', show_edges=True)
    plotter.add_axes(viewport=(0, 0, 0.4, 0.4))  # Make the axes widget larger
    plotter.view_isometric()

    angle_step = 360.0 / n_views
    for i in range(n_views):
        buffer = io.BytesIO()
        plotter.screenshot(buffer)
        buffer.seek(0)
        images_bytes.append(buffer.read())
        plotter.camera.azimuth += angle_step
        plotter.render()  # Force a re-render

    plotter.close()
    return images_bytes

# %% [markdown]
# ## 3 · Inline HTML display
# This helper function takes the generated PNGs and displays them in the notebook.

# %%
def show_images_inline(images_bytes, cols=4, thumb=150):
    """Display a list of PNG images from bytes in a grid by embedding them as base64."""
    images_html = ""
    for i, img_bytes in enumerate(images_bytes):
        b64 = base64.b64encode(img_bytes).decode()

        style = f"width:{thumb}px; display:inline-block; margin:2px; border:1px solid #ddd"
        images_html += f'<img src="data:image/png;base64,{b64}" style="{style}" />'
        
        if (i + 1) % cols == 0 and i < len(images_bytes) - 1:
            images_html += "<br>"
            
    display(HTML(images_html))

# %% [markdown]
# ## 4 · Demo time ✨
# Now we chain our helpers: *load → render → display*.
# We'll do this for both a `.glb` and a `.gltf` file.

# %%
for sample in [("GLB file", GLB_PATH)]:
    title, path = sample
    print(f"\n⏳ {title}: {os.path.basename(path)}")
    mesh = load_3d_file(path)
    images_bytes = render_turntable(mesh)
    show_images_inline(images_bytes)

# %% [markdown]
# ## 5 · (Optional) Converting `.blend` files
# While `pyvista` doesn't natively support `.blend` files, we can use Blender's command-line interface to convert them to a supported format like `.glb`. This is a one-time operation that allows us to integrate Blender assets into our Python 3.12+ workflow.
#
# The following cell shows how you would run this conversion from a terminal.
#
# ```bash
# blender --background --python-expr "import bpy; bpy.ops.wm.open_mainfile(filepath='src/attachments/data/Llama.blend'); bpy.ops.export_scene.gltf(filepath='src/attachments/data/Llama.glb')"
# ```
#
# Once converted, we can load the `Llama.glb` just like any other .glb file.

# %%
# Let's process the newly converted Llama model
LLAMA_PATH = get_sample_path("Llama.blend").replace('.blend', '.glb') # Assuming it's converted

if os.path.exists(LLAMA_PATH):
    print(f"\n⏳ Llama GLB file: {os.path.basename(LLAMA_PATH)}")
    llama_mesh = load_3d_file(LLAMA_PATH)
    
    # The Llama model is oriented Z-up, but PyVista expects Y-up.
    # We'll rotate it -90 degrees on the X-axis to correct it.
    llama_mesh.rotate_x(-90, inplace=True)
    
    images_bytes = render_turntable(llama_mesh, n_views=16)
    show_images_inline(images_bytes)
else:
    print(f"\n🤷 Llama GLB not found at {LLAMA_PATH}. Skipping.")

# %% [markdown]
# ## 6 · Extending Attachments to support 3D files
#
# Now for the magic part. We've figured out how to load a 3D model and render it. How do we package this logic so that the `Attachments` library can use it automatically?
# The library is designed to be easily extended with plugins. We just need to define two functions: a `@loader` and a `@presenter`.
#
# ### 6.1 · The Loader
#
# A loader's job is to open a file and load its contents into a Python object that presenters can work with.
# For a "perfect" loader, we should follow a few best practices:
#
# 1.  **Matcher Function**: Use a `match` function to identify the file type. This keeps the loading logic clean.
# 2.  **Handle Any Source**: Use `att.input_source` to transparently handle local files and URLs.
# 3.  **Store in `_obj`**: Place the loaded object in `att._obj` for the framework to use.
# 4.  **Handle `ImportError`**: Gracefully fail with a helpful message if a dependency is missing.
#
# Here is the improved, "perfect" version of our loader:


from attachments.core import Attachment, loader

def gltf_match(att: Attachment) -> bool:
    """Matches .glb and .gltf files, whether local or on the web."""
    return att.path.lower().endswith(('.glb', '.gltf'))

@loader(match=gltf_match)
def load_gltf_or_glb(att: Attachment) -> Attachment:
    """
    Loads .gltf and .glb files into a PyVista mesh object.
    
    This loader is a best-practice example:
    - It uses a `match` function to identify applicable files.
    - It uses `att.input_source` to work with both local paths and URLs.
    - It stores the loaded object in `att._obj` for other pipeline steps.
    - It handles missing dependencies gracefully with an `ImportError`.
    """
    try:
        import pyvista as pv
    except ImportError:
        raise ImportError("pyvista is required for 3D model loading. Install with: `uv pip install pyvista`")
        
    try:
        # Use att.input_source to handle local files and URLs seamlessly.
        data = pv.read(att.input_source)
        
        # If pv.read returns a MultiBlock container, we'll combine it into a single mesh.
        # This ensures our presenters receive a renderable pv.DataSet.
        if isinstance(data, pv.MultiBlock):
            mesh = data.combine(merge_points=True)
        else:
            mesh = data
        
        # Store the loaded mesh in `_obj` for the dispatcher.
        att._obj = mesh
        
        # Add relevant metadata.
        att.metadata['content_type'] = 'model/gltf-binary' if att.path.endswith('.glb') else 'model/gltf+json'
        att.metadata['3d_bounds'] = mesh.bounds

    except Exception as e:
        att.text = f"Failed to load 3D model with PyVista: {e}"
        
    return att

# %% [markdown]
# ### 6.2 · The Presenter
#
# The presenter's job is to take the data loaded by our loader (the PyVista mesh) and "present" it by extracting text and images. This is where our turntable rendering and auto-orientation logic comes in.
#
# That's an excellent question. Using dispatched presenters like `text`, `markdown`, and `images` allows for modular and flexible pipelines. While a single presenter function can be simpler, splitting the logic is more powerful and robust.
#
# We will define two presenters:
# 1.  `images`: This will perform the expensive rendering of the 3D model into a turntable view. It will add the generated images to `att.images` and store metadata about the rendering process.
# 2.  `markdown`: This will create a text summary of the 3D model. It will be "smart" and check the metadata to see if the `images` presenter has already run, including details about the turntable in its summary.
#
# This separation of concerns is a best practice. First, let's look at our auto-orientation utility function.

# %%
import numpy as np

def align_major_axis_to_y(mesh):
    """
    Rotates a pyvista mesh so its longest dimension aligns with the Y-axis.
    Returns the mesh and a status message about the alignment.
    """
    bounds = mesh.bounds
    extents = [bounds[1] - bounds[0], bounds[3] - bounds[2], bounds[5] - bounds[4]]
    major_axis_index = np.argmax(extents)
    
    status = "Mesh is already Y-up."
    if major_axis_index != 1:
        align_axis = ['X', 'Y', 'Z'][major_axis_index]
        status = f"Aligned to Y-up (longest dimension was on {align_axis}-axis)."
        if major_axis_index == 0:  # Longest axis is X, rotate around Z to bring X to Y
            mesh.rotate_z(90, inplace=True)
        elif major_axis_index == 2:  # Longest axis is Z, rotate around X to bring Z to Y
            mesh.rotate_x(-90, inplace=True)
            
    return mesh, status

# %% [markdown]
# Now we can define the presenters. The `@presenter` decorator, combined with type hints, tells Attachments to run these functions when it finds a PyVista mesh in `att._obj`.

# %%
from attachments.core import presenter

@presenter
def images(att: Attachment, mesh: pv.DataSet) -> Attachment:
    """
    Renders a turntable of a PyVista mesh, auto-orients it,
    and adds the views as base64 data URLs to the attachment.
    """
    try:
        # Avoid re-rendering if images have already been generated
        if '3d_views' in att.metadata:
            return att

        # 1. Auto-orient the mesh and get the status for metadata.
        aligned_mesh, align_status = align_major_axis_to_y(mesh)
        
        # 2. Render the turntable to get a list of PNG image bytes.
        png_bytes_list = render_turntable(aligned_mesh, n_views=16)

        # 3. Add images and metadata for other presenters.
        att.metadata['3d_views'] = len(png_bytes_list)
        att.metadata['3d_auto_align_status'] = align_status

        print(len(att.images))
        for png_bytes in png_bytes_list:
            b64_string = base64.b64encode(png_bytes).decode('utf-8')
            att.images.append(f"data:image/png;base64,{b64_string}")

    except Exception as e:
        att.metadata['3d_images_presenter_error'] = str(e)
        att.text += f"\n\n*Error generating 3D turntable: {e}*\n"
        
    return att


@presenter
def markdown(att: Attachment, mesh: pv.DataSet) -> Attachment:
    """
    Generates a markdown summary for a 3D model. It intelligently
    reports on the turntable if the `images` presenter has run.
    """
    try:
        model_name = os.path.basename(att.path)
        att.text += f"\n\n## 3D Model Summary: {model_name}\n"

        # Check for metadata from the images presenter.
        if '3d_views' in att.metadata:
            status = att.metadata.get('3d_auto_align_status', 'Alignment status unknown')
            att.text += f"A {att.metadata['3d_views']}-view turntable of the model has been rendered ({status}).\n"
        else:
            att.text += "This is a 3D model object. To see a visual representation, include the `images` presenter in the pipeline.\n"

        # Add basic mesh info as a list.
        att.text += f"- **Bounds**: `{mesh.bounds}`\n"

    except Exception as e:
        att.metadata['3d_markdown_presenter_error'] = str(e)
        att.text += f"\n\n*Error generating 3D model summary: {e}*\n"
        
    return att

# %% [markdown]
# ## 7 · Putting It All Together: Explicit Pipelines
#
# As you astutely observed from the output, simply calling `Attachments(LLAMA_PATH)` didn't work. The logs show that a default pipeline was used, which tried many standard loaders but not our custom `load_gltf_or_glb`.
#
# This is a key lesson in extending `attachments`: for full control and to guarantee our custom logic runs, we can build an **explicit pipeline**. This is the "power user" API mentioned in the architecture documents.
#
# We now chain our loader with our new `images` and `markdown` presenters. This modular approach is powerful, idiomatic, and allows for greater control.

# %%
from attachments import attach, load, present

# Define our explicit pipeline for 3D models
# It chains our custom loader with our `images` and `markdown` presenters.
glb_pipeline = (
    load.load_gltf_or_glb
    | present.images + present.markdown
)

# Now, let's process the Llama file with our specific pipeline
LLAMA_PATH = get_sample_path("Llama.blend").replace('.blend', '.glb')

#%%
llama_attachment = attach(LLAMA_PATH) | glb_pipeline

print(llama_attachment.text)
print(f"\nNumber of images extracted: {len(llama_attachment.images)}")

# Display the images that are now part of the attachment object
images_html = ""
for i, data_url in enumerate(llama_attachment.images):
    style = f"width:150px; display:inline-block; margin:2px; border:1px solid #ddd"
    images_html += f'<img src="{data_url}" style="{style}" />'
    if (i + 1) % 4 == 0:
        images_html += "<br>"
display(HTML(images_html))
#%%




import openai
from attachments import attach, load, present

glb_pipeline = (
    load.load_gltf_or_glb
    | present.images + present.markdown
)

client = openai.OpenAI()
llama_attachment = attach(LLAMA_PATH) | glb_pipeline

resp = client.responses.create(
    input=llama_attachment.openai_responses("Describe this 3D model"),
    model="gpt-4.1-nano"  # You can also use "gpt-4o"
)
print(resp.output[0].content[0].text)

# %% [markdown]
# ## 8 · One-liners for other LLM SDKs
# The same `Attachments` object can be sent to other providers thanks to adapters.
# Below are *very concise* examples for Anthropic Claude, Agno, and DSPy.

# %%
# Anthropic Claude (vision-capable)
try:
    import anthropic
    claude = anthropic.Anthropic()
    claude_msg = claude.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=1024,
        messages=llama_attachment.claude("Describe this 3D model:")
    )
    print("Claude:", claude_msg.content)
except ImportError:
    print("anthropic not installed; skipping Claude example")

# %%
# Agno agent
try:
    from agno import Agent
    agent = Agent(model="gpt-4o-mini")
    agno_resp = agent.run(llama_attachment.agno("Describe this 3D model:"))
    print("Agno response:", agno_resp)
except ImportError:
    print("agno not installed; skipping Agno example")

# %%
# DSPy chain
try:
    import dspy
    dspy.configure(lm=dspy.LM("openai/gpt-4o-mini"))
    rag = dspy.ChainOfThought("question, document -> answer")
    result = rag(
        question="What does this 3D model depict?",
        document=llama_attachment.dspy()
    )
    print("DSPy answer:", getattr(result, "answer", result))
except ImportError:
    print("dspy not installed; skipping DSPy example")

# %%
