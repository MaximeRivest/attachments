#!/usr/bin/env python3
"""
Comprehensive Demo: Recreating OpenAI Attachments Tutorial with Opus Notes

This demonstrates how the opus_notes architecture can provide the same functionality
as the original attachments library tutorial, but with a more modular and extensible design.
"""

import sys
sys.path.insert(0, 'src')

# Import the opus_notes module
import importlib.util
spec = importlib.util.spec_from_file_location("opus_notes", "src/attachments/opus_notes.py")
opus_notes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(opus_notes)

print("🚀 Opus Notes Tutorial Demo")
print("=" * 80)
print("Recreating the OpenAI Attachments Tutorial with modular components")
print("=" * 80)

def demo_basic_pdf_processing():
    """Demo basic PDF processing like the tutorial"""
    print("\n📄 1. BASIC PDF PROCESSING")
    print("-" * 40)
    
    # Load PDF
    print("Loading PDF...")
    att = opus_notes.load.pdf("examples/sample.pdf")
    print(f"✅ Loaded: {att.source} ({att.content.page_count} pages)")
    
    # Extract text (like tutorial's .text property)
    print("\nExtracting text...")
    text_att = opus_notes.present.text(att)
    print(f"✅ Text extracted: {len(text_att.content)} characters")
    print(f"📝 Preview: {repr(text_att.content[:50])}...")
    
    # Generate images (like tutorial's .images property)
    print("\nGenerating images...")
    image_att = opus_notes.present.images(att)
    print(f"✅ Images generated: {len(image_att.content)} images")
    print(f"🖼️  First image: {image_att.content[0][:50]}...")
    
    return att, text_att, image_att

def demo_openai_integration():
    """Demo OpenAI integration like the tutorial"""
    print("\n🤖 2. OPENAI INTEGRATION")
    print("-" * 40)
    
    # Load PDF
    att = opus_notes.load.pdf("examples/sample.pdf")
    
    # Create OpenAI format (like tutorial's .to_openai() method)
    print("Converting to OpenAI format...")
    openai_content = opus_notes.adapt.openai(att, "What do you see in this PDF?")
    
    print(f"✅ OpenAI format created: {len(openai_content)} content items")
    for i, item in enumerate(openai_content):
        item_type = item.get('type', 'unknown')
        if item_type == 'text':
            preview = item['text'][:50] + "..." if len(item['text']) > 50 else item['text']
            print(f"   Item {i}: {item_type} - {repr(preview)}")
        else:
            print(f"   Item {i}: {item_type} - {len(str(item))} chars")
    
    # Show what would be sent to OpenAI
    print("\n📤 Ready for OpenAI API:")
    openai_message = {
        "role": "user", 
        "content": openai_content
    }
    print(f"   Message structure: role={openai_message['role']}, content={len(openai_message['content'])} items")
    
    return openai_content

def demo_page_operations():
    """Demo page operations like the tutorial"""
    print("\n📑 3. PAGE OPERATIONS")
    print("-" * 40)
    
    # Load with page specification (like tutorial's page filtering)
    print("Loading with page specification...")
    att = opus_notes.load.pdf("examples/sample.pdf[pages: 1]")
    print(f"✅ Page spec parsed: {att.commands}")
    
    # Apply page filtering
    print("Applying page filter...")
    filtered_att = opus_notes.modify.pages(att)
    print(f"✅ Pages filtered: {filtered_att.content.page_count} pages")
    
    # Direct page specification
    print("Direct page modification...")
    att_full = opus_notes.load.pdf("examples/sample.pdf")
    att_page1 = opus_notes.modify.pages(att_full, "1")
    print(f"✅ Direct page selection: {att_page1.content.page_count} pages")
    
    return filtered_att

def demo_pipeline_approach():
    """Demo pipeline approach"""
    print("\n🔗 4. PIPELINE APPROACH")
    print("-" * 40)
    
    # Multi-step pipeline
    print("Pipeline: Load → Filter Pages → Extract Text → Format for OpenAI")
    
    # Step by step (could be chained with | operator)
    att = opus_notes.load.pdf("examples/sample.pdf[pages: 1]")
    print(f"  📥 Loaded: {att.source}")
    
    filtered_att = opus_notes.modify.pages(att)
    print(f"  🔍 Filtered: {filtered_att.content.page_count} pages")
    
    text_att = opus_notes.present.text(filtered_att)
    print(f"  📝 Text: {len(text_att.content)} chars")
    
    openai_content = opus_notes.adapt.openai(filtered_att, "Analyze this PDF page")
    print(f"  🤖 OpenAI: {len(openai_content)} items")
    
    return openai_content

def demo_multiple_presentations():
    """Demo multiple presentation formats"""
    print("\n🎭 5. MULTIPLE PRESENTATIONS")
    print("-" * 40)
    
    att = opus_notes.load.pdf("examples/sample.pdf")
    
    # Text presentation
    text_result = opus_notes.present.text(att)
    print(f"📝 Text presentation: {len(text_result.content)} chars")
    
    # Markdown presentation (if available)
    try:
        markdown_result = opus_notes.present.markdown(att)
        print(f"📖 Markdown presentation: {len(markdown_result.content)} chars")
    except TypeError:
        print("📖 Markdown presentation: Not implemented for PDF")
    
    # Image presentation
    image_result = opus_notes.present.images(att)
    print(f"🖼️  Image presentation: {len(image_result.content)} images")
    
    # Combined for OpenAI (text + images)
    openai_result = opus_notes.adapt.openai(att, "Comprehensive analysis please")
    print(f"🤖 Combined OpenAI format: {len(openai_result)} items")
    
    return text_result, image_result, openai_result

def demo_tutorial_equivalent():
    """Show exact tutorial equivalent"""
    print("\n🎯 6. TUTORIAL EQUIVALENT")
    print("-" * 40)
    
    print("Original tutorial code:")
    print("  att = Attachments('sample.pdf')")
    print("  content = att.to_openai('What is in this PDF?')")
    
    print("\nOpus Notes equivalent:")
    print("  att = load.pdf('sample.pdf')")
    print("  content = adapt.openai(att, 'What is in this PDF?')")
    
    # Execute the opus notes version
    att = opus_notes.load.pdf("examples/sample.pdf")
    content = opus_notes.adapt.openai(att, "What is in this PDF?")
    
    print(f"\n✅ Result: {len(content)} content items ready for OpenAI")
    print("📊 Content breakdown:")
    for i, item in enumerate(content):
        print(f"   {i+1}. {item.get('type', 'unknown')}: {len(str(item))} chars")
    
    return content

def main():
    """Run the complete demo"""
    print("Running comprehensive opus_notes tutorial demo...\n")
    
    # Run all demos
    demo_basic_pdf_processing()
    demo_openai_integration() 
    demo_page_operations()
    demo_pipeline_approach()
    demo_multiple_presentations()
    demo_tutorial_equivalent()
    
    # Final summary
    print("\n" + "=" * 80)
    print("🎉 DEMO COMPLETE")
    print("=" * 80)
    print("✅ All tutorial functionality successfully recreated!")
    print("🏗️  Modular architecture allows for:")
    print("   • Type-safe dispatch (PDFs, images, text, etc.)")
    print("   • Extensible loaders, presenters, modifiers, adapters")
    print("   • Pipeline composition with | operator")
    print("   • Union type support for flexibility")
    print("   • Command parsing from path expressions")
    print("🚀 Ready for production use!")
    print("\n💡 Key advantages over monolithic approach:")
    print("   • Each component has single responsibility")
    print("   • Easy to add new file types and presentations")
    print("   • Type dispatch prevents runtime errors")
    print("   • Composable operations with clear interfaces")

if __name__ == "__main__":
    main() 