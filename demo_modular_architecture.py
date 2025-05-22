#!/usr/bin/env python3
"""Demo of the new modular attachments architecture."""

import sys
sys.path.insert(0, 'src')

print("🔧 Attachments Modular Architecture Demo")
print("=" * 50)

# Import the modular components
from attachments.core import load, modify, present, adapt
from attachments import Attachments

print("\n1. 📋 Core Namespaces")
print(f"   Loaders: {[attr for attr in dir(load) if not attr.startswith('_')]}")
print(f"   Modifiers: {[attr for attr in dir(modify) if not attr.startswith('_')]}")
print(f"   Presenters: {[attr for attr in dir(present) if not attr.startswith('_')]}")
print(f"   Adapters: {[attr for attr in dir(adapt) if not attr.startswith('_')]}")

print("\n2. 📄 Loading and Processing PDF")
# Load a PDF
pdf_att = load.pdf("examples/sample.pdf")
print(f"   Loaded: {type(pdf_att.content).__name__} from {pdf_att.source}")

# Extract text
text_att = present.text(pdf_att)
print(f"   Text extracted: {len(text_att.content)} characters")

# Generate images
images_att = present.images(pdf_att)
print(f"   Images generated: {len(images_att.content)} pages")

print("\n3. 🔄 Using Modifiers")
# Load with page specification
pdf_with_pages = load.pdf("examples/sample.pdf[pages: 1]")
print(f"   Commands parsed: {pdf_with_pages.commands}")

# Apply modifier
modified_att = modify.pages(pdf_with_pages)
print(f"   Pages after modification: {modified_att.content.page_count}")

print("\n4. 🔗 OpenAI Adapter")
openai_format = adapt.openai(pdf_att, "Analyze this document")
print(f"   OpenAI content items: {len(openai_format)}")
for i, item in enumerate(openai_format[:3]):  # Show first 3 items
    print(f"   Item {i+1}: {item['type']}")

print("\n5. 🚀 High-Level Interface")
# Use the high-level interface
ctx = Attachments("examples/sample.pdf")
print(f"   Files loaded: {len(ctx)}")
print(f"   Total text length: {len(ctx.text)}")
print(f"   Total images: {len(ctx.images)}")

# OpenAI format
openai_msgs = ctx.to_openai("Please analyze this document")
print(f"   OpenAI messages: {len(openai_msgs)}")
print(f"   Message role: {openai_msgs[0]['role']}")
print(f"   Content items: {len(openai_msgs[0]['content'])}")

print("\n6. 🎯 Type-Safe Dispatch Demo")
import pandas as pd
import numpy as np

# Create test data
df = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
arr = np.array([1, 2, 3, 4, 5])

# Multiple dispatch works automatically
df_text = present.text(df)
df_markdown = present.markdown(df)
arr_markdown = present.markdown(arr)

print(f"   DataFrame text: {len(df_text)} chars")
print(f"   DataFrame markdown: {'|' in df_markdown}")  # Should have table pipes
print(f"   Array markdown: {'```' in arr_markdown}")   # Should have code blocks

print("\n✅ All components working correctly!")
print("\n🏗️  Architecture Benefits:")
print("   • Type-safe dispatch")
print("   • Modular components")
print("   • Easy extensibility")
print("   • Auto-registration")
print("   • Clean separation of concerns")
print("\n🔮 Ready for new loaders, presenters, modifiers & adapters!") 