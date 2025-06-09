# Developer Guide: Adding New DSL Commands

This guide explains how to add new DSL commands to the `attachments` library while ensuring that the "Did you mean..." suggestion feature remains up-to-date.

## The Philosophy

Our goal is to make this process as easy as possible. For the most common case (adding a new command *key*), everything is fully automatic. For supporting suggestions on command *values*, a small manual step is required.

---

## 1. Adding a New DSL Command Key

This is for commands like `[new_feature: true]` or `[threshold: 0.5]`.

### What You Need to Do: Nothing. It's Automatic.

The library uses an AST-based discovery tool (`get_dsl_info`) that automatically scans the entire codebase and finds all command keys. The "Did you mean..." feature for keys will work automatically.

Simply use the command in your code via `att.commands.get()`, `att.commands['...']`, or `'...' in att.commands`.

#### Example: Creating a new `blur` refiner

```python
# in a refiner, processor, or any other verb...

@refiner
def blur(att: Attachment) -> Attachment:
    # Get the blur radius from the DSL, defaulting to 10
    radius = int(att.commands.get('blur', 10))
    
    # ... logic to apply blur to an image ...
    
    return att
```

That's it. The `get_dsl_info` tool will now discover the `blur` command, and if a user types `[blu: 20]`, the system will correctly suggest `blur`.

---

## 2. Supporting "Did You Mean..." for Command Values

This is for commands that accept a specific set of string values, like `[mode: fast]` where `fast` is one of several valid options.

### What You Need to Do: A Quick Manual Update

To provide suggestions for values (e.g., suggesting `fast` when the user types `fsat`), you need to tell the suggestion engine what the valid values are. This requires a quick, one-time update to `src/attachments/dsl_suggestion.py`.

#### Example: Adding suggestions for `[quality: low|medium|high]`

Let's say you are creating a feature that uses the `quality` command.

**Step 1: Add the list of valid values**

Open `src/attachments/dsl_suggestion.py` and add a new list containing your valid values.

```python
# src/attachments/dsl_suggestion.py

# ... existing code ...

VALID_FORMATS = ['plain', 'text', 'txt', 'markdown', 'md', 'html', 'code', 'xml', 'csv', 'structured']
VALID_QUALITY_LEVELS = ['low', 'medium', 'high'] # <-- ADD THIS

def suggest_format_command(format_value: str) -> Optional[str]:
# ... existing code ...
```

**Step 2: Add a suggestion helper function**

In the same file, add a small helper function for your new command. This keeps the logic clean and centralized.

```python
# src/attachments/dsl_suggestion.py

# ... existing code ...
def suggest_format_command(format_value: str) -> Optional[str]:
    # ... existing code ...

def suggest_quality_command(quality_value: str) -> Optional[str]:
    """Suggests a correction for the 'quality' command's value."""
    if quality_value in VALID_QUALITY_LEVELS:
        return None # It's already valid
    return find_closest_command(quality_value, VALID_QUALITY_LEVELS)
```

**Step 3: Use the helper in your code**

Now, in the verb or processor where you use the `quality` command, call your new helper to check the user's input and log a warning if needed.

```python
# in your processor or verb file...
from ..dsl_suggestion import suggest_quality_command
from ..config import verbose_log

# ...
def my_image_verb(att: Attachment) -> Attachment:
    quality_cmd = att.commands.get('quality', 'medium')
    
    # Check for typos and suggest corrections
    suggestion = suggest_quality_command(quality_cmd)
    if suggestion:
        verbose_log(f"⚠️ Warning: Unknown quality '{quality_cmd}'. Did you mean '{suggestion}'?")
        # You might want to fall back to a default or raise an error
        quality_cmd = 'medium'

    # ... rest of your logic using quality_cmd ...
    return att
```

By following this pattern, you ensure that the "Did you mean..." feature remains powerful and helpful for all DSL commands. 