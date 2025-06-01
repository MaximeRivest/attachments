#%%
from attachments import Attachments, attach, processors
from attachments.data import get_sample_path
#%%


#%%
from attachments import load, present, refine, modify, split
res = (attach("https://en.wikipedia.org/wiki/Artificial_intelligence[select: p]") 
       | load.url_to_bs4
       | modify.select
       | present.images
)
#%%
res.images[0][:100]
#%%
from IPython.display import HTML
HTML(f"<img src='{res.images[0]}' alt='Image' />")



#%%
from attachments import load, present, modify, split
res = (attach("https://en.wikipedia.org/wiki/Artificial_intelligence[select: p]") 
       | load.url_to_bs4
       | modify.select
       | present.markdown
       | split.paragraphs
)
#%%
len(res)
#%%
len(res[0].text)

#%%
res.images



#%%

res = Attachments("https://en.wikipedia.org/wiki/Artificial_intelligence[images: false][select: p][split: sentences]") 


#%%
len(res)

#%%
for i, att in enumerate(res):
    print(f"{i}: {att.text[:500]}")





#%%
print(res.images)









#%%
ctx = Attachments("https://en.wikipedia.org/wiki/Artificial_intelligence[images: false][select: p][split: paragraphs]")

#%%
len(ctx[0].text)
#%%
len(ctx)
#%%
len(ctx[0].images)
#%%
len(ctx[0].images[0])
#%%
len(ctx[0].images[0][0])
#%%
for i, att in enumerate(ctx.attachments):
    print(f"{i}: {att.text[:100]}")

#%%
print(ctx.attachments[2].text)
#%%
print(str(ctx))

#%%
print(len(ctx.images))

#%%

#%%
# Option 1: Use included sample files (works offline)
txt_path = get_sample_path("sample.txt")
ctx = Attachments(pdf_path, txt_path)

print(str(ctx))      # Pretty text view
print(len(ctx.images))  # Number of extracted images

# Try different file types
docx_path = get_sample_path("test_document.docx")
csv_path = get_sample_path("test.csv")
json_path = get_sample_path("sample.json")

ctx = Attachments(docx_path, csv_path, json_path)
print(f"Processed {len(ctx)} files: Word doc, CSV data, and JSON")

# Option 2: Use URLs (same API, works with any URL)
ctx = Attachments(
    "https://github.com/MaximeRivest/attachments/raw/main/src/attachments/data/sample.pdf",
    "https://github.com/MaximeRivest/attachments/raw/main/src/attachments/data/sample_multipage.pptx"
)

print(str(ctx))      # Pretty text view  
print(len(ctx.images))  # Number of extracted images
```

### Advanced usage with DSL

```python
from attachments import Attachments

a = Attachments(
    "https://github.com/MaximeRivest/attachments/raw/main/src/attachments/data/" \
    "sample_multipage.pptx[3-5]"
)
print(a)           # pretty text view
len(a.images)      # 👉 base64 PNG list
```