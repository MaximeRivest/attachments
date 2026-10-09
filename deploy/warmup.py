"""Warm-up script for the attachments server image.

Run once at container start (before gunicorn forks workers, via --preload
importing this module's side effects) OR at image build time to populate
caches. It:

1. Pre-imports every processor module so the import cost (pymupdf, pandas,
   lxml, PIL, ...) is paid once in the gunicorn master and shared with
   workers via fork (copy-on-write).
2. Runs a tiny OCR inference so rapidocr loads its ONNX models (shipped in
   its wheel) and the onnxruntime sessions are in RAM before the first
   request. Workers forked afterwards use them (checked: no hang).
3. Converts a tiny document with LibreOffice both ways (docx -> doc, then
   reads the .doc back), so a broken LibreOffice install is caught, and its
   files are in the page cache before the first .doc/.ppt request.

Usage:
    python /app/warmup.py            # at container start: problems are logged
    python /app/warmup.py --strict   # at image build: any problem fails
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


def warm_ocr(strict: bool = False) -> None:
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

        result = _process_single(
            "warmup.png", buf.getvalue(), options={"ocr": True}, prefer="local-only"
        )
        error = result.get("meta", {}).get("error")
        if error:
            raise RuntimeError(f"{error['code']}: {error['message']}")
        print(f"[warmup] OCR engine warm in {time.time() - t0:.1f}s")
    except Exception as exc:  # noqa: BLE001 — warmup must never kill the server
        if strict:
            raise
        print(f"[warmup] OCR warmup skipped/failed (non-fatal): {exc}", file=sys.stderr)


def warm_libreoffice(strict: bool = False) -> None:
    """Convert a tiny document both ways: LibreOffice installed and working."""
    t0 = time.time()
    try:
        import docx

        from attachments._processors import processors
        from attachments._processors.legacy_office import convert
        from attachments.deps import find_libreoffice

        soffice = find_libreoffice()
        if soffice is None:
            raise RuntimeError("LibreOffice (soffice) not found")
        document = docx.Document()
        document.add_paragraph("warmup 123")
        buf = io.BytesIO()
        document.save(buf)
        doc_bytes = convert(buf.getvalue(), ".docx", ".doc", soffice)
        result = processors[".doc"](doc_bytes, filename="warmup.doc")
        if "warmup 123" not in result.get("text", ""):
            raise RuntimeError(f"unexpected result: {result.get('meta')}")
        print(f"[warmup] LibreOffice converts (.doc) in {time.time() - t0:.1f}s")
        t1 = time.time()
        drawn = processors[".docx"](
            buf.getvalue(), filename="warmup.docx", render_images=True
        )
        if len(drawn.get("images", [])) != 1:
            raise RuntimeError(f"page picture failed: {drawn.get('meta')}")
        print(f"[warmup] LibreOffice draws pages in {time.time() - t1:.1f}s")
    except Exception as exc:  # noqa: BLE001 — warmup must never kill the server
        if strict:
            raise
        print(f"[warmup] LibreOffice check failed (non-fatal): {exc}", file=sys.stderr)


def main(strict: bool = False) -> None:
    warm_processors()
    warm_ocr(strict)
    warm_libreoffice(strict)
    print("[warmup] done")


if __name__ == "__main__":
    main(strict="--strict" in sys.argv[1:])
