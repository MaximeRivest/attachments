"""Warm-up script for the attachments server image.

Run once at container start (before gunicorn forks workers, via --preload
importing this module's side effects) OR at image build time to populate
caches. It:

1. Pre-imports every processor module so the import cost (pymupdf, pandas,
   lxml, PIL, ...) is paid once in the gunicorn master and shared with
   workers via fork (copy-on-write).
2. Runs a tiny OCR inference so rapidocr downloads/loads its ONNX models
   and the onnxruntime session is resident in RAM before the first request.

Usage:
    python /app/warmup.py
"""

from __future__ import annotations

import io
import sys
import time


def warm_processors() -> None:
    """Import the processor registry — this pulls in every heavy dep."""
    t0 = time.time()
    from attachments._processors import processors
    from attachments.deps import check_deps

    deps = check_deps()
    available = sorted(k for k, v in deps.items() if v)
    print(f"[warmup] {len(processors)} formats registered in {time.time() - t0:.1f}s")
    print(f"[warmup] features: {', '.join(available)}")


def warm_ocr() -> None:
    """Run one tiny OCR inference so the ONNX session is RAM-warm."""
    t0 = time.time()
    try:
        from PIL import Image, ImageDraw

        # Same code path the server uses for POST /process.
        from attachments.core import _process_single

        # Tiny synthetic image with text — enough to force model load + run.
        img = Image.new("RGB", (200, 60), "white")
        draw = ImageDraw.Draw(img)
        draw.text((10, 20), "warmup 123", fill="black")
        buf = io.BytesIO()
        img.save(buf, format="PNG")

        _process_single(
            "warmup.png", buf.getvalue(), options={"ocr": True}, prefer="local-only"
        )
        print(f"[warmup] OCR engine warm in {time.time() - t0:.1f}s")
    except Exception as exc:  # noqa: BLE001 — warmup must never kill the server
        print(f"[warmup] OCR warmup skipped/failed (non-fatal): {exc}", file=sys.stderr)


def main() -> None:
    warm_processors()
    warm_ocr()
    print("[warmup] done")


if __name__ == "__main__":
    main()
