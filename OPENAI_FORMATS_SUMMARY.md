# OpenAI API Formats Implementation Summary

## Overview

We have successfully implemented support for **both** OpenAI API formats in the attachments library. This addresses the important distinction between two different OpenAI endpoints that use different data structures.

## The Two Formats

### 1. Chat Completions API (Standard)
**Endpoint**: `client.chat.completions.create()`
**Method**: `ctx.to_openai()`

```python
{
    "messages": [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "What's in this image?"},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,iVBORw0..."}
                }
            ]
        }
    ]
}
```

### 2. Responses API (Alternative)
**Endpoint**: `client.responses.create()`
**Method**: `ctx.to_openai_responses()`

```python
# Usage:
input_data = ctx.to_openai_responses("What's in this image?")
response = client.responses.create(model="gpt-4", input=input_data)

# Returns (direct array for input parameter):
[
    {
        "role": "user", 
        "content": [
            {"type": "input_text", "text": "What's in this image?"},
            {
                "type": "input_image",
                "image_url": "data:image/png;base64,iVBORw0..."
            }
        ]
    }
]
```

## Key Differences

| Aspect | Chat Completions | Responses |
|--------|------------------|-----------|
| **Return Type** | `List[Dict]` (messages) | `List[Dict]` (direct input) |
| **Usage** | `client.chat.completions.create(messages=result)` | `client.responses.create(input=result)` |
| **Text Type** | `"text"` | `"input_text"` |
| **Image Type** | `"image_url"` | `"input_image"` |
| **Image URL** | `{"url": "..."}` (nested) | `"..."` (direct string) |

## Implementation Details

### Auto-Generated Methods
Both adapters are automatically added to the `Attachments` class:
- `@adapter` decorator on `openai_chat` → `ctx.to_openai()`
- `@adapter` decorator on `openai_responses` → `ctx.to_openai_responses()`

### Content Type Controls
Both methods support the same content control parameters:
```python
ctx.to_openai("prompt", text=True, audio=True, images=True)
ctx.to_openai_responses("prompt", text=False, images=True)
```

### Precedence Rules
Same precedence for both formats:
1. **DSL commands**: `file.pdf[text:false]`
2. **Adapter parameters**: `ctx.to_openai("...", text=False)`
3. **Global settings**: `Attachments("file.pdf", text=False)`
4. **Defaults**: All enabled

## Testing

### Verification Tests
- ✅ Format structure validation
- ✅ Content type verification
- ✅ Image URL packaging differences
- ✅ Content control parameters
- ✅ Auto-generation functionality

### Usage Examples
```python
from attachments import Attachments

ctx = Attachments("image.jpg", "document.pdf")

# Chat Completions API format
chat_data = ctx.to_openai("Analyze these files")
response = client.chat.completions.create(model="gpt-4", messages=chat_data)

# Responses API format  
input_data = ctx.to_openai_responses("Analyze these files")
response = client.responses.create(model="gpt-4", input=input_data)
```

## Architecture Benefits

1. **Clear Separation**: Each format has its own dedicated adapter
2. **Consistent Interface**: Same parameter signature for both
3. **Auto-Discovery**: Methods are automatically added to `Attachments` class
4. **Type Safety**: Proper return type annotations
5. **Content Controls**: Full DSL and parameter support for both

## Cursor Rules Integration

Added to `myrules.mdc`:
- **CRITICAL**: Never mix the two formats
- **Documentation**: Clear examples of both formats
- **Implementation**: Separate adapters, no cross-calling

This ensures future development maintains the distinction and doesn't accidentally merge or confuse the two different OpenAI API formats. 