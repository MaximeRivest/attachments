#!/usr/bin/env python
"""60-second terminal demo of attachments 1.0 — for screen recording.

Run:  uv run python scripts/demo.py
Record into a GIF with vhs:  see scripts/demo.tape

Creates its scratch files in a temp dir and cleans up after itself.
"""

import os
import sys
import tempfile
import time

PAUSE = float(os.environ.get("DEMO_PAUSE", "2.0"))


def say(text: str, pause: float | None = None) -> None:
    print(text)
    sys.stdout.flush()
    time.sleep(PAUSE if pause is None else pause)


def heading(text: str) -> None:
    say(f"\n\033[1;36m# {text}\033[0m", pause=1.0)


def main() -> None:
    workdir = tempfile.mkdtemp(prefix="att-demo-")
    os.chdir(workdir)

    say("\033[1mattachments 1.0\033[0m — turn anything into LLM-ready artifacts", 1.0)
    say("$ pip install attachments", 1.0)

    # Make a real PDF to play with.
    import fitz

    doc = fitz.open()
    for i, line in enumerate(
        [
            "Q1 revenue grew 12% to $4.2M.",
            "Q2 churn dropped to 1.1%.",
            "Outlook: hiring 3 engineers.",
        ],
        1,
    ):
        page = doc.new_page(width=400, height=200)
        page.insert_text((40, 80), f"Page {i}: {line}", fontsize=12)
    doc.save("report.pdf")
    doc.close()

    from attachments import att

    heading("One function. Any input.")
    say('>>> a = att("report.pdf[images: true]")', 0.5)
    a = att("report.pdf[images: true, dpi: 60]")
    say(repr(a))

    heading("print() is the assembled prompt")
    say(">>> print(a)", 0.5)
    say(str(a))

    heading("Discovery is built in")
    say('>>> att.options(".pdf")', 0.5)
    say(repr(att.options(".pdf")))

    heading("Errors never raise — they come back as artifacts")
    say('>>> att("missing.pdf")', 0.5)
    say(repr(att("missing.pdf")))

    heading("Typos teach")
    say('>>> att("data.csv[row: 5]")', 0.5)
    with open("data.csv", "w") as f:
        f.write("region,sales\nEast,100\nWest,120\n")
    warned = att("data.csv[row: 5]")
    say(repr(warned[0]["meta"]["warnings"]))

    heading("The last mile hangs off the result")
    say('>>> a.claude("Summarize in one sentence.")', 0.5)
    msgs = a.claude("Summarize in one sentence.")
    say(f"    -> 1 message, blocks: {[b['type'] for b in msgs[0]['content']]}")
    say(">>> a.chunk(max_chars=80)", 0.5)
    say(f"    -> {len(a.chunk(max_chars=80))} segment-aware chunks")

    heading("Scanned PDF? OCR kicks in automatically")
    img_doc = fitz.open()
    p = img_doc.new_page(width=300, height=100)
    p.insert_text((20, 50), "INVOICE TOTAL: $1,234.56", fontsize=14)
    pix = p.get_pixmap(dpi=150)
    scan = fitz.open()
    sp = scan.new_page(width=300, height=100)
    sp.insert_image(fitz.Rect(0, 0, 300, 100), stream=pix.tobytes("png"))
    scan.save("scan.pdf")
    scan.close()
    img_doc.close()
    say('>>> att("scan.pdf")[0]["text"]   # image-only page, no text layer', 0.5)
    say(repr(att("scan.pdf")[0]["text"]))

    say(
        "\n\033[1mpip install attachments\033[0m — github.com/MaximeRivest/attachments",
        3.0,
    )

    for f in ("report.pdf", "scan.pdf", "data.csv"):
        os.remove(f)


if __name__ == "__main__":
    main()
