#!/usr/bin/env python3
"""
Demo: Complete Modular Architecture

Showing how all the pieces fit together:
- Loaders create Attachments
- Modifiers transform Attachments  
- Presenters change content format (preserve Attachment)
- Adapters exit to LLM formats
"""

from attachments import Attachments
from attachments.core import load, modify, present, adapt
from attachments.utils.parsing import parse_path_expression


def demo_complete_pipeline():
    """Demo the complete pipeline flow."""
    print("🚀 Complete Pipeline Flow")
    print("=" * 50)
    
    source = "examples/sample.pdf[pages:1-2]"
    
    # Step 1: Load (creates Attachment)
    print(f"\n1. Loading: {source}")
    att = load.pdf(source)
    print(f"   → {type(att).__name__} with {type(att.content).__name__}")
    
    # Step 2: Modify (transforms Attachment)
    print("\n2. Modifying: select pages")
    att = modify.pages(att)  # Uses commands from source
    print(f"   → {type(att).__name__} with {type(att.content).__name__}")
    
    # Step 3: Present (changes content, preserves Attachment)
    print("\n3. Presenting: as text")
    att = present.text(att)
    print(f"   → {type(att).__name__} with {type(att.content).__name__}")
    print(f"   Content preview: {att.content[:50]}...")
    
    # Step 4: Adapt (EXIT POINT - returns LLM format)
    print("\n4. Adapting: to OpenAI format")
    openai_msg = adapt.openai_chat(att, "Summarize this document")
    print(f"   → {type(openai_msg).__name__} (LEFT ATTACHMENT WORLD)")
    print(f"   Message structure: {list(openai_msg[0].keys())}")


def demo_adapter_overloading():
    """Demo how adapters handle single vs multiple attachments."""
    print("\n\n🔄 Adapter Overloading")
    print("=" * 50)
    
    # Single attachment - use adapter directly
    print("\n1. Single Attachment:")
    ctx = Attachments("examples/sample.pdf[pages:1]")
    openai_msg = ctx.to_openai("Summarize")
    print(f"   Attachments count: {len(ctx)}")
    print(f"   → to_openai() uses adapt.openai_chat() directly")
    print(f"   Result: {len(openai_msg)} message(s)")
    
    # Multiple attachments - squashing operation
    print("\n2. Multiple Attachments:")
    ctx = Attachments("examples/sample.pdf", "sample.png")
    openai_msg = ctx.to_openai("Compare these files")
    print(f"   Attachments count: {len(ctx)}")
    print(f"   → to_openai() squashes all content together")
    print(f"   Result: {len(openai_msg)} message(s) with {len(openai_msg[0]['content'])} content items")


def demo_presentation_in_pipelines():
    """Demo how to specify presentation in pipelines."""
    print("\n\n🎨 Presentation in Pipelines")
    print("=" * 50)
    
    # Method 1: Direct presenter call
    print("\n1. Direct presenter call:")
    att = load.pdf("examples/sample.pdf") | modify.pages("1") | present.text
    print(f"   load | modify | present.text → {type(att.content).__name__}")
    
    # Method 2: DSL-driven presentation
    print("\n2. DSL-driven presentation:")
    sources = [
        "examples/sample.pdf[present:text]",
        "examples/sample.pptx[pages:1-2,present:xml]",
    ]
    
    for source in sources:
        path, commands = parse_path_expression(source)
        presentation = commands.get('present', 'text')
        print(f"\n   {source}")
        print(f"   → Presentation: {presentation}")


def demo_type_based_dispatch():
    """Demo how type-based dispatch works."""
    print("\n\n🎯 Type-Based Dispatch") 
    print("=" * 50)
    
    # Different content types use different presenters
    files = [
        ("examples/sample.pdf", "PdfReader → text presenter"),
        ("examples/sample.pptx", "Presentation → text presenter"),
        ("sample.png", "PngImageFile → text presenter"),
    ]
    
    for file, desc in files:
        try:
            att = load.pdf(file) if file.endswith('.pdf') else (
                load.pptx(file) if file.endswith('.pptx') else 
                load.image(file)
            )
            text_att = present.text(att)
            print(f"\n{file}:")
            print(f"   {desc}")
            print(f"   Result length: {len(text_att.content)} chars")
        except Exception as e:
            print(f"\n{file}:")
            print(f"   Error: {e}")


def demo_universal_pipeline():
    """Demo a universal pipeline that handles everything."""
    print("\n\n🌐 Universal Pipeline")
    print("=" * 50)
    
    def universal_pipeline(source: str) -> dict:
        """
        A universal pipeline that:
        1. Loads any file type
        2. Applies modifiers from DSL
        3. Presents based on DSL
        4. Adapts if requested
        """
        path, commands = parse_path_expression(source)
        
        # Universal loader (simplified - in reality would compose with |)
        loaders = [
            (lambda p: p.endswith('.pdf'), load.pdf),
            (lambda p: p.endswith('.pptx'), load.pptx),
            (lambda p: p.endswith('.csv'), load.csv),
            (lambda p: True, load.image),  # Fallback
        ]
        
        att = None
        for matcher, loader in loaders:
            if matcher(path):
                try:
                    att = loader(source)
                    break
                except:
                    continue
        
        if not att:
            raise ValueError(f"No loader for: {path}")
        
        # Apply modifiers
        if 'pages' in commands:
            att = modify.pages(att)
        
        # Apply presentation
        presentation = commands.get('present', 'text')
        if presentation == 'markdown' and hasattr(present, 'markdown'):
            att = getattr(present, 'markdown')(att)
        elif presentation == 'xml' and hasattr(present, 'xml'):
            att = getattr(present, 'xml')(att)
        elif presentation == 'images' and hasattr(present, 'images'):
            att = getattr(present, 'images')(att)
        else:
            att = present.text(att)
        
        # Adapt if requested (EXIT POINT)
        if 'adapt' in commands:
            adapter_name = commands['adapt']
            prompt = commands.get('prompt', '')
            
            if adapter_name == 'openai':
                return {'type': 'adapted', 'content': adapt.openai_chat(att, prompt)}
            elif adapter_name == 'claude':
                return {'type': 'adapted', 'content': adapt.claude(att, prompt)}
        
        return {'type': 'attachment', 'content': att}
    
    # Test the universal pipeline
    test_cases = [
        "examples/sample.pdf[pages:1-2,present:text]",
        "examples/sample.pdf[present:text,adapt:openai,prompt:Summarize]",
    ]
    
    for test in test_cases:
        print(f"\n{test}")
        try:
            result = universal_pipeline(test)
            print(f"   → {result['type']}")
            if result['type'] == 'attachment':
                print(f"     Content type: {type(result['content'].content).__name__}")
            else:
                print(f"     Ready for LLM: {type(result['content']).__name__}")
        except Exception as e:
            print(f"   → Error: {e}")


def main():
    """Run all demos."""
    print("🏗️ Modular Architecture Demo")
    print("=" * 50)
    
    # Architecture summary
    print("\n📋 Architecture Summary:")
    print("1. Loaders: Create Attachments from files")
    print("2. Modifiers: Transform Attachments (preserve wrapper)")
    print("3. Presenters: Change content format (preserve wrapper)")
    print("4. Adapters: Exit to LLM formats (NO wrapper)")
    
    # Run demos
    demo_complete_pipeline()
    demo_adapter_overloading()
    demo_presentation_in_pipelines()
    demo_type_based_dispatch()
    demo_universal_pipeline()
    
    # Final thoughts
    print("\n\n📊 Key Takeaways:")
    print("1. ✅ The architecture is already very clean!")
    print("2. ✅ Presenters preserve Attachments for pipeline flow")
    print("3. ✅ Adapters are the exit point from attachment world")
    print("4. ✅ DSL commands guide pipeline behavior") 
    print("5. 💡 Next: Make loaders composable with | operator")


if __name__ == "__main__":
    main() 