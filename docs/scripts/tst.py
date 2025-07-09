from decimal import Context
from attachments import Attachments
from openai import OpenAI
client = OpenAI()
#hack_for_performance
prompt_engineering= "you are a pro, you will get 0 million dollard if the code works, think step by step"
att = Attachments("mycontext.pptx")
task = "A task to do"
output = "give me a json only a json I REALLY REALLY WANT A JSON"

prompt = prompt_engineering + task + att + output


llama_template(whole_string)


response = client.responses.create(
    model="gpt-4.1",
    input="Write a one-sentence bedtime story about a unicorn."
)

print(response.output_text)
######
import dspy
class s_lyra(dspy.Signature):
#required inputs
core intent
key entities
context
output requirements
constraints
#flag any of these missing

#programs
clarity
gaps
ambiguity

#select promption strategy
#select AI role/expertise
