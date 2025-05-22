#!/usr/bin/env python3
"""Debug loader composition issue."""

from attachments.core import load, Attachment


def debug_single_loader():
    """Debug single loader behavior."""
    print("🔍 Debugging Single Loader")
    print("=" * 50)
    
    # Test PDF loader directly
    print("\nTesting load.pdf('examples/sample.pdf'):")
    try:
        att = load.pdf("examples/sample.pdf")
        print(f"  Result type: {type(att)}")
        print(f"  Content type: {type(att.content)}")
        print(f"  Content is None: {att.content is None}")
        print(f"  Has content: {att.content is not None}")
    except Exception as e:
        print(f"  Error: {e}")
        import traceback
        traceback.print_exc()


def debug_loader_matching():
    """Debug loader matching behavior."""
    print("\n\n🔍 Debugging Loader Matching")
    print("=" * 50)
    
    # Check if loaders have matcher functions
    print("\nLoader attributes:")
    for name in ['pdf', 'pptx', 'image']:
        loader = getattr(load, name, None)
        if loader:
            print(f"\nload.{name}:")
            print(f"  Type: {type(loader)}")
            print(f"  Has __call__: {hasattr(loader, '__call__')}")
            print(f"  Has matcher_func: {hasattr(loader, 'matcher_func')}")
            if hasattr(loader, 'matcher_func'):
                # Test matcher
                print(f"  matcher('sample.pdf'): {loader.matcher_func('sample.pdf')}")
                print(f"  matcher('sample.png'): {loader.matcher_func('sample.png')}")


def debug_composed_loader():
    """Debug composed loader step by step."""
    print("\n\n🔍 Debugging Composed Loader")
    print("=" * 50)
    
    # Create simple composition
    print("\nCreating: pdf_or_image = load.pdf | load.image")
    pdf_or_image = load.pdf | load.image
    print(f"  Type: {type(pdf_or_image)}")
    print(f"  Name: {pdf_or_image.__name__}")
    
    # Test on PDF
    print("\nTesting pdf_or_image('examples/sample.pdf'):")
    try:
        # Add debug wrapper
        original_pdf = load.pdf.__call__
        def debug_pdf_call(path):
            print(f"    [DEBUG] pdf.__call__ called with: {path}")
            result = original_pdf(path)
            print(f"    [DEBUG] pdf.__call__ returned: {type(result)}, content={type(result.content) if hasattr(result, 'content') else 'N/A'}")
            return result
        
        load.pdf.__call__ = debug_pdf_call
        
        att = pdf_or_image("examples/sample.pdf")
        print(f"  Final result type: {type(att)}")
        print(f"  Final content type: {type(att.content) if hasattr(att, 'content') else 'No content attr'}")
        
    except Exception as e:
        print(f"  Error: {e}")
        import traceback
        traceback.print_exc()


def main():
    """Run debugging."""
    print("🐛 Loader Composition Debug")
    print("=" * 50)
    
    debug_single_loader()
    debug_loader_matching()
    debug_composed_loader()


if __name__ == "__main__":
    main() 