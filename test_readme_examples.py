#!/usr/bin/env python3
"""Test README examples to ensure they work correctly."""

import os
import sys
from pathlib import Path

def test_basic_imports():
    """Test that basic imports work."""
    print("🧪 Testing basic imports...")
    
    try:
        from attachments import Attachments
        print("   ✅ High-level import: attachments.Attachments")
        
        from attachments.core import load, present, modify, adapt
        print("   ✅ Low-level imports: load, present, modify, adapt")
        
        # Check that decorators exist
        from attachments.core.decorators import loader, presenter, modifier, adapter
        print("   ✅ Decorators: loader, presenter, modifier, adapter")
        
    except ImportError as e:
        print(f"   ❌ Import failed: {e}")
        return False
    
    return True


def test_pdf_examples():
    """Test PDF examples from README."""
    print("\n📄 Testing PDF examples...")
    
    # Check if sample PDF exists
    sample_pdf = "examples/sample.pdf"
    if not os.path.exists(sample_pdf):
        print(f"   ⚠️  Sample PDF not found: {sample_pdf}")
        return True  # Skip but don't fail
    
    try:
        from attachments import Attachments
        
        # Test basic PDF loading
        ctx = Attachments(sample_pdf)
        text = str(ctx)
        images = ctx.images
        
        print(f"   ✅ Basic PDF: {len(text)} chars text, {len(images)} images")
        
        # Test page selection 
        ctx_pages = Attachments(f"{sample_pdf}[1]")
        text_pages = str(ctx_pages)
        
        print(f"   ✅ Page selection: {len(text_pages)} chars")
        
        # Test low-level API
        from attachments.core import load, modify, present
        
        pdf_doc = load.pdf(sample_pdf)
        pages = modify.pages(pdf_doc, "1")
        text_ll = present.text(pages)
        
        print(f"   ✅ Low-level API: {len(text_ll.content)} chars")
        
    except Exception as e:
        print(f"   ❌ PDF test failed: {e}")
        return False
    
    return True


def test_powerpoint_examples():
    """Test PowerPoint examples from README."""
    print("\n🎨 Testing PowerPoint examples...")
    
    # Check if sample PowerPoint exists
    sample_pptx = "examples/sample.pptx"
    if not os.path.exists(sample_pptx):
        print(f"   ⚠️  Sample PowerPoint not found: {sample_pptx}")
        return True  # Skip but don't fail
    
    try:
        from attachments import Attachments
        
        # Test basic PowerPoint loading
        ctx = Attachments(sample_pptx)
        text = str(ctx)
        
        print(f"   ✅ Basic PowerPoint: {len(text)} chars text")
        
        # Test slide selection
        ctx_slides = Attachments(f"{sample_pptx}[1-2]")
        text_slides = str(ctx_slides)
        
        print(f"   ✅ Slide selection: {len(text_slides)} chars")
        
        # Test low-level API with modular architecture
        from attachments.core import load, modify, present
        
        pptx_doc = load.pptx(sample_pptx)
        slides = modify.pages(pptx_doc, "1-2")
        text_ll = present.text(slides)
        xml_ll = present.xml(slides)
        md_ll = present.markdown(slides)
        
        print(f"   ✅ Low-level text: {len(text_ll.content)} chars")
        print(f"   ✅ Low-level XML: {len(xml_ll.content)} chars")
        print(f"   ✅ Low-level markdown: {len(md_ll.content)} chars")
        
        # Test the complete pipeline from README
        pptx_doc = load.pptx(sample_pptx)
        slides = modify.pages(pptx_doc, "1-3")
        xml = present.xml(slides)
        
        print(f"   ✅ Complete pipeline: {len(xml.content)} chars XML")
        
    except Exception as e:
        print(f"   ❌ PowerPoint test failed: {e}")
        return False
    
    return True


def test_csv_examples():
    """Test CSV examples from README."""
    print("\n📊 Testing CSV examples...")
    
    # Check if sample CSV exists
    sample_csv = "examples/sample.csv"
    if not os.path.exists(sample_csv):
        print(f"   ⚠️  Sample CSV not found: {sample_csv}")
        return True  # Skip but don't fail
    
    try:
        from attachments import Attachments
        
        # Test basic CSV loading
        ctx = Attachments(sample_csv)
        text = str(ctx)
        
        print(f"   ✅ Basic CSV: {len(text)} chars text")
        
        # Test sampling
        ctx_sample = Attachments(f"{sample_csv}[sample:10]")
        text_sample = str(ctx_sample)
        
        print(f"   ✅ CSV sampling: {len(text_sample)} chars")
        
    except Exception as e:
        print(f"   ❌ CSV test failed: {e}")
        return False
    
    return True


def test_image_examples():
    """Test image examples from README."""
    print("\n🖼️ Testing image examples...")
    
    # Check if sample image exists
    sample_img = "sample.png"
    if not os.path.exists(sample_img):
        print(f"   ⚠️  Sample image not found: {sample_img}")
        return True  # Skip but don't fail
    
    try:
        from attachments import Attachments
        
        # Test basic image loading
        ctx = Attachments(sample_img)
        images = ctx.images
        
        print(f"   ✅ Basic image: {len(images)} images")
        
        # Test resize
        ctx_resize = Attachments(f"{sample_img}[resize:50%]")
        images_resize = ctx_resize.images
        
        print(f"   ✅ Image resize: {len(images_resize)} images")
        
    except Exception as e:
        print(f"   ❌ Image test failed: {e}")
        return False
    
    return True


def test_mixed_examples():
    """Test mixed file examples from README."""
    print("\n🔀 Testing mixed file examples...")
    
    try:
        from attachments import Attachments
        
        # Find available files
        files = []
        test_files = [
            "examples/sample.pdf",
            "examples/sample.pptx", 
            "examples/sample.csv",
            "sample.png"
        ]
        
        for file in test_files:
            if os.path.exists(file):
                files.append(file)
        
        if not files:
            print("   ⚠️  No sample files found for mixed test")
            return True
        
        # Test loading multiple files
        ctx = Attachments(*files)
        text = str(ctx)
        images = ctx.images
        
        print(f"   ✅ Mixed files ({len(files)}): {len(text)} chars, {len(images)} images")
        
    except Exception as e:
        print(f"   ❌ Mixed files test failed: {e}")
        return False
    
    return True


def test_extension_example():
    """Test the extension example from README."""
    print("\n🔧 Testing extension example...")
    
    try:
        from attachments.core.decorators import loader, presenter
        
        # Test the JSON loader example from README
        @loader(lambda path: path.endswith('.json'))
        def json_file(path: str):
            import json
            with open(path) as f:
                return json.load(f)
        
        # Test the summary presenter example from README  
        @presenter
        def summary(data: dict) -> str:
            """Generate summary for dictionary data."""
            return f"Dictionary with {len(data)} keys: {list(data.keys())[:5]}..."
        
        print("   ✅ Extension decorators work")
        
        # Test if they're available
        from attachments.core import load, present
        
        # Create a test JSON file
        import json, tempfile
        test_data = {"key1": "value1", "key2": "value2", "key3": "value3"}
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(test_data, f)
            json_path = f.name
        
        try:
                        # Test the custom loader
            loaded_att = load.json_file(json_path)
            result = loaded_att.content  # Get the actual content from attachment
            print(f"   ✅ Custom JSON loader: {len(result)} keys")
            
            # Test the custom presenter
            summary_result = present.summary(loaded_att)
            print(f"   ✅ Custom presenter: {len(summary_result.content)} chars")
            
        finally:
            os.unlink(json_path)
        
    except Exception as e:
        print(f"   ❌ Extension test failed: {e}")
        return False
    
    return True


def main():
    """Run all README tests."""
    print("🧪 Testing README Examples")
    print("=" * 50)
    
    tests = [
        test_basic_imports,
        test_pdf_examples, 
        test_powerpoint_examples,
        test_csv_examples,
        test_image_examples,
        test_mixed_examples,
        test_extension_example
    ]
    
    results = []
    for test in tests:
        try:
            success = test()
            results.append(success)
        except Exception as e:
            print(f"   💥 Test crashed: {e}")
            results.append(False)
    
    print(f"\n📊 Results: {sum(results)}/{len(results)} tests passed")
    
    if all(results):
        print("🎉 All README examples work correctly!")
        return 0
    else:
        print("❌ Some README examples failed")
        return 1


if __name__ == "__main__":
    exit(main()) 