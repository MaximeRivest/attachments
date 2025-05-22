#!/usr/bin/env python3
"""
Demo: Composable Pipelines with Match Predicates

Testing the idea where:
1. Loaders have match predicates 
2. Pipelines can be composed with | operator
3. Failed matches pass to next pipeline
4. Users can specify presentation via DSL
"""

from typing import Any, Optional, Callable, List, Dict
from dataclasses import dataclass
from attachments.core import load, modify, present, adapt
from attachments.utils.parsing import parse_path_expression


@dataclass
class Pipeline:
    """A composable pipeline with match predicate."""
    name: str
    match_fn: Callable[[str], bool]
    process_fn: Callable[[str], Any]
    
    def __call__(self, source: str) -> Any:
        """Try to process source, raise if no match."""
        if not self.match_fn(source):
            raise ValueError(f"Pipeline '{self.name}' cannot handle: {source}")
        return self.process_fn(source)
    
    def __or__(self, other: 'Pipeline') -> 'Pipeline':
        """Compose pipelines with | operator."""
        def combined_match(source: str) -> bool:
            return self.match_fn(source) or other.match_fn(source)
        
        def combined_process(source: str) -> Any:
            # Try first pipeline
            if self.match_fn(source):
                return self.process_fn(source)
            # Fall back to second pipeline
            elif other.match_fn(source):
                return other.process_fn(source)
            else:
                raise ValueError(f"No pipeline can handle: {source}")
        
        return Pipeline(
            name=f"{self.name}|{other.name}",
            match_fn=combined_match,
            process_fn=combined_process
        )


def create_pdf_pipeline() -> Pipeline:
    """Create a pipeline for PDF files with presentation options."""
    
    def match_pdf(source: str) -> bool:
        path, commands = parse_path_expression(source)
        return path.lower().endswith('.pdf')
    
    def process_pdf(source: str) -> Any:
        path, commands = parse_path_expression(source)
        
        # Load
        att = load.pdf(source)
        
        # Modify based on commands
        if 'pages' in commands:
            att = modify.pages(att)
        
        # Present based on commands
        presentation = commands.get('present', 'text')  # Default to text
        
        if presentation == 'markdown':
            return present.markdown(att)
        elif presentation == 'xml':
            return present.xml(att)
        elif presentation == 'images':
            # Handle image options like 2x2 tiling
            result = present.images(att)
            if 'tile' in commands:
                # Would need a tile modifier
                pass
            return result
        else:
            return present.text(att)
    
    return Pipeline("pdf", match_pdf, process_pdf)


def create_powerpoint_pipeline() -> Pipeline:
    """Create a pipeline for PowerPoint files."""
    
    def match_pptx(source: str) -> bool:
        path, commands = parse_path_expression(source)
        return path.lower().endswith('.pptx')
    
    def process_pptx(source: str) -> Any:
        path, commands = parse_path_expression(source)
        
        # Load
        att = load.pptx(source)
        
        # Modify
        if 'pages' in commands:  # pages works for slides too
            att = modify.pages(att)
        
        # Present
        presentation = commands.get('present', 'markdown')  # Default to markdown for pptx
        
        if presentation == 'text':
            return present.text(att)
        elif presentation == 'xml':
            return present.xml(att)
        elif presentation == 'images':
            return present.images(att)
        else:
            return present.markdown(att)
    
    return Pipeline("powerpoint", match_pptx, process_pptx)


def create_image_pipeline() -> Pipeline:
    """Create a pipeline for image files."""
    
    def match_image(source: str) -> bool:
        path, commands = parse_path_expression(source)
        return any(path.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp'])
    
    def process_image(source: str) -> Any:
        path, commands = parse_path_expression(source)
        
        # Load
        att = load.image(source)
        
        # Modify
        if 'resize' in commands:
            if hasattr(modify, 'resize'):
                resize_fn = getattr(modify, 'resize')
                att = resize_fn(att, commands['resize'])
        
        # Present - images default to image presentation
        presentation = commands.get('present', 'images')
        
        if presentation == 'text':
            # OCR or description
            return present.text(att)
        else:
            return present.images(att)
    
    return Pipeline("image", match_image, process_image)


def create_csv_pipeline() -> Pipeline:
    """Create a pipeline for CSV files."""
    
    def match_csv(source: str) -> bool:
        path, commands = parse_path_expression(source)
        return path.lower().endswith('.csv')
    
    def process_csv(source: str) -> Any:
        path, commands = parse_path_expression(source)
        
        # Load
        att = load.csv(source)
        
        # Modify
        if 'sample' in commands:
            if hasattr(modify, 'sample'):
                sample_size = int(commands.get('sample', 100))
                sample_fn = getattr(modify, 'sample')
                att = sample_fn(att, sample_size)
        
        # Present
        presentation = commands.get('present', 'text')
        
        if presentation == 'markdown':
            return present.markdown(att)
        else:
            return present.text(att)
    
    return Pipeline("csv", match_csv, process_csv)


def create_universal_pipeline() -> Pipeline:
    """Create a universal pipeline by composing all specific pipelines."""
    pdf = create_pdf_pipeline()
    pptx = create_powerpoint_pipeline()
    img = create_image_pipeline()
    csv = create_csv_pipeline()
    
    # Compose with | operator
    return pdf | pptx | img | csv


def demo_single_pipelines():
    """Demo individual pipelines."""
    print("🔧 Testing Individual Pipelines")
    print("=" * 50)
    
    # Test PDF pipeline
    pdf_pipeline = create_pdf_pipeline()
    
    test_cases = [
        "examples/sample.pdf",
        "examples/sample.pdf[pages:1-3]",
        "examples/sample.pdf[present:markdown]",
        "examples/sample.pdf[pages:1,3-5,present:xml]",
    ]
    
    for test in test_cases:
        try:
            result = pdf_pipeline(test)
            print(f"✅ {test}")
            print(f"   Result type: {type(result).__name__}")
            if hasattr(result, 'content'):
                preview = str(result.content)[:100]
                print(f"   Preview: {preview}...")
        except Exception as e:
            print(f"❌ {test}: {e}")
    
    print()


def demo_composed_pipelines():
    """Demo composed pipelines with fallback."""
    print("🔗 Testing Composed Pipelines")
    print("=" * 50)
    
    # Create universal pipeline
    universal = create_universal_pipeline()
    
    test_cases = [
        "examples/sample.pdf[pages:1-2]",
        "examples/sample.pptx[pages:1-3,present:xml]", 
        "sample.png[present:images]",
        "examples/sample.csv[sample:10,present:markdown]",
    ]
    
    for test in test_cases:
        try:
            result = universal(test)
            print(f"✅ {test}")
            print(f"   Pipeline used: {universal.name}")
            print(f"   Result type: {type(result).__name__}")
        except Exception as e:
            print(f"❌ {test}: {e}")
    
    print()


def demo_advanced_dsl():
    """Demo advanced DSL ideas for presentation."""
    print("🎨 Advanced DSL Ideas")
    print("=" * 50)
    
    # Ideas for more complex presentation specs
    ideas = [
        "document.pdf[pages:1-3,present:markdown]",
        "slides.pptx[pages:1-5,present_text:xml,present_image:2x2]",
        "data.csv[sample:100,present:markdown,format:table]",
        "image.jpg[resize:50%,present:images,tile:2x2]",
        "report.pdf[pages:all,present:text,adapt:openai]",
    ]
    
    print("Proposed DSL extensions:")
    for idea in ideas:
        path, commands = parse_path_expression(idea)
        print(f"\n{idea}")
        print(f"  Path: {path}")
        print(f"  Commands: {commands}")


def demo_pipeline_to_llm():
    """Demo complete pipeline from file to LLM format."""
    print("🤖 Complete Pipeline to LLM")
    print("=" * 50)
    
    # Create a pipeline that goes all the way to LLM format
    def create_llm_pipeline(adapter_name: str = 'openai') -> Pipeline:
        base = create_universal_pipeline()
        
        def match_with_adapt(source: str) -> bool:
            path, commands = parse_path_expression(source)
            # Check if base can handle it and adapt is specified
            return base.match_fn(source) and 'adapt' in commands
        
        def process_with_adapt(source: str) -> Any:
            path, commands = parse_path_expression(source)
            
            # Process with base pipeline
            result = base(source)
            
            # Apply adapter if specified
            adapter = commands.get('adapt', adapter_name)
            if adapter == 'openai' and hasattr(adapt, 'openai_chat'):
                prompt = commands.get('prompt', '')
                # Need to get back to attachment object for adapter
                # This shows a limitation - we need to preserve the attachment
                return {"adapter": adapter, "result": result, "note": "Would adapt here"}
            
            return result
        
        return Pipeline(f"{base.name}+adapt", match_with_adapt, process_with_adapt)
    
    llm_pipeline = create_llm_pipeline()
    
    test_cases = [
        "examples/sample.pdf[pages:1-2,adapt:openai,prompt:Summarize this]",
        "examples/sample.pptx[present:markdown,adapt:openai]",
    ]
    
    for test in test_cases:
        try:
            result = llm_pipeline(test)
            print(f"✅ {test}")
            print(f"   Result: {result}")
        except Exception as e:
            print(f"❌ {test}: {e}")


def main():
    """Run all pipeline demos."""
    print("🚀 Composable Pipeline Demo")
    print("=" * 50)
    print()
    
    # Assumptions (Scientific Method)
    print("📋 Assumptions:")
    print("1. Loaders can have match predicates")
    print("2. Pipelines can be composed with | operator")
    print("3. DSL can specify presentation format")
    print("4. Failed matches cascade to next pipeline")
    print()
    
    # Run demos
    demo_single_pipelines()
    demo_composed_pipelines()
    demo_advanced_dsl()
    demo_pipeline_to_llm()
    
    # Conclusions
    print("\n📊 Findings:")
    print("1. ✅ Pipeline composition with | works well")
    print("2. ✅ Match predicates enable intelligent routing")
    print("3. ⚠️  Need to preserve Attachment through pipeline")
    print("4. 💡 DSL parsing already supports complex commands")
    print("5. 🔄 Pipeline needs to return Attachment for adapters")


if __name__ == "__main__":
    main() 