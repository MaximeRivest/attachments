"""Check a running attachments service end to end.

    .venv/bin/python deploy/lambda/smoke.py   # lambda's nginx, 127.0.0.1:8820
    .venv/bin/python deploy/lambda/smoke.py \
        https://api.attachments.dev https://attachments.dev

Checks: health and version; a Word file, an old Word 97 file (LibreOffice) and a
PowerPoint file read by the service; a 10-page scan read by OCR (time, and words read
correctly against the text the scan was made from); that the service refuses to fetch
a private address; the browser (CORS) answer for the website; the website itself. It
does not test the rate limit, which would lock this machine out for a minute. Needs
this repository's .venv (attachments, PyMuPDF).
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import pymupdf

from attachments import att, configure

API = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8820"
SITE = sys.argv[2] if len(sys.argv) > 2 else None
LOCAL = API.startswith("http://127.0.0.1")
# Word and PowerPoint samples from markitdown's tests (any checkout of it will do)
BENCH = "/home/maxime/Projects/attachments-bench"
MARKITDOWN = f"{BENCH}/src-markitdown/packages/markitdown/tests/test_files"
FILES = Path(os.environ.get("SMOKE_FILES", MARKITDOWN))

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'ok  ' if ok else 'FAIL'} {name}{': ' + detail if detail else ''}")
    if not ok:
        failures.append(name)


def http(method: str, url: str, body: bytes | None = None, headers: dict | None = None):
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


# Lorem-free text with real words, so OCR quality can be counted word by word.
PARAGRAPH = (
    "The hosted service reads documents for language models. Scanned pages go through "
    "optical character recognition, page by page, and the text comes back with each "
    "page's picture. Invoice number {n} was paid on March {d}, 2026, for 1,250 dollars."
)


def make_scan(path: Path, pages: int = 10) -> list[str]:
    """An image-only PDF (no text layer) and the words printed on it."""
    words: list[str] = []
    src = pymupdf.open()
    for n in range(pages):
        page = src.new_page()
        text = "\n".join(PARAGRAPH.format(n=4100 + n, d=n + 3) for _ in range(3))
        page.insert_textbox(pymupdf.Rect(60, 60, 540, 780), text, fontsize=12)
        words += re.findall(r"[A-Za-z0-9]+", text)
    scan = pymupdf.open()
    for page in src:
        pix = page.get_pixmap(dpi=150, colorspace=pymupdf.csGRAY)
        out = scan.new_page(width=page.rect.width, height=page.rect.height)
        out.insert_image(out.rect, stream=pix.tobytes("png"))
    scan.save(path)
    return words


def main() -> int:
    headers = {"Host": "api.attachments.dev"} if LOCAL else {}
    status, _, body = http("GET", f"{API}/health", headers=headers)
    health = json.loads(body) if status == 200 else {}
    check(
        "health",
        status == 200 and health.get("status") == "ok",
        f"version {health.get('version')}",
    )

    # The client cannot set a Host header: against 127.0.0.1 nginx answers with its
    # first server, api.attachments.dev, which is the one wanted.
    configure(service_url=API)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        doc = tmp / "test.doc"
        # Word 97 copy of test.docx, made once with LibreOffice, kept next to this file.
        doc.write_bytes((Path(__file__).parent / "smoke-test.doc").read_bytes())
        for path in (FILES / "test.docx", doc, FILES / "test.pptx"):
            t0 = time.time()
            try:
                a = att(str(path), prefer="service-only")
                text = a.text
                via = {x["meta"].get("via") for x in a}
                check(
                    f"{path.suffix} via service",
                    len(text) > 200 and "service" in via,
                    f"{len(text)} characters, {time.time() - t0:.1f} s",
                )
            except Exception as e:  # noqa: BLE001
                check(f"{path.suffix} via service", False, f"{type(e).__name__}: {e}")

        scan = tmp / "scan-10.pdf"
        truth = make_scan(scan)
        t0 = time.time()
        try:
            a = att(f"{scan}[ocr: true]", prefer="service-only")
            took = time.time() - t0
            got = re.findall(r"[A-Za-z0-9]+", a.text)
            have = {}
            for w in got:
                have[w] = have.get(w, 0) + 1
            hit = 0
            for w in truth:
                if have.get(w, 0) > 0:
                    have[w] -= 1
                    hit += 1
            check(
                "10-page scan by OCR",
                hit / len(truth) > 0.97,
                f"{took:.1f} s ({took / 10:.1f} s a page), "
                f"{100 * hit / len(truth):.1f}% of words read",
            )
        except Exception as e:  # noqa: BLE001
            check("10-page scan by OCR", False, f"{type(e).__name__}: {e}")

    status, _, body = http(
        "POST",
        f"{API}/unpack",
        json.dumps({"url": "http://127.0.0.1:8810/health"}).encode(),
        {**headers, "Content-Type": "application/json"},
    )
    check("refuses a private address", status == 400, f"{status} {body[:90]!r}")

    status, h, _ = http(
        "OPTIONS",
        f"{API}/process",
        headers={**headers, "Origin": "https://attachments.dev"},
    )
    check(
        "browser access from attachments.dev",
        status == 204
        and h.get("Access-Control-Allow-Origin") == "https://attachments.dev",
        str(status),
    )

    site = SITE or API
    status, _, body = http(
        "GET", f"{site}/", headers={"Host": "attachments.dev"} if LOCAL else {}
    )
    check(
        "website",
        status == 200 and b"attachments" in body.lower(),
        f"{status}, {len(body)} bytes",
    )

    print(
        "all checks passed"
        if not failures
        else f"{len(failures)} failed: {', '.join(failures)}"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
