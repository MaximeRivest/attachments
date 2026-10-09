"""Measure scanned-PDF handling: OCR accuracy, speed, request size.

    uv run python evals/scans/make_scans.py /tmp/scans   # once
    uv run python evals/scans/run.py /tmp/scans

For each test PDF, with default options: word and character error rates
against the known text, seconds per page (the OCR engine loaded first, so
its one-time start is not counted), and the size of the Claude request
`.claude()` builds. Results in README.md next to this file.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from score import cer, wer  # noqa: E402

from attachments import att  # noqa: E402
from attachments._processors import _ocr  # noqa: E402


def main(folder: Path) -> None:
    truth = json.loads((folder / "truth.json").read_text())
    _ocr.engine()  # load the models before timing
    workers, threads = _ocr.plan()
    print(f"{_ocr.usable_cores()} cores; {workers} pages at once x {threads} threads\n")
    print("| file | pages | words wrong | characters wrong | s/page | request |")
    print("|---|---:|---:|---:|---:|---:|")
    for name, pages in truth.items():
        started = time.monotonic()
        result = att(str(folder / name))
        seconds = time.monotonic() - started
        doc = result[0]
        texts = {
            s["page"]: doc["text"][s["start"] : s["end"]]
            for s in doc["meta"]["segments"]
        }
        got = [texts.get(n, "") for n in range(1, len(pages) + 1)]
        w = sum(wer(t, g) for t, g in zip(pages, got, strict=True)) / len(pages)
        c = sum(cer(t, g) for t, g in zip(pages, got, strict=True)) / len(pages)
        request = len(json.dumps({"messages": result.claude("Summarize.")})) / 1e6
        print(
            f"| {name} | {len(pages)} | {w:.1%} | {c:.1%} | "
            f"{seconds / len(pages):.2f} | {request:.1f} MB |"
        )


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/scans"))
