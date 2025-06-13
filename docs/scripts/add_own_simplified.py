#%%
import pyvista as pv, io, base64, openai
from attachments import attach, load, present
from attachments.core import Attachment, loader, presenter

# Attachments must first must identification criteria. Here we use the file extension.
def glb_match(a: Attachment):
    return a.path.lower().endswith((".glb", ".gltf"))

# Then we need to load the attachment. Here we use pyvista to load the file.
@loader(match=glb_match)
def three_d(a: Attachment):
    a._obj = pv.read(a.input_source)
    return a

# Then we need to turn the object into llm friendly format. 
# Here, for image presentation, we use pyvista to render the object into images.
@presenter
def images(att: Attachment, mesh: "pyvista.MultiBlock") -> Attachment:
    p = pv.Plotter(off_screen=True)
    p.add_mesh(mesh)
    if isinstance(mesh, pv.MultiBlock):
        mesh = mesh.combine(merge_points=True)
    else:
        mesh = mesh
    for _ in range(8):
        buffer = io.BytesIO()
        p.screenshot(buffer)
        buffer.seek(0)
        att.images.append("data:image/png;base64," + base64.b64encode(buffer.read()).decode())
        p.camera.azimuth += 45
    p.close()
    return att

# Then we need to turn the object into llm friendly format. 
# Here, for text presentation, we use the path and the bounds of the object.
@presenter
def markdown(att: Attachment, mesh: pv.DataSet) -> Attachment:
    att.text = f"{att.path} bounds: {mesh.bounds}"
    return att

# Simple pipeline.
# This pipeline is a simple pipeline that loads the object, renders it into images,
# and then renders the object into text.
pipe = load.three_d | present.images + present.markdown
att = attach("/home/maxime/Projects/attachments/src/attachments/data/Llama.glb") | pipe

#%%
print("Number of images:", len(att.images))


#%%
from attachments.pipelines import processor

@processor(
    match=glb_match,
    description="A custom GLB processor"
)
def glb_to_llm(att: Attachment) -> Attachment:
    return att | load.three_d | present.images + present.markdown
#%%
from attachments.dspy import Attachments
import dspy

att1 = Attachments("/home/maxime/Projects/attachments/src/attachments/data/Llama.glb")

dspy.configure(lm=dspy.LM("openai/gpt-4.1"))
rag = dspy.Predict("three_d_model -> description_of_3d_object")
rag(three_d_model=att)


#%%
from IPython.display import HTML

images_html = ""
for i, data_url in enumerate(att1.images):
    style = f"width:150px; display:inline-block; margin:2px; border:1px solid #ddd"
    images_html += f'<img src="{data_url}" style="{style}" />'
    if (i + 1) % 4 == 0:
        images_html += "<br>"
display(HTML(images_html))
#%%
print("Number of images:", len(att1.images))



# %%
# Open AI completion api
cli = openai.OpenAI()
resp = cli.chat.completions.create(
        model="gpt-4.1-nano",
        messages=att.openai("What do you see")
    ).choices[0].message.content
print("OpenAI completion api", resp)

# %%
# OpenAI responses api
cli = openai.OpenAI()
resp = cli.responses.create(
    model="gpt-4.1-nano",
    input=att.openai_responses("What do you see")
).output[0].content[0].text
print("OpenAI Responses api", resp)

# %%
# Anthropic
import anthropic
claude = anthropic.Anthropic()
claude_msg = claude.messages.create(
    model="claude-3-5-haiku-20241022",
    max_tokens=1024,
    messages=att.claude("Describe this 3D model:")
).content[0].text
print("Claude:", claude_msg)

# %%
# Agno agent
from agno.agent import Agent
from agno.models.openai import OpenAIChat
agent = Agent(model=OpenAIChat(id = "gpt-4.1-nano"))
agno_resp = agent.run(**att.agno("Describe this 3D model:")).content
print("Agno response:", agno_resp)

# %%
# DSPy
import dspy
dspy.configure(lm=dspy.LM("openai/gpt-4.1"))
rag = dspy.Predict("three_d_model -> description_of_3d_object")
dspy_resp = rag(three_d_model=att.dspy()).description_of_3d_object
print("DSPy: ", dspy_resp)

# %%

# %%




# %%
