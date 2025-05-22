#!/usr/bin/env python3
"""
Demo: Idiomatic Pipeline Usage

Showing how the existing architecture already supports everything we need!
Presenters already preserve Attachment wrappers.
"""

from typing import Callable, Any
from attachments.core import Attachment, load, modify, present, adapt
from attachments.utils.parsing import parse_path_expression


def demo_presenters_preserve_attachments():
    """Show that presenters already work perfectly in pipelines."""
    print("🎯 Presenters Already Preserve Attachments!")
    print("=" * 50)
    
    # Load a PDF
    att = load.pdf("examples/sample.pdf")
    print(f"\n1. Loaded: {type(att).__name__} with content type: {type(att.content).__name__}")
    
    # Apply pages modifier
    att = modify.pages(att, "1-2")
    print(f"2. Modified: {type(att).__name__} with content type: {type(att.content).__name__}")
    
    # Apply text presenter - IT RETURNS AN ATTACHMENT!
    text_att = present.text(att)
    print(f"3. Presented as text: {type(text_att).__name__} with content type: {type(text_att.content).__name__}")
    print(f"   Content preview: {text_att.content[:50]}...")
    
    # We can continue the pipeline!
    # Apply adapter as exit point
    openai_msg = adapt.openai_chat(text_att, "Summarize")
    print(f"4. Adapted (exit): {type(openai_msg).__name__}")


def demo_pipeline_with_presenters():
    """Demo clean pipeline using presenters."""
    print("\n\n🔗 Pipeline with Presenters")
    print("=" * 50)
    
    # Simple pipeline - presenters work!
    pipeline = lambda source: (
        load.pdf(source) | 
        modify.pages | 
        present.text
    )
    
    result = pipeline("examples/sample.pdf[pages:1-3]")
    print(f"\nPipeline result: {type(result).__name__}")
    print(f"Content type: {type(result.content).__name__}")
    print(f"Content length: {len(result.content)} chars")


def demo_dynamic_presenter_selection():
    """Demo selecting presenter based on DSL."""
    print("\n\n🎨 Dynamic Presenter Selection")
    print("=" * 50)
    
    def smart_pipeline(source: str) -> Any:
        """Pipeline that respects DSL presentation commands."""
        path, commands = parse_path_expression(source)
        
        # Load
        if path.endswith('.pdf'):
            att = load.pdf(source)
        elif path.endswith('.pptx'):
            att = load.pptx(source)
        else:
            att = load.image(source)
        
        # Modify
        if 'pages' in commands:
            att = modify.pages(att)
        
        # Present based on DSL
        presentation = commands.get('present', 'text')
        if presentation == 'markdown':
            att = present.markdown(att)
        elif presentation == 'xml':
            att = present.xml(att)
        elif presentation == 'images':
            att = present.images(att)
        else:
            att = present.text(att)
        
        return att
    
    # Test different presentations
    test_cases = [
        "examples/sample.pdf[present:text]",
        "examples/sample.pdf[present:markdown]",
        "examples/sample.pptx[pages:1-2,present:xml]",
    ]
    
    for test in test_cases:
        try:
            result = smart_pipeline(test)
            print(f"\n{test}")
            print(f"   Result: {type(result).__name__} → {type(result.content).__name__}")
            if isinstance(result.content, str):
                print(f"   Preview: {result.content[:80].replace(chr(10), ' ')}...")
        except Exception as e:
            print(f"\n{test}")
            print(f"   Error: {e}")


def demo_composable_loader_pipelines():
    """Demo how loaders can be composed with |."""
    print("\n\n🔧 Composable Loader Pipelines")
    print("=" * 50)
    
    # The missing piece: make loaders composable!
    class ComposableLoader:
        def __init__(self, loaders):
            self.loaders = loaders
        
        def __call__(self, source: str) -> Attachment:
            for loader in self.loaders:
                try:
                    att = loader(source)
                    if att and att.content is not None:
                        return att
                except:
                    continue
            raise ValueError(f"No loader could handle: {source}")
        
        def __or__(self, other):
            if isinstance(other, ComposableLoader):
                return ComposableLoader(self.loaders + other.loaders)
            else:
                return ComposableLoader(self.loaders + [other])
    
    # Create universal loader
    universal = ComposableLoader([load.pdf]) | ComposableLoader([load.pptx]) | ComposableLoader([load.image])
    
    print("\nUniversal loader created with: load.pdf | load.pptx | load.image")
    
    # Test it
    for file in ["examples/sample.pdf", "examples/sample.pptx", "sample.png"]:
        try:
            att = universal(file)
            print(f"✅ {file} → {type(att.content).__name__}")
        except Exception as e:
            print(f"❌ {file} → {e}")


def demo_complete_idiomatic_pipeline():
    """Demo the complete idiomatic approach."""
    print("\n\n🚀 Complete Idiomatic Pipeline")
    print("=" * 50)
    
    class IdiomaticPipeline:
        """A truly idiomatic pipeline using our architecture."""
        
        def __init__(self):
            # Compose loaders
            self.loader = self._create_universal_loader()
        
        def _create_universal_loader(self):
            """Create a universal loader by composing all loaders."""
            # In reality, we'd enhance the loader decorator to support |
            # For now, we'll use a simple approach
            def universal(source: str) -> Attachment:
                loaders = [load.pdf, load.pptx, load.csv, load.image]
                for loader in loaders:
                    try:
                        att = loader(source)
                        if att and att.content is not None:
                            return att
                    except:
                        continue
                raise ValueError(f"No loader for: {source}")
            return universal
        
        def __call__(self, source: str) -> Any:
            """Process source through the pipeline."""
            path, commands = parse_path_expression(source)
            
            # Load
            att = self.loader(source)
            
            # Modify based on commands
            if 'pages' in commands:
                att = modify.pages(att)
            
            if 'tile' in commands:
                att = modify.tile(att)
            
            # Present based on command or default
            presentation = commands.get('present', 'text')
            presenter_map = {
                'text': present.text,
                'markdown': present.markdown,
                'xml': present.xml,
                'images': present.images,
            }
            
            if presentation in presenter_map:
                att = presenter_map[presentation](att)
            
            # Adapt if specified (exit point)
            if 'adapt' in commands:
                adapter = commands['adapt']
                prompt = commands.get('prompt', '')
                
                if adapter == 'openai':
                    return adapt.openai_chat(att, prompt)
                elif adapter == 'claude':
                    # Would use adapt.claude
                    return f"Would adapt to Claude with prompt: {prompt}"
            
            return att
    
    # Create and test pipeline
    pipeline = IdiomaticPipeline()
    
    test_cases = [
        "examples/sample.pdf[pages:1-2,present:text]",
        "examples/sample.pdf[present:markdown,adapt:openai,prompt:Summarize this]",
        "examples/sample.pptx[pages:1-3,present:xml]",
    ]
    
    for test in test_cases:
        print(f"\n{test}")
        try:
            result = pipeline(test)
            if isinstance(result, Attachment):
                print(f"   → Attachment with {type(result.content).__name__}")
            else:
                print(f"   → {type(result).__name__} (exited attachment world)")
        except Exception as e:
            print(f"   → Error: {e}")


def main():
    """Run all demos."""
    print("🎯 Idiomatic Pipeline Architecture Demo")
    print("=" * 50)
    
    # Key insights
    print("\n📋 Key Insights:")
    print("1. Presenters ALREADY preserve Attachment wrappers!")
    print("2. We can chain: load → modify → present → adapt")
    print("3. DSL commands guide the pipeline behavior")
    print("4. Adapters are the exit point from Attachment world")
    
    # Run demos
    demo_presenters_preserve_attachments()
    demo_pipeline_with_presenters()
    demo_dynamic_presenter_selection()
    demo_composable_loader_pipelines()
    demo_complete_idiomatic_pipeline()
    
    # Recommendations
    print("\n\n📊 Recommendations:")
    print("1. ✅ Presenters work great as-is!")
    print("2. 💡 Make loaders support | operator for composition")
    print("3. 💡 Update Attachments class to use universal loader")
    print("4. 💡 Add helper function for DSL-aware pipelines")
    print("5. ✅ Architecture is already very powerful!")


if __name__ == "__main__":
    main() 