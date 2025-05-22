import sys
from .registry import REGISTRY
from .core import Attachments
import logging
import os

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

    parser.add_argument("-d", "--debug", action="store_true",
                        help="Print plugin diagnostics to stderr")

    parser.add_argument(
        "--log-level",
        default=os.getenv("ATTACHMENTS_LOG", "WARNING"),
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set the logging level (default: WARNING or ATTACHMENTS_LOG env var)"
    )

    parsed_args = parser.parse_args(args)

    # Apply log level from CLI arg
    logging.basicConfig(level=parsed_args.log_level.upper(), force=True) # force=True to override previous config

    if parsed_args.debug:
        import pprint
        from . import diagnostics
        pprint.pp(diagnostics(), stream=sys.stderr)

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