#%%
from attachments import auto_attach
from openai import OpenAI

att = auto_attach(
"""
what does sample.pdf[pages: 1] says? And the object in sample.svg?

Also, what is the first sentence in  https://en.wikipedia.org/wiki/Llama_(language_model)[select: p][images: false]
""",
    root_dir = ["/home/maxime/Projects/attachments/src/attachments/data",
                "https://en.wikipedia.org"]
).openai_responses()
print(OpenAI().responses.create(input=att, model="gpt-4.1-nano").\
      output[0].content[0].text)

#The first page of the PDF (sample.pdf[pages:1]) says:
#**"Hello PDF!"**
#
#The object in sample.svg is an SVG image that displays a title "Attachments Library Demo", 
# with a blue circle, a red square, a green triangle, and a caption "SVG with both code and 
# visual representation".
#
#The first sentence in the Wikipedia page about Llama (language model) is:  
#**"Llama (Large Language Model Meta AI, formerly stylized as LLaMA) is a family of large 
# language models (LLMs) released by Meta AI starting in February 2023."**



# %%
