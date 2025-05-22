#!/usr/bin/env python3
"""
Demo: Adapter Pipeline Vision

Exploring:
1. Adapters that work with both Attachment and Attachments
2. Presentation specification in pipelines  
3. The "squashing" nature of adapters as exit points
"""

from typing import List, Dict, Any, Union, Optional
from dataclasses import dataclass
from attachments.core import Attachment, load, modify, present, adapt
from attachments.core.decorators import adapter, presenter
from attachments.utils.parsing import parse_path_expression


# First, let's explore adapter overloading
@adapter
def openai_chat(att: Attachment, prompt: str = "") -> List[Dict[str, Any]]:
    """Adapt single attachment for OpenAI."""
    content = []
    
    if prompt:
        content.append({"type": "text", "text": prompt})
    
    # Extract text and images using presenters
    try:
        text_result = present.text(att)
        if text_result and hasattr(text_result, 'content'):
            content.append({"type": "text", "text": text_result.content})
    except:
        pass
    
    try:
        images_result = present.images(att)
        if images_result and hasattr(images_result, 'content'):
            for img in images_result.content:
                content.append({"type": "image_url", "image_url": {"url": img}})
    except:
        pass
    
    return [{"role": "user", "content": content}]


# Hypothetical Attachments adapter (would go in high-level interface)
def openai_chat_multi(attachments: List[Attachment], prompt: str = "") -> List[Dict[str, Any]]:
    """
    Adapt multiple attachments for OpenAI - this is the "squashing" operation.
    
    This shows how we combine multiple attachments into a single LLM message.
    """
    all_content = []
    
    if prompt:
        all_content.append({"type": "text", "text": prompt})
    
    # Squash all attachments together
    for att in attachments:
        # Extract text
        try:
            text_result = present.text(att)
            if text_result and hasattr(text_result, 'content'):
                all_content.append({"type": "text", "text": f"\n--- From {att.source} ---\n{text_result.content}"})
        except:
            pass
        
        # Extract images
        try:
            images_result = present.images(att)  
            if images_result and hasattr(images_result, 'content'):
                for img in images_result.content:
                    all_content.append({"type": "image_url", "image_url": {"url": img}})
        except:
            pass
    
    return [{"role": "user", "content": all_content}]


# Now let's explore presentation specification ideas
class PresentationPipeline:
    """
    A pipeline that can specify presentation format.
    
    Ideas:
    1. Use DSL: "file.pdf[present:markdown]"
    2. Pipeline configuration: pipeline.with_presentation('markdown')
    3. Presentation as part of pipeline: load | modify | present.as('markdown')
    """
    
    def __init__(self, loader_pipeline, presentation='text'):
        self.loader_pipeline = loader_pipeline
        self.presentation = presentation
    
    def __call__(self, source: str) -> Attachment:
        # Parse DSL to check for presentation override
        path, commands = parse_path_expression(source)
        presentation = commands.get('present', self.presentation)
        
        # Load and modify
        att = self.loader_pipeline(source)
        
        # Apply presentation
        if presentation == 'markdown':
            result = present.markdown(att)
        elif presentation == 'xml':
            result = present.xml(att)
        elif presentation == 'images':
            result = present.images(att)
        else:
            result = present.text(att)
        
        # Return new attachment with presented content
        return Attachment(result, att.source, {**att.commands, 'presented_as': presentation})


def demo_adapter_overloading():
    """Demo adapters working with single vs multiple attachments."""
    print("🔄 Adapter Overloading Demo")
    print("=" * 50)
    
    # Single attachment
    print("\n1. Single Attachment → OpenAI:")
    att = load.pdf("examples/sample.pdf")
    if att and att.content:
        att = modify.pages(att, "1-2")
        openai_msg = adapt.openai_chat(att, "Summarize this")
        print(f"   Single message: {len(openai_msg)} items")
        print(f"   Content items: {len(openai_msg[0]['content'])}")
    
    # Multiple attachments (simulated)
    print("\n2. Multiple Attachments → OpenAI (Squashing):")
    attachments = []
    for file in ["examples/sample.pdf", "sample.png"]:
        try:
            if file.endswith('.pdf'):
                att = load.pdf(file)
            else:
                att = load.image(file)
            if att and att.content:
                attachments.append(att)
        except:
            pass
    
    if attachments:
        openai_msgs = openai_chat_multi(attachments, "Compare these files")
        print(f"   Squashed into: {len(openai_msgs)} message")
        print(f"   Total content items: {len(openai_msgs[0]['content'])}")
        print(f"   Sources included: {[att.source for att in attachments]}")


def demo_presentation_in_dsl():
    """Demo presentation specification via DSL."""
    print("\n📝 Presentation via DSL")
    print("=" * 50)
    
    test_cases = [
        "examples/sample.pdf[present:text]",
        "examples/sample.pdf[present:markdown]", 
        "examples/sample.pdf[pages:1-2,present:images]",
        "examples/sample.pptx[present:xml]",
    ]
    
    for test in test_cases:
        path, commands = parse_path_expression(test)
        print(f"\n{test}")
        print(f"   Presentation: {commands.get('present', 'default')}")
        print(f"   Other commands: {[k for k in commands if k != 'present']}")


def demo_presentation_pipeline():
    """Demo presentation as part of pipeline configuration."""
    print("\n🔧 Presentation Pipeline Ideas")
    print("=" * 50)
    
    # Idea 1: Pipeline with default presentation
    pdf_to_markdown = PresentationPipeline(
        loader_pipeline=load.pdf,
        presentation='markdown'
    )
    
    # Idea 2: Composable presentation pipeline
    print("\nIdea 1: Pipeline with default presentation")
    print("   pdf_to_markdown = PresentationPipeline(load.pdf, 'markdown')")
    print("   result = pdf_to_markdown('doc.pdf')  # Uses markdown")
    print("   result = pdf_to_markdown('doc.pdf[present:xml]')  # Override to XML")
    
    # Idea 3: Presentation as pipeline step
    print("\nIdea 2: Presentation as explicit pipeline step")
    print("   pipeline = load.pdf | modify.pages | present.markdown")
    print("   But this breaks the Attachment flow...")
    
    # Idea 4: Wrapped presenter that preserves Attachment
    print("\nIdea 3: Smart presenter that preserves Attachment wrapper")
    print("   pipeline = load.pdf | modify.pages | present_as('markdown')")
    print("   Where present_as returns an Attachment with presented content")


def demo_complete_pipeline_to_llm():
    """Demo complete pipeline from file to LLM."""
    print("\n🤖 Complete Pipeline to LLM")
    print("=" * 50)
    
    # The ideal pipeline flow
    print("Ideal flow:")
    print("1. Load: file.pdf → Attachment(PdfReader)")
    print("2. Modify: → Attachment(PdfReader[selected pages])")  
    print("3. Present: → Attachment('extracted text')")
    print("4. Adapt: → {'role': 'user', 'content': [...]}  # EXIT POINT")
    print("\nAfter adapt, we've left the Attachment world!")
    
    # Example implementation
    class SmartPipeline:
        def __init__(self, steps):
            self.steps = steps
            
        def __call__(self, source: str, adapt_to: Optional[str] = None, prompt: str = ""):
            # Process through steps
            result = source
            for step in self.steps:
                result = step(result)
            
            # If adapt specified, this is our exit point
            if adapt_to == 'openai':
                return adapt.openai_chat(result, prompt)
            elif adapt_to == 'claude':
                return adapt.claude(result, prompt)
            else:
                return result
    
    # Usage
    print("\nExample usage:")
    print("pipeline = SmartPipeline([load.pdf, modify.pages, present.text])")
    print("att = pipeline('doc.pdf')  # Returns Attachment")
    print("msg = pipeline('doc.pdf', adapt_to='openai', prompt='Summarize')  # Returns OpenAI format")


def demo_multi_format_presentation():
    """Demo handling multiple presentation formats in one pipeline."""
    print("\n🎨 Multi-Format Presentation")
    print("=" * 50)
    
    # Idea: Compound presentation commands
    ideas = [
        "doc.pdf[present_text:markdown,present_images:tiles]",
        "slides.pptx[text:xml,images:2x2]",
        "report.pdf[extract:text+images,format:markdown]",
    ]
    
    print("Compound presentation ideas:")
    for idea in ideas:
        path, commands = parse_path_expression(idea)
        print(f"\n{idea}")
        print(f"   Commands: {commands}")
    
    # How this might work
    print("\nImplementation idea:")
    print("- Presenters could return compound results")
    print("- Attachment.content could be a dict: {'text': '...', 'images': [...]}")
    print("- Adapters would know how to handle compound content")


def main():
    """Run all demos."""
    print("🚀 Adapter & Pipeline Vision Demo")
    print("=" * 50)
    
    # Scientific method
    print("\n📋 Hypotheses:")
    print("1. Adapters should handle both Attachment and Attachments")
    print("2. Adapters are the 'exit point' from attachment world")
    print("3. Presentation needs to be specifiable in pipelines")
    print("4. DSL can guide presentation choices")
    
    # Run demos
    demo_adapter_overloading()
    demo_presentation_in_dsl()
    demo_presentation_pipeline()
    demo_complete_pipeline_to_llm()
    demo_multi_format_presentation()
    
    # Conclusions
    print("\n📊 Findings & Recommendations:")
    print("1. ✅ Adapter overloading makes sense - different behavior for 1 vs many")
    print("2. ✅ Adapters as 'exit points' is the right mental model")
    print("3. 💡 Best presentation approach: DSL commands + smart pipelines")
    print("4. 💡 Consider: present_as() modifier that preserves Attachment wrapper")
    print("5. 🔮 Future: Compound content types for multi-format presentation")


if __name__ == "__main__":
    main() 