#!/usr/bin/env python3
"""
Demo: Elegant Auto-Parameter Discovery Solution

Shows how we solved the architectural violation with maximum elegance:

BEFORE (violated type contract):
  modifier.resize(PdfReader) → List[Image]  ❌ Type mismatch!

BEFORE (verbose DSL):
  file.pdf[present.images.resize:50%]       ❌ Too verbose!

AFTER (elegant + auto-discovery):
  file.pdf[resize:50%]                      ✅ Clean & simple!
  
Architecture:
- Loaders: File → Native Type  
- Modifiers: Type → Same Type (preserve contract)
- Presenters: Type → Presentation (auto-extract params from commands)
- Adapters: Presentation → API Format

The magic: decorated functions automatically receive parameters 
from DSL commands that match their signature!
"""

import sys
from pathlib import Path

# Add the src directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def demo_elegant_solution():
    """Show the new elegant auto-parameter discovery."""
    
    print("🎯 ELEGANT AUTO-PARAMETER DISCOVERY")
    print("="*50)
    
    # Step 1: Show the DSL parsing
    from attachments.utils.dsl import parse_path_expression
    
    test_expressions = [
        "file.pdf",  # Basic file
        "file.pdf[pages:1-3]",  # Modifier
        "file.pdf[resize:50%]",  # Auto-parameter for presenter
        "file.pdf[pages:1-3,resize:800x600]",  # Combined
    ]
    
    print("\n1️⃣  Simple DSL Parsing:")
    for expr in test_expressions:
        path, commands = parse_path_expression(expr)
        print(f"   {expr}")
        print(f"   → path: {path}")
        print(f"   → commands: {commands}")
        print()
    
    # Step 2: Show auto-parameter discovery
    print("2️⃣  Auto-Parameter Discovery:")
    print("   When present.images(attachment) is called:")
    print("   1. Dispatcher reads attachment.commands")
    print("   2. Inspects presenter function signature")
    print("   3. Auto-extracts matching parameters")
    print("   4. Calls function with: images(pdf_reader, resize='50%')")
    print()
    
    # Step 3: Show function signature analysis
    print("3️⃣  Function Signature Analysis:")
    try:
        from attachments.core.decorators import _get_available_presenters_for_type
        from pypdf import PdfReader
        
        presenters = _get_available_presenters_for_type(PdfReader)
        print(f"   Available presenters for PdfReader:")
        for name, desc in presenters.items():
            print(f"   • {name}: {desc}")
        print()
        
    except Exception as e:
        print(f"   Demo error: {e}")
    
    # Step 4: Show live demo
    print("4️⃣  Live Demo:")
    try:
        # Try to load a PDF if available
        pdf_files = list(Path(".").glob("*.pdf"))
        if pdf_files:
            from attachments import Attachments
            
            pdf_path = str(pdf_files[0])
            print(f"   Testing: {pdf_path}[resize:50%]")
            
            # Use the elegant syntax
            ctx = Attachments(f"{pdf_path}[resize:50%]")
            print(f"   Result: {len(ctx.images)} images generated")
            if ctx.images:
                print(f"   Sample: {ctx.images[0][:50]}...")
            
        else:
            print("   No PDF files found for demo")
            
    except Exception as e:
        print(f"   Demo error: {e}")


def demo_auto_documentation():
    """Show how auto-documentation works from function signatures."""
    
    print("\n📚 AUTO-DOCUMENTATION FROM SIGNATURES")
    print("="*50)
    
    print("   Function signatures automatically become DSL help:")
    print()
    print("   def images(pdf_reader: PdfReader, resize: Optional[str] = None):")
    print("   → DSL: file.pdf[resize:50%]")
    print("   → Help: 'resize: Optional[str] = None'")
    print()
    print("   def sample(df: DataFrame, n: int = 100, method: str = 'random'):")
    print("   → DSL: data.csv[n:50,method:stratified]")
    print("   → Help: 'n: int = 100, method: str = random'")
    print()


def demo_usage_examples():
    """Show usage examples of the elegant syntax."""
    
    print("📋 ELEGANT USAGE EXAMPLES")
    print("="*50)
    
    examples = [
        ("Basic image resize", "photo.jpg[resize:50%]"),
        ("PDF with resize", "document.pdf[resize:800x600]"),
        ("Combined operations", "report.pdf[pages:1-3,resize:25%]"),
        ("Data sampling", "big_data.csv[sample:1000]"),
        ("Multiple parameters", "presentation.pptx[quality:high,format:png]"),
    ]
    
    for description, syntax in examples:
        print(f"   {description}:")
        print(f"   {syntax}")
        print()


if __name__ == "__main__":
    demo_elegant_solution()
    demo_auto_documentation()
    demo_usage_examples()
    
    print("🚀 THE MAGIC:")
    print("   ✅ Simple, intuitive DSL: file.pdf[resize:50%]")
    print("   ✅ Auto-parameter discovery from function signatures")
    print("   ✅ Self-documenting through introspection")
    print("   ✅ Zero architectural violations")
    print("   ✅ Maximum elegance achieved!") 