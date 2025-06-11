# Demo

See Attachments in action! This demo shows how to process various file types and extract content for LLM use.

```{raw} html
<video width="100%" controls>
  <source src="https://github.com/MaximeRivest/attachments/raw/main/demo.mp4" type="video/mp4">
  Your browser does not support the video tag.
</video>
```

## What you'll see in the demo:

- **PDF processing**: Extract text and images from PDF documents
- **PowerPoint slides**: Process PPTX files with slide-specific extraction
- **Web scraping**: Use CSS selectors to extract specific content from web pages
- **Image processing**: Handle various image formats with transformations
- **LLM integration**: Send processed content directly to OpenAI and Claude APIs

## Try it yourself:

```python
from attachments import Attachments

# Process the same files shown in the demo
pdf = Attachments("https://github.com/MaximeRivest/attachments/raw/main/src/attachments/data/sample.pdf")
pptx = Attachments("https://github.com/MaximeRivest/attachments/raw/main/src/attachments/data/sample_multipage.pptx[3-5]")

print(f"PDF text length: {len(str(pdf))}")
print(f"PPTX images extracted: {len(pptx.images)}")
```

```{seealso}
- {doc}`examples/how_to_load_and_morph` - Detailed tutorial on URL processing
- {doc}`examples/pptx_split_demo` - PowerPoint processing examples
- {doc}`dsl_cheatsheet` - Complete DSL command reference
``` 