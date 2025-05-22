"""Command-line interface for the Attachments library."""

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from . import Attachments


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="attachments",
        description="The Python funnel for LLM context - turn any file into model-ready text + images",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  attachments document.pdf --text          # Extract text only
  attachments data.csv --images            # Convert to images
  attachments file.pdf --openai           # Format for OpenAI API
  attachments doc.pdf page.jpg --summary  # Process multiple files
  attachments "doc.pdf[pages: 1-3]"       # Use DSL commands
        """,
    )
    
    parser.add_argument(
        "files", 
        nargs="+", 
        help="File paths or URLs to process (supports DSL: 'file.pdf[pages: 1-3]')"
    )
    
    # Output format options
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "--text", 
        action="store_true", 
        help="Output extracted text only"
    )
    output_group.add_argument(
        "--images", 
        action="store_true", 
        help="Output base64 images only"
    )
    output_group.add_argument(
        "--openai", 
        action="store_true", 
        help="Format output for OpenAI API"
    )
    output_group.add_argument(
        "--claude", 
        action="store_true", 
        help="Format output for Claude API"
    )
    
    # Additional options
    parser.add_argument(
        "--summary", 
        action="store_true", 
        help="Show summary information about processed files"
    )
    parser.add_argument(
        "--prompt", 
        type=str, 
        help="Add a prompt to API-formatted output"
    )
    parser.add_argument(
        "--version", 
        action="version", 
        version="%(prog)s 0.4.0"
    )
    
    args = parser.parse_args()
    
    try:
        # Process files
        ctx = Attachments(*args.files)
        
        if not ctx:
            print("No files were successfully processed.", file=sys.stderr)
            return 1
            
        # Handle different output formats
        if args.text:
            print(ctx.text)
        elif args.images:
            for i, img in enumerate(ctx.images):
                print(f"Image {i+1}: {img}")
        elif args.openai:
            import json
            messages = ctx.to_openai(args.prompt or "")
            print(json.dumps(messages, indent=2))
        elif args.claude:
            import json
            messages = ctx.to_claude(args.prompt or "")
            print(json.dumps(messages, indent=2))
        elif args.summary:
            print(ctx)
        else:
            # Default: show summary
            print(ctx)
            
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
        
    return 0


if __name__ == "__main__":
    sys.exit(main()) 