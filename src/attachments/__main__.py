import sys
from .registry import REGISTRY
from .core import Attachments

def cli():
    import argparse
    parser = argparse.ArgumentParser(
        description="Attachments CLI: inspect registry or extract text/images from files"
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="File(s) to extract (if omitted, just dumps plugin registry)",
    )
    args = parser.parse_args()

    if not args.paths:
        print("[attachments] Plugin registry:")
        REGISTRY.dump()
        return 0
    else:
        atts = Attachments(*args.paths)
        print("[attachments] Text output:\n")
        print(str(atts))
        images = atts.images
        if images is not None:
            print(f"\n[attachments] {len(images)} image(s) extracted (base64 PNGs)")
        else:
            print("\n[attachments] 0 image(s) extracted (base64 PNGs)")
        return 0

if __name__ == "__main__":
    sys.exit(cli()) 