"""Check one install of attachments: the extras given, and nothing else.

    python tests/extras/check.py ""            # plain `pip install attachments`
    python tests/extras/check.py pdf
    python tests/extras/check.py pdf,ocr

Run in an environment holding only the built package and those extras (CI's
`extras` job; locally: scripts/check_extras.sh). The full test suite
installs every extra at once, so it cannot see an extra that is not enough
for its own format: 1.0.0 shipped `attachments[pdf]` failing every scanned
PDF on a missing Pillow, with the advice "pip install PIL".

Each sample file in files/ is read with the defaults and with
`[images: true]`. A format whose extra is installed must read without an
error, and its warnings must give working advice. A format whose extra is
missing may still read (another extra's dependencies can cover it); if it
fails, it must fail as a missing dependency naming that extra. No message may
tell anyone to `pip install` an import name such as PIL.
"""

from __future__ import annotations

import re
import sys
import warnings
from pathlib import Path

FILES = Path(__file__).parent / "files"

#: The extra each sample needs; None: none (the bare install reads it).
NEEDS = {
    "text.pdf": "pdf",
    "scan.pdf": "pdf",
    "sign.png": "image",
    "report.docx": "docx",
    "slides.pptx": "pptx",
    "book.xlsx": "xlsx",
    "page.html": "html",
    "drawing.svg": None,
    "data.csv": None,
    "notes.md": None,
    "notes.ipynb": None,
}

#: Extras that bring others (pyproject.toml).
BUNDLES = {
    "office": {"xlsx", "docx", "pptx"},
    "xlsx-pandas": {"xlsx"},
    "heic": {"image"},
    "all-local": {"pdf", "xlsx", "docx", "pptx", "html", "image", "svg"},
    "server": {"pdf", "xlsx", "docx", "pptx", "html", "image", "svg", "ocr"},
}

#: Advice naming an import instead of what to install.
BAD_ADVICE = re.compile(
    r"pip install (?:PIL|fitz|docx|pptx|bs4|cv2|yaml|sklearn|pymupdf_fonts)\b"
)
#: What working advice names.
GOOD_ADVICE = re.compile(r"attachments\[[a-z-]+\]|LibreOffice|playwright install")


def installed(spec: str) -> set[str]:
    extras: set[str] = set()
    for name in filter(None, spec.split(",")):
        extras.add(name)
        extras |= BUNDLES.get(name, set())
    return extras


def main() -> int:
    warnings.simplefilter("ignore")
    from attachments import __file__ as where
    from attachments import __version__, att, configure

    if "/src/attachments/" in where:
        print(f"refusing to check the source tree ({where}); install the package")
        return 2
    configure(prefer="local-only", progress=False)
    extras = installed(sys.argv[1] if len(sys.argv) > 1 else "")
    print(f"attachments {__version__}, extras: {', '.join(sorted(extras)) or 'none'}")
    failures: list[str] = []

    for name, needs in NEEDS.items():
        for options in ("", "[images: true]"):
            label = name + options
            artifact = att(f"{FILES / name}{options}")[0]
            meta = artifact["meta"]
            error = meta.get("error") or {}
            said = [error.get("message") or "", meta.get("note") or ""]
            said += meta.get("warnings", [])
            said.append(str(meta.get("extra", {}).get("ocr_hint") or ""))
            problems: list[str] = []

            if needs is None or needs in extras:
                if error:
                    problems.append(
                        f"error {error.get('code')}: {error.get('message')}"
                    )
            elif not error:
                pass  # another extra's dependencies cover it (pptx brings Pillow)
            elif error.get("code") != "missing-dependency":
                problems.append(f"expected missing-dependency, got {error}")
            elif f"attachments[{needs}]" not in error.get("message", ""):
                problems.append(f"advice does not name attachments[{needs}]: {error}")

            for text in said:
                if BAD_ADVICE.search(text):
                    problems.append(f"wrong install advice: {text}")
                elif "install" in text and not GOOD_ADVICE.search(text):
                    problems.append(f"install advice without a remedy: {text}")

            if name == "scan.pdf" and "pdf" in extras and not error:
                if "ocr" in extras:
                    if "SCANNED" not in (artifact.get("text") or ""):
                        problems.append("OCR installed but the scan was not read")
                elif not meta.get("extra", {}).get("ocr_hint"):
                    problems.append("no OCR and no hint saying how to get it")
                if len(artifact.get("images") or []) != 1:
                    problems.append("the scanned page has no picture")
            if name == "text.pdf" and options and "pdf" in extras and not error:
                if len(artifact.get("images") or []) != 1:
                    problems.append("images: true made no picture")

            status = "FAIL" if problems else "ok  "
            detail = "; ".join(problems) or (error.get("code") or "read")
            print(f"{status} {label:28} {detail[:200]}")
            failures += [f"{label}: {p}" for p in problems]

    print(f"{len(failures)} problems" if failures else "all good")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
