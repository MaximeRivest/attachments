# %% [markdown]
# # How to Add a whole new file type to Attachments
# 
# This tutorial demonstrates how to build a complete pipeline for a new file type in the Attachments library.
# We'll implement the 2 necessary verbs: LOAD → PRESENT
# 
# In this case, we'll be adding support for 3D files (.glTF, .blend, .obj).
# 
# **What we're building:**
# - A loader that can read .glb, .gltf, .blend, .obj files into a bpy object.
# - A presenter that renders 3D models to images (multiple camera angles)
# 
# **Why this matters:**
# The tagline is "Turn _any_ file into model-ready text + images, in one line" - and glTF, .blend, .obj are 
# major 3D formats used in web development, game engines, AR/VR, and 3D modeling workflows.
#
# First, we need to install bpy.
#
# ```bash
# uv pip install bpy
# ```
#
# ## Working with 3D files
# 
# In general, at a minimum, we need to:
# 1. Load the file into an object
# 2. Present the object as text and images
# 
# Thus, we will first do that simply without worrying about attachments for now.
#
# ## Loading 3D files as bpy objects
# 
# First, we'll use the Attachments library's data helper to get the paths to sample 3D files.
# We have three different formats available: .blend, .glb, and .gltf
#
#%%
from attachments.data import get_sample_path

# Get paths to all our sample 3D files
blend_path = get_sample_path("Llama.blend")
glb_path = get_sample_path("demo.glb")
print(f"Blend file: {blend_path}")
print(f"GLB file: {glb_path}")

# %% [markdown]
# Now let's load each file type into Blender's bpy context. Different file formats require different import methods.
# 
# ### Loading .blend files
# For .blend files, we use `bpy.ops.wm.open_mainfile()` which opens the entire Blender scene.
# %%
import bpy

# Clear the default scene first
bpy.ops.wm.read_factory_settings(use_empty=True)

# Load the .blend file
bpy.ops.wm.open_mainfile(filepath=blend_path)
print("Objects in .blend file:")
for obj in bpy.data.objects:
    print(f"  - {obj.name} ({obj.type})")

# %% [markdown]
# ### Loading .glb files
# For .glb (binary glTF) files, we use the glTF importer.
# %%
# Clear the scene and load GLB
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=glb_path)

print("Objects in .glb file:")
for obj in bpy.data.objects:
    print(f"  - {obj.name} ({obj.type})")

# %% [markdown]
# ## Creating a unified loader function
# 
# Now let's create a function that can handle all three formats automatically based on file extension,
# with proper error handling for problematic files.
# %%
def load_3d_file(filepath: str):
    """Load a 3D file into Blender, supporting .blend, .glb, and .gltf formats."""
    import os
    
    # Clear the current scene
    bpy.ops.wm.read_factory_settings(use_empty=True)
    
    # Get file extension
    _, ext = os.path.splitext(filepath.lower())
    
    try:
        if ext == '.blend':
            bpy.ops.wm.open_mainfile(filepath=filepath)
        elif ext in ['.glb', '.gltf']:
            bpy.ops.import_scene.gltf(filepath=filepath)
        else:
            raise ValueError(f"Unsupported file format: {ext}")
        
        # Return information about loaded objects
        objects = list(bpy.data.objects)
        return {
            'filepath': filepath,
            'format': ext,
            'objects': [{'name': obj.name, 'type': obj.type} for obj in objects],
            'object_count': len(objects),
            'success': True,
            'error': None
        }
    except Exception as e:
        return {
            'filepath': filepath,
            'format': ext,
            'objects': [],
            'object_count': 0,
            'success': False,
            'error': str(e)
        }

# Test our unified loader with all three files
for path in [blend_path, glb_path, gltf_path]:
    result = load_3d_file(path)
    print(f"\nLoaded {result['format']} file:")
    print(f"  File: {result['filepath']}")
    
    if result['success']:
        print(f"  ✓ Success! Objects: {result['object_count']}")
        for obj in result['objects']:
            print(f"    - {obj['name']} ({obj['type']})")
    else:
        print(f"  ✗ Failed: {result['error']}")

# %% [markdown]
# ## Working with the successfully loaded files
# 
# Let's focus on the files that loaded successfully and demonstrate how to work with them.
# %%
# Load the .blend file (most reliable)
blend_result = load_3d_file(blend_path)
if blend_result['success']:
    print("Working with .blend file objects:")
    for obj_info in blend_result['objects']:
        obj = bpy.data.objects[obj_info['name']]
        print(f"  - {obj.name}: location={obj.location}, rotation={obj.rotation_euler}")

# Load the .glb file (also reliable, embedded data)
glb_result = load_3d_file(glb_path)
if glb_result['success']:
    print("\nWorking with .glb file objects:")
    for obj_info in glb_result['objects']:
        obj = bpy.data.objects[obj_info['name']]
        print(f"  - {obj.name}: location={obj.location}, rotation={obj.rotation_euler}")

# %% [markdown]
# Now we need to turn these 3D scenes into images for presentation.
# %%

# %% [markdown]
# # 📚 Rendering 3-D files with Attachments, one literate step at a time
# Donald Knuth advised us to tell a story while we program.  
# This notebook does exactly that: we weave a brief narrative that
# constructs—in small, testable pieces—a pipeline that
# 1. **Loads** `.blend` or `.glb` files into Blender,
# 2. **Renders** a turn-table of PNG snapshots, and
# 3. **Displays** those images inline via base-64 HTML.
#
# Feel free to convert this script to `.ipynb` with `jupytext`.
# Let’s begin.

# %% [markdown]
# ## 0 · Imports & sample paths
# We rely only on the Python standard library, `bpy`, and `IPython.display`.
# Attachments merely provides *sample* assets so that the notebook is fully
# reproducible.

# %%
import os, math, base64, tempfile, shutil
from IPython.display import HTML, display

import bpy
from attachments.data import get_sample_path

BLEND_PATH = get_sample_path("Llama.blend")
GLB_PATH   = get_sample_path("demo.glb")

# %% [markdown]
# ## 1 · Resetting Blender’s scene
# Blender starts with a cube, camera, and lamp—noise for our purposes.  
# A single helper gives us a blank canvas.

# %%
def reset_scene():
    """Throw everything out and start from an empty factory scene."""
    bpy.ops.wm.read_factory_settings(use_empty=True)

# %% [markdown]
# ## 2 · Guaranteeing a camera and a light
# Many demo objects ship without either.  We add a simple
# three-quarter camera and a sunlight if necessary.

# %%
def ensure_camera_and_light():
    """Ensure basic illumination and a camera with an isometric view."""
    scene = bpy.context.scene

    # Camera
    if "Camera" not in bpy.data.objects:
        cam = bpy.data.cameras.new("Camera")
        cam_obj = bpy.data.objects.new("Camera", cam)
        bpy.context.collection.objects.link(cam_obj)
        scene.camera = cam_obj
    else:
        cam_obj = bpy.data.objects["Camera"]

    cam_obj.location       = (4, -4, 3)
    cam_obj.rotation_euler = (math.radians(60), 0, math.radians(45))

    # Light
    if not [o for o in bpy.data.objects if o.type == "LIGHT"]:
        sun = bpy.data.lights.new("Sun", type="SUN")
        sun_obj = bpy.data.objects.new("Sun", sun)
        sun_obj.location = (0, 0, 10)
        bpy.context.collection.objects.link(sun_obj)

# %% [markdown]
# ## 3 · Loading `.blend` and `.glb`
# The two formats use different Blender operators; we hide that
# divergence behind `load_3d_file`.

# %%
def load_3d_file(path: str):
    """Load a .blend or .glb/.gltf into a fresh scene."""
    reset_scene()
    ext = os.path.splitext(path)[1].lower()
    if ext == ".blend":
        bpy.ops.wm.open_mainfile(filepath=path)
    elif ext in {".glb", ".gltf"}:
        bpy.ops.import_scene.gltf(filepath=path)
    else:
        raise ValueError(f"Unsupported extension: {ext}")
    ensure_camera_and_light()

# %% [markdown]
# ## 4 · Producing a turn-table of PNGs
# We rotate all non-camera/light objects around Z and
# render `n_views` images into a temporary folder.

# %%
def _detect_eevee_engine():
    """Return the proper EEVEE enum for this Blender version, or fallback to Cycles."""
    enum_items = {item.identifier for item in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items}
    if "BLENDER_EEVEE" in enum_items:         # Blender ≤ 3.6
        return "BLENDER_EEVEE"
    if "BLENDER_EEVEE_NEXT" in enum_items:    # Blender 4.x+
        return "BLENDER_EEVEE_NEXT"
    return "CYCLES"                           # last-ditch fallback

def render_turntable(n_views: int = 4, size: int = 512):
    """Render `n_views` rotations and return the PNG paths."""
    scene = bpy.context.scene
    tmpdir = tempfile.mkdtemp()

    # ▸ choose the right engine
    scene.render.engine = _detect_eevee_engine()
    scene.render.resolution_x = scene.render.resolution_y = size
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = True

    out = []
    for i in range(n_views):
        angle = 2 * math.pi * i / n_views
        for obj in scene.objects:
            if obj.type not in {"CAMERA", "LIGHT"}:
                obj.rotation_euler[2] = angle
        path = os.path.join(tmpdir, f"view_{i:02d}.png")
        scene.render.filepath = path
        bpy.ops.render.render(write_still=True)
        out.append(path)
    return out

# %% [markdown]
# ## 5 · Inline HTML display
# Base-64-encode each PNG, wrap them in `<img>` tags, and stream the HTML back
# to the notebook.

# %%
def show_pngs_inline(png_paths, thumb=200):
    """Display PNGs inline via a simple flexbox strip."""
    tags = []
    for p in png_paths:
        with open(p, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        style = f"width:{thumb}px;margin:4px;border:1px solid #ddd"
        tags.append(f"<img src='data:image/png;base64,{b64}' style='{style}'/>")
    html = "<div style='display:flex;flex-wrap:wrap'>" + "".join(tags) + "</div>"
    display(HTML(html))

# %% [markdown]
# ## 6 · Demo time ✨
# We now chain our helpers: *load → render → display*  
# First the `.blend`, then the `.glb`.

# %%
for sample in [("Blend file", BLEND_PATH), ("GLB file", GLB_PATH)]:
    title, path = sample
    print(f"\n⏳ {title}: {os.path.basename(path)}")
    load_3d_file(path)
    pngs = render_turntable()
    show_pngs_inline(pngs)

# %%
