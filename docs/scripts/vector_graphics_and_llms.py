# %% [markdown]
# # Vector Graphics and LLMs: A Literate Programming Exploration
#
# This notebook demonstrates the elegant power of processing SVG vector graphics for LLM consumption using the `attachments` library with DSPy integration.
# We'll show how complex multimodal processing becomes simple and declarative.
#
# ## 1. High-Level API: Attachments with DSPy
#
# Let's begin by using the highest-level interface that seamlessly integrates with DSPy for AI-powered analysis.

# %%
from attachments.dspy import Attachments
from IPython.display import HTML, display
import dspy

# %% [markdown]
# We configure DSPy with a capable model for multimodal analysis.
# %%
dspy.configure(lm=dspy.LM('openai/gpt-4.1-nano', max_tokens=16000))

# %% [markdown]
# We create an `Attachments` context for the SVG URL. The DSPy-optimized version automatically handles fetching, parsing, and presenting both text and images in a format ready for DSPy signatures.
# %%
ctx = Attachments("https://upload.wikimedia.org/wikipedia/commons/6/62/Llama_mark.svg")

# %%
ctx.text[:2000]
# %% [markdown]
# Let's examine what we've captured from the SVG.
# The length of the SVG text is:
# %%
len(ctx.text)
# %% [markdown]
# the number of images rendered is:
# %%
len(ctx.images)
# %% [markdown]
# Display the rendered SVG image:
# %%
display(HTML(f"<img src='{ctx.images[0]}' style='max-width: 300px;'>"))

# %% [markdown]
# ## 2. Elegant DSPy Integration
#
# Now we'll demonstrate the true power: seamless multimodal AI analysis with minimal code.
# The DSPy-optimized Attachments work directly in signatures without any adapter calls.

# %%
# %% [markdown]
# Define DSPy signatures for SVG analysis and improvement.
# %%
class AnalyzeDesign(dspy.Signature):
    """Analyze SVG design and suggest one concrete improvement."""

    document: Attachments = dspy.InputField(description="SVG document with markup and rendered image")

    analysis: str = dspy.OutputField(description="Brief analysis of the design elements and visual appeal")
    improvement: str = dspy.OutputField(description="One specific, actionable improvement suggestion")

class GenerateImprovedSVG(dspy.Signature):
    """Generate an improved SVG based on analysis."""

    original_document: Attachments = dspy.InputField(description="Original SVG document")
    improvement_idea: str = dspy.InputField(description="Specific improvement to implement")

    improved_complete_svg: str = dspy.OutputField(description="Enhanced SVG markup with the improvement applied")

# %% [markdown]
# ### The Magic: Direct Integration
#
# Notice how the Attachments object works directly in DSPy signatures - no manual conversion needed:
# %%
analyzer = dspy.ChainOfThought(AnalyzeDesign)
generator = dspy.ChainOfThought(GenerateImprovedSVG)

# %% [markdown]
# Analyze the SVG - ctx works directly as a DSPy input!
# %%
analysis_result = analyzer(document=ctx)
# %% [markdown]
# The analysis of the SVG design:
# %%
analysis_result.analysis
# %% [markdown]
# The suggested improvement:
# %%
analysis_result.improvement

# %% [markdown]
# ### Generate Improvement
#
# Now let's apply the suggested improvement:
# %%
improvement_result = generator(
    original_document=ctx,
    improvement_idea=analysis_result.improvement
)
# %% [markdown]
# The length of the improved SVG:
# %%
len(improvement_result.improved_complete_svg)
# %% [markdown]
# First 200 characters of improved SVG:
# %%
improvement_result.improved_complete_svg[:200] + "..."

# %% [markdown]
# The improved SVG:
# %%
print(improvement_result.improved_complete_svg)

# %% [markdown]
# ## 4. Loading Improved SVG Back into Attachments
# 
# Now let's demonstrate the full cycle by loading our AI-improved SVG back into the attachments library.
# We'll do this entirely in-memory without touching the disk - much more elegant!

# %%
from io import StringIO
from PIL import Image as PILImage
import base64

# Create an in-memory SVG and load it directly into attachments
# We'll use a data URL approach to avoid disk I/O
svg_content = improvement_result.improved_complete_svg

# Create a data URL for the SVG content
svg_data_url = f"data:image/svg+xml;base64,{base64.b64encode(svg_content.encode()).decode()}"

# %% [markdown]
# Load the improved SVG directly from memory using a data URL:
# %%
improved_ctx = Attachments(svg_data_url)

# %%
HTML(f"<img src='{svg_data_url}' style='max-width: 600px;'>")

# %% [markdown]
# Compare the original and improved versions:
# %%
print("📊 COMPARISON METRICS")
print("=" * 40)
print(f"Original SVG length: {len(ctx.text):,} characters")
print(f"Improved SVG length: {len(improved_ctx.text):,} characters")
print(f"Change: {len(improved_ctx.text) - len(ctx.text):+,} characters")
print(f"Original images: {len(ctx.images)}")
print(f"Improved images: {len(improved_ctx.images)}")

# %% [markdown]
# Display both versions side by side:
# %%
print("🖼️ VISUAL COMPARISON")
print("=" * 30)
print("Original SVG:")
display(HTML(f"<div style='display: inline-block; margin: 10px;'><h4>Original</h4><img src='{ctx.images[0]}' style='max-width: 250px; border: 1px solid #ccc;'></div>"))

print("Improved SVG:")
if improved_ctx.images:
    display(HTML(f"<div style='display: inline-block; margin: 10px;'><h4>Improved</h4><img src='{improved_ctx.images[0]}' style='max-width: 250px; border: 1px solid #ccc;'></div>"))
else:
    print("⚠️ No images rendered for improved SVG")

# %% [markdown]
# ### Key Insights from the In-Memory Cycle
# 
# This demonstration shows the complete in-memory workflow:
# 1. **Load** original content with attachments
# 2. **Analyze** using DSPy AI signatures  
# 3. **Generate** improvements with AI
# 4. **Reload** improved content directly from memory (no disk I/O!)
# 5. **Compare** results visually and quantitatively
# 
# The data URL approach (`data:image/svg+xml;base64,...`) allows us to work entirely in-memory,
# making the workflow faster and more elegant for dynamic content generation.

# %%

# %% [markdown]
# ## 3. The Power Demonstrated
#
# This simple example showcases the elegant power of `attachments.dspy`:
# %%
print("✨ ATTACHMENTS + DSPy POWER")
print("=" * 30)
print("🚀 What we achieved with minimal code:")
print("   • Fetched and parsed SVG from URL")
print("   • Rendered SVG to PNG automatically")
print("   • Seamless multimodal DSPy integration")
print("   • AI-powered design analysis")
print("   • Automated improvement generation")
print("   • Type-safe, declarative programming")
print()
print("🎯 Lines of core logic: ~10")
print("🔧 Manual multimodal handling: 0")
print("⚡ DSPy signatures that just work: 2")

# %% [markdown]
# ## Conclusion: Elegance in Simplicity
#
# The `attachments.dspy` integration demonstrates how complex multimodal AI workflows can be both powerful and elegantly simple:
#
# 1. **One Import**: `from attachments.dspy import Attachments`
# 2. **Zero Adapters**: Objects work directly in DSPy signatures
# 3. **Full Multimodal**: Text + images handled automatically
# 4. **Declarative**: Clean signatures express intent clearly
# 5. **Scalable**: Same pattern works for any file type
#
# This is the future of AI development: powerful capabilities with minimal complexity.

# %%
print("🎉 Demo complete - Ready to build amazing multimodal AI systems!")
