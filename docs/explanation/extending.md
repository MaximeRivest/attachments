## User-side tutorial: adding an external plugin

### Create a folder and a plugin file

```bash
mkdir -p ~/my_attachments_plugins
cat > ~/my_attachments_plugins/my_md_loader.py <<'PY'
from attachments.registry import REGISTRY
from attachments.core import Loader, Renderer

class MarkdownLoader(Loader):
    def match(self, path): return path.endswith(".md")
    def load(self, path):  return open(path, encoding="utf-8").read()

REGISTRY.register("loader", MarkdownLoader, priority=120)

class MarkdownText(Renderer):
    content_type = "text"
    def match(self, obj): return isinstance(obj, str) and obj.lstrip().startswith("#")
    def render(self, obj, meta): return obj  # already plain text

REGISTRY.register("renderer_text", MarkdownText, priority=120)
PY
```

### Point the environment variable to the folder

```bash
export ATTACHMENTS_PLUGIN_PATH="$HOME/my_attachments_plugins"
```

*(Multiple locations?  Use colons:
`export ATTACHMENTS_PLUGIN_PATH="$HOME/my_plugins:/opt/company/pdf_handlers"`)*

### Use it

```python
from attachments import Attachment
doc = Attachment("README.md")
print(doc.text[:200])
```

If everything is correct you’ll see your Markdown printed; the registry listing would show:

```python
from attachments.registry import REGISTRY; REGISTRY.dump()
```

```
{'loader': [(120, 'MarkdownLoader'), (100, 'ImageLoader'), ...],
 'renderer_text': [(120, 'MarkdownText'), (120, 'CSVBrief'), ...],
 ...}
```

---

## Key points & guarantees

| Behaviour                       | Notes                                                                                                                     |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| **Priority still works**        | External plugins register just like built-ins; you can call `REGISTRY.bump_priority()` at runtime if you need to reorder. |
| **No package install required** | They’re just ordinary `.py` files discovered via path scanning.                                                           |
| **Isolation**                   | If a user breaks their plugin, the import error appears before built-ins load, making debugging obvious.                  |
| **Uninstalling**                | Remove the file or take it out of the env-var path – nothing else to touch.                                               |

Feel free to plug in as many corporate or personal handlers as you like!
