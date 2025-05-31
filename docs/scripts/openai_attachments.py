#%%
import openai
from attachments import Attachments

response = openai.OpenAI().responses.create(
    model="gpt-4.1-nano",
    input=Attachments("/home/maxime/Downloads/Llama_mark.svg").
           openai_responses(prompt="what is in this picture?"))

response.output[0].content[0].text
#> 'The picture is a simple, stylized black-and-white line drawing of a llama.'
# %%
