#%%
import pyvista as pv, io, base64, openai
from attachments import attach, load, present
from attachments.core import Attachment, loader, presenter

@loader(match=lambda a: a.path.lower().endswith((".glb", ".gltf")))
def three_d(a: Attachment):
    a._obj = pv.read(a.input_source)
    return a

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


@presenter
def markdown(att: Attachment, mesh: pv.DataSet) -> Attachment:
    att.text = f"{att.path} bounds: {mesh.bounds}"
    return att

pipe = load.three_d | present.images + present.markdown
att = attach("/home/maxime/Projects/attachments/src/attachments/data/Llama.glb") | pipe

#%%
print("Number of images:", len(att.images))



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
