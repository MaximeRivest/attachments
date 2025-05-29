#%%
from attachments import A, load, split, present, refine, adapt
from attachments.data import get_sample_path
#%%
att = A(get_sample_path("sample.svg")) | load.text_to_string 

att
# %%
print(att.text)
# %%