import sys
from .registry import REGISTRY
from .core import Attachments

def cli(args=None, attachments_cls=Attachments):
    """CLI entry point with dependency injection support for testing."""
    import argparse
    parser = argparse.ArgumentParser(
        description="Attachments CLI: inspect registry or extract text/images from files"
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="File(s) to extract (if omitted, just dumps plugin registry)",
    )
    parsed_args = parser.parse_args(args)

    if not parsed_args.paths:
        print("[attachments] Plugin registry:")
        REGISTRY.dump()
    else:
        atts = attachments_cls(*parsed_args.paths)
        print("[attachments] Text output:\n")
        print(str(atts))
        images = atts.images
        if images is not None:
            print(f"\n[attachments] {len(images)} image(s) extracted (base64 PNGs)")
        else:
            print("\n[attachments] 0 image(s) extracted (base64 PNGs)")
    
    # Always exit with success code
    sys.exit(0)

if __name__ == "__main__":
    cli() 