# Attachments – the Python funnel for LLM context

### Turn *any* file into model-ready text ＋ images, in one line

Most users will not have to learn anything more then that: `Attachments("path/to/file.pdf")`

> **TL;DR**  
> ```bash
> pip install attachments
> ```
> ```python
> from attachments import Attachments
> ctx = Attachments("report.pdf", "photo.jpg[rotate:90]")
> llm_ready_text   = str(ctx)       # all extracted text, already “prompt-engineered”
> llm_ready_images = ctx.images     # list[str] – base64 PNGs
> ```


Attachments aims to be **the** community funnel from *file → text + base64 images* for LLMs.  
Stop re-writing that plumbing in every project – contribute your *loader / transform / renderer* plugin instead!

## Quick-start ⚡

```bash
pip install attachments
````

```python
from attachments import Attachments

a = Attachments(
    "/path/to/contract.docx",
    "slides.pptx[:3,N]",                  # first 3 & last slide
    "https://…/table.csv[summary:true]",  # built-in df.describe()
    "diagram.png[rotate:90]"              # chained image transform
)

print(a)           # pretty text view
len(a.images)      # 👉 base64 PNG list
```

### Send to OpenAI

```python
from openai import OpenAI
from attachments import Attachments

pdf = Attachments("https://…/test.pdf")

client = OpenAI()
resp = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=pdf.to_openai("Analyse the following document:")
)
print(resp.choices[0].message.content)
```

### Send to Anthropic / Claude

```python
import anthropic
from attachments import Attachments

pptx = Attachments("https://…/test.pptx")

msg = anthropic.Anthropic().messages.create(
    model="claude-3-5-haiku-20241022",
    max_tokens=8_192,
    messages=pptx.to_claude("Analyse the slides:")
)
print(msg.content)
```

*(The package auto-injects one `to_<provider>()` helper per registered deliverer; if you add a new
`Deliverer` plugin called `myapi`, both `Attachment.as_myapi()` and `Attachments.to_myapi()` appear automatically.)*

---

## DSL cheatsheet 📝

| Piece                     | Example                   | Notes                                         |
| ------------------------- | ------------------------- | --------------------------------------------- |
| **Select pages / slides** | `report.pdf[1,3-5,-1]`    | Supports ranges, negative indices, `N` = last |
| **Image transforms**      | `photo.jpg[rotate:90]`    | Any token implemented by a `Transform` plugin |
| **Data-frame summary**    | `table.csv[summary:true]` | Ships with a quick `df.describe()` renderer   |

---

## Supported formats (out of the box)

* **Docs**: PDF, PowerPoint (`.pptx`), CSV.
* **Images**: PNG, JPEG, BMP, GIF, WEBP, HEIC/HEIF, …
* Plugins live in `attachments/plugins/`; drop in a new file, decorate it with `@register_plugin`, and it’s picked up at import time (or via `$ATTACHMENTS_PLUGIN_PATH`).

---

## Extending 🧩

```python
# my_ocr_renderer.py
from attachments.plugin_api import register_plugin, requires
from attachments.core import Renderer

@register_plugin("renderer_text", priority=50)
@requires("pytesseract", "PIL")
class ImageOCR(Renderer):
    content_type = "text"

    def match(self, obj):
        from PIL import Image
        return isinstance(obj, Image.Image)

    def render(self, obj, meta):
        import pytesseract
        return pytesseract.image_to_string(obj)
```

1. Put the file somewhere on disk.
2. `export ATTACHMENTS_PLUGIN_PATH=/abs/path/to/dir_or_file`
3. `import attachments` – your plugin is auto-discovered, no code changes.

---

## API reference (essentials)

| Object / method         | Description                                                     |
| ----------------------- | --------------------------------------------------------------- |
| `Attachments(*sources)` | Many `Attachment` objects flattened into one container          |
| `Attachments.text`      | All text joined with blank lines                                |
| `Attachments.images`    | Flat list of base64 PNGs                                        |
| `.to_openai(prompt="")` | Convenience wrapper (shown above)                               |
| `.to_claude(prompt="")` | idem                                                            |

---

### Roadmap

* More built-in loaders (DOCX, XLSX, HTML)

Join us – file an issue or open a PR! 🚀