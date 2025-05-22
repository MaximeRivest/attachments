# %% [markdown]
# # Attachment pipelines
# ## Overview
# Plugins in the Attachments library will be designed explicitly to support intuitive pipeline operations. Plugins will be callable, composable, and behave predictably within pipelines. This document defines how Loaders, Transformers, Renderers, and Deliverers should operate.

# ## Pipeline Syntax

# The pipeline syntax supports chaining and branching:

# * Chaining (sequential execution): `|`
# * Branching (parallel execution): `&`

# ### Example Pipelines

#%%
# Single-use pipeline
# at its core, a pipeline is a function that takes a path and returns an attachment OR anything else that comes out of the 
# deliverer, still unsure about the name (suggestions welcome).
# The attachments library will make it easy to add functions and would be loaded like this:
#%%
import attachments.functions.loaders as at_l
import attachments.functions.transformers as at_t
import attachments.functions.image_renderers as at_ri
import attachments.functions.text_renderers as at_rt
import attachments.functions.audio_renderers as at_ra
import attachments.functions.deliverers as at_d

#%% [markdown]
# or more simply:
#%%
from attachments.shorthand import *

#%% [markdown]
# this has the advantage of letting user use the automatic completion of the IDE to find the available functions.
"/home/maxime/Projects/attachments/examples/sample.pdf" | 
    at_l.load_pdf() |
    at_t.pages(":2") |
    (at_rt.pdf() | at_t.summarize_text()) & at_ri.pdf() |
    at_t.tile_image() |
    at_d.openai()

#%% [markdown]
# This is considered the low level usage of the library. It is what we use in the background to create the Attachment and
# Attachments objects (more on that later).
#%% [markdown]
# Save and reuse a pipeline
# By simply assigning the pipeline to a variable, we can reuse it as a callable. Notice how above we choose to provide the
# arguments directly in the function calls whereas below we stay general and the user of the `pdf_to_openai` uses the square
# bracket syntax to pass arguments to the pipeline. The way it works is that loaders always extract the arguments from the path
# and stores them in the `Attachment` object as commands those will be pick up by any plugins that needs them. The convention
# still needs to be defined. But that may emerge from the usage as developers and contributors experiment with this.
#%%
pdf_to_openai = at_l.load_pdf() |
    at_t.remove_pages() |
    (at_rt.pdf() | at_t.summarize_text()) & at_ri.pdf() |
    at_t.tile_image(always = False) |
    at_d.openai()

pdf_to_openai("/home/maxime/Projects/attachments/examples/sample.pdf[:2 & -5:, tiling = True]")

#%% [markdown]
# ## Pipeline composition
# Pipelines can be composed by simply chaining them together.
# As each loader has a match method to check if the path is for itself to process we can see if each pipeline is compatible 
# with the input path if se we use it else we pass it to the next pipeline.
# Advanced developers can create this however they want but the primary goal is to make the development of Attachments
# as easy as possible.
#
# The attachments library will output 1 Attachments class that will run through one pipeline of pipelines behind the scenes.
# Attachments will tak a list of paths or several path like below and will run the pipelines of pipelines on each path.
# It will thus hold a list of Attachment objects. It will provide all the deliverer methods on the list to concatenate them
# all the lists of attachments. See more in the examples below.
#
#%%
# the end goal is this:



pdf_pipeline = (
        at_l.load_pdf() | 
        at_t.pages() | at_t.regex_filter() | at_t.translate()
        (at_rt.pdf() | at_t.summarize_text()) & at_ri.pdf() | 
        at_t.tile_image(always = False)
    )

pdf_md_pipeline = (
        at_l.load_pdf() | 
        at_t.pages() | at_t.regex_filter() | at_t.translate()
        (at_rt.pdf_md() & at_ri.pdf() | 
        at_t.tile_image(always = False)
    )

pptx_xml_pipeline = (at_l.load_pptx() | 
    at_t.pages() | 
    at_rt.pptx_xml() & at_ri.pptx() | 
    at_t.tile_image(always = False))

pptx_md_pipeline = (at_l.load_pptx() | 
    at_t.pages() | 
    at_rt.pptx_md() & at_ri.pptx() | 
    at_t.tile_image(always = False))


#this is mostly a fallback
txt_pipeline = at_l.load_txt() | at_rt.txt() 


attachments = Attachments(pipelines = [pdf_pipeline, pptx_xml_pipeline, pptx_md_pipeline, txt_pipeline])


all_my_attachments = attachments("md:/home/maxime/Projects/attachments/examples/sample.pdf[:2 & -5:, tiling = True]",
            "xml:/home/maxime/Projects/attachments/examples/sample.pptx",
            "/home/maxime/Projects/attachments/examples/sample.txt")


all_my_attachments.to_openai() # or to_openai(all_my_attachments)

# %% [markdown]
# for use here:
#%%
response = client.responses.create(
    model="gpt-4.1-nano",
    input=[
    {
        "role": "user",
        "content": all_my_attachments.to_openai("what do you see in these three files?") # or at_d.to_openai(all_my_attachments)
    }
]
)
response.output[0].content[0].text

# %% [markdown]
# ## Anthropic / Claude
#%%
import anthropic
msg = anthropic.Anthropic().messages.create(
    model="claude-3-5-haiku-20241022",
    max_tokens=8_192,
    messages=all_my_attachments.to_claude("Analyse the slides:") # or at_d.to_claude(all_my_attachments)
)
print(msg.content)

#other specialized attachments objects can be created
# this could still be diserable because it concats the txt of all intividual attachments and provides the deliverers
attachments_txt_only = Attachments(pipelines = [txt_pipeline])



txt_to_openai = at_l.load_txt() | at_rt.txt() | at_d.openai()

txt_to_openai("/home/maxime/Projects/attachments/examples/sample.txt")
#%%
attachment_to_openai = pdf_to_openai | txt_to_openai

#%%

openai_content = attachment_to_openai("/home/maxime/Projects/attachments/examples/sample.pdf[:2 & -5:, tiling = True]")
openai_content = attachment_to_openai("/home/maxime/Projects/attachments/examples/sample.txt")

#%%
new_pipeline = pdf_to_openai.pop(reshape_for_openai) | txt_to_openai.pop(reshape_for_openai)
myattachmentsoject = new_pipeline("/home/maxime/Projects/attachments/examples/sample.pdf[:2 & -5:, tiling = True]",
           "/home/maxime/Projects/attachments/examples/sample.txt")

myattachmentsoject.to_openai() # or to_openai(my_attachments_oject)
myattachmentsoject.to_claude() # or to_claude(my_attachments_oject)
#%%
# Defined pipeline
my_pipeline = myfavpptxloader() | transform_pptx_fromindices() | summarizer_transform() | text_render() & image_render() | curlopenaideliverer()
my_pipeline("Path/to/pptx")

# Transforms with arguments
"Path/to/pptx" | myfavpptxloader() | transform_pptx_fromindices(':2','-5:') | text_render() & image_render() | curlopenaideliverer()

# File-path transform syntax
"Path/to/pptx[:2,-5:]" | myfavpptxloader() | transform_pptx_fromindices() | text_render() & image_render() | curlopenaideliverer()

# %% [markdown]
# ## Plugin Behaviors

# ### Loader

# * **Responsibility**: Convert input paths into an `Attachment` object with `.obj` populated.
# * **Usage**: Must be callable independently.

#%%
att = myfavpptxloader("Path/to/pptx[:2,-5:]")
# %% [markdown]

# * If transform arguments in the path (e.g., `[indices]`) have no matching transform in the pipeline, loaders should gracefully ignore them.

# ### Transformer

# * **Responsibility**: Modify `Attachment.obj` or `Attachment.text/images/audio`.
# * **Usage**: Callable independently and within pipelines.
# * Transforms can have optional arguments.

#%%
att = transform_pptx_fromindices(':2', '-5:', attachment=att)
# %% [markdown]

# * Decorator example:

#%%
@Transformer
def summarize_and_tile(att):
    # Modify .text and .images directly
    return att

summarize_and_tile(att).to_openai()
# %% [markdown]

# ### Renderer

# * **Responsibility**: Generate final `.text`, `.images`, or `.audio` from `.obj`.
# * **Behavior**: Multiple renderers can run in parallel (fork), populating different fields of the same `Attachment` object.
# * Once a renderer runs, the `Attachment` object records it, allowing re-triggering rendering later.

#%%
att = text_render(att)
att = image_render(att)
# %% [markdown]

# * Renderer invocation should set the active renderer state on the `Attachment`.

# ### Deliverer

# * **Responsibility**: Convert the `Attachment` object into the structure required by downstream APIs (e.g., OpenAI).
* **Requirement**: Must fail explicitly if no renderer output (e.g., `.text` or `.images`) is present.

#%%
res = "file.csv" | csv_load | csv_text_renderer | to_openai  # works
res = "file.csv" | csv_load | to_openai                      # raises error
# %% [markdown]
# ## Flexible Invocation Patterns

# * Both object methods and standalone function invocations must be supported:

#%%
att.to_openai()
to_openai(att)
# %% [markdown]

# * Re-triggering renderers upon repeated calls:

#%%
att = other_text_renderer(att)
mynew_function_summarizing_the_text_and_tiling_image(att).to_openai()  # Uses other_text_renderer
# %% [markdown]

# ## Plugin Definition Flexibility

# * Any plugin type (Loader, Transformer, Renderer, Deliverer) can be defined from any Python function using a decorator matching the plugin type.
# * The decorators will validate that the function meets essential plugin requirements.

#%%
@loader
def csv_load(path):
    return pd.read_csv(path)
# %% [markdown]

# * Enforce pipeline correctness at runtime (e.g., loaders must have subsequent renderers).

# ## Error Handling

# * Clear and immediate errors when pipeline constraints aren't met, such as a loader without a renderer or a deliverer called without renderer outputs.

# %% [markdown]
# This specification ensures intuitive, flexible, and robust pipeline interactions within the Attachments library ecosystem.
