"""Build scanned-looking PDFs whose text is known, for OCR and size checks.

Each page is typeset with a real font, drawn at 300 dpi in grey, then
"scanned": paper tint, a slight tilt, sensor noise, a little blur, JPEG
at quality 75, and put back into a PDF with no text layer. That is what a
desktop scanner or a phone scanning app produces; the exact text of each
page is kept next to the PDF, so OCR can be scored.

    uv run python evals/scans/make_scans.py [OUT_DIR]

Writes scan-en.pdf (English prose), scan-fr.pdf (French, accents),
scan-table.pdf (an invoice with numbers), scan-20.pdf (20 pages mixing
the three, for size and speed), mixed.pdf (text pages with two scanned
pages inside) and truth.json ({file: [page text, ...]}).
"""

from __future__ import annotations

import io
import json
import random
import sys
from pathlib import Path

import numpy as np
import pymupdf
from PIL import Image, ImageFilter

EN = [
    "The committee met on Tuesday morning to review the quarterly results "
    "and the plan for the coming year. Revenue grew by twelve percent, "
    "mostly from the new service contracts signed in the spring, while "
    "costs stayed close to the budget approved in January.",
    "Several members asked why the warehouse expansion was delayed. The "
    "contractor explained that the permits arrived three weeks late and "
    "that the steel supplier had changed its delivery schedule twice. The "
    "work should now be finished before the end of November.",
    "A short discussion followed about hiring. Two positions remain open "
    "in the support team, and the manager proposed to fill them with "
    "people who already know the product, even if training takes longer "
    "for candidates coming from outside the company.",
    "The meeting closed with a vote on the new travel policy. It passed "
    "with nine votes in favour and two against. The secretary will send "
    "the final text to every department by Friday, together with the "
    "minutes and the list of actions agreed today.",
    "Questions about this document can be sent to the office of the "
    "treasurer. Please include the reference number printed at the top of "
    "the first page, and allow five working days for an answer.",
]

FR = [
    "Le conseil s'est réuni mardi matin pour étudier les résultats du "
    "trimestre et le plan de l'année prochaine. Les revenus ont augmenté "
    "de douze pour cent, surtout grâce aux nouveaux contrats signés au "
    "printemps, et les dépenses sont restées près du budget prévu.",
    "Plusieurs membres ont demandé pourquoi l'agrandissement de l'entrepôt "
    "avait pris du retard. L'entrepreneur a expliqué que les permis étaient "
    "arrivés trois semaines trop tard et que le fournisseur d'acier avait "
    "modifié deux fois son calendrier de livraison.",
    "Une courte discussion a suivi au sujet de l'embauche. Deux postes "
    "restent ouverts dans l'équipe de soutien; la gestionnaire propose de "
    "les pourvoir avec des personnes qui connaissent déjà le produit, même "
    "si la formation des candidats externes serait plus rapide.",
    "La séance s'est terminée par un vote sur la nouvelle politique de "
    "déplacement, adoptée à neuf voix contre deux. La secrétaire enverra "
    "le texte final à chaque service d'ici vendredi, avec le procès-verbal "
    "et la liste des décisions prises aujourd'hui.",
]


def invoice(seed: int) -> str:
    rng = random.Random(seed)
    items = [
        "Paper, A4, 500 sheets",
        "Toner cartridge",
        "Desk lamp",
        "USB cable, 2 m",
        "Notebook, lined",
        "Stapler",
        "Office chair",
        "Monitor stand",
        "Whiteboard markers",
        "Filing cabinet",
    ]
    lines = [
        f"INVOICE No. {10200 + seed}",
        f"Date: 2026-09-{seed % 28 + 1:02d}",
        "Bill to: Northwind Supplies Ltd, 45 King Street, Montreal",
        "",
    ]
    total = 0.0
    for name in rng.sample(items, 8):
        qty = rng.randint(1, 12)
        price = rng.randint(300, 25000) / 100
        total += qty * price
        lines.append(f"{name}    {qty} x {price:.2f}    {qty * price:.2f}")
    tax = round(total * 0.14975, 2)
    lines += [
        "",
        f"Subtotal    {total:.2f}",
        f"Tax (14.975%)    {tax:.2f}",
        f"Total due    {total + tax:.2f}",
        "",
        "Payment within 30 days. Thank you for your business.",
    ]
    return "\n".join(lines)


def page_text(kind: str, n: int) -> str:
    if kind == "table":
        return invoice(n)
    paras = EN if kind == "en" else FR
    rot = n % len(paras)
    chosen = paras[rot:] + paras[:rot]
    title = (
        f"Minutes of meeting {n + 1}"
        if kind == "en"
        else f"Procès-verbal de la réunion {n + 1}"
    )
    return title + "\n\n" + "\n\n".join(chosen)


def typeset(text: str) -> bytes:
    """A one-page PDF with *text*, in a real font, with a text layer."""
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)  # US Letter
    rect = pymupdf.Rect(72, 72, 540, 720)
    left = page.insert_textbox(
        rect, text, fontname="tiro", fontsize=11, lineheight=1.35
    )
    assert left >= 0, "text does not fit on the page"
    return doc.tobytes()


def scan(pdf_page: bytes, seed: int, dpi: int = 300) -> bytes:
    """The page as a scanner would deliver it: a JPEG, no text."""
    rng = np.random.default_rng(seed)
    src = pymupdf.open(stream=pdf_page, filetype="pdf")
    pix = src[0].get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
    img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
    paper = 236 + int(rng.integers(-6, 6))
    arr = np.asarray(img, dtype=np.float32) / 255.0
    arr = paper * arr + 25 * (1 - arr)  # ink ~25, paper ~236
    img = Image.fromarray(arr.clip(0, 255).astype("uint8"))
    img = img.rotate(
        float(rng.uniform(-0.8, 0.8)), resample=Image.BICUBIC, fillcolor=paper
    )
    arr = np.asarray(img, dtype=np.float32)
    arr += rng.normal(0, 7, arr.shape)  # sensor noise
    img = Image.fromarray(arr.clip(0, 255).astype("uint8"))
    img = img.filter(ImageFilter.GaussianBlur(0.6)).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=75)
    return buf.getvalue()


def build(pages: list[tuple[str, int, bool]], path: Path) -> list[str]:
    """Write a PDF of (kind, n, scanned) pages; return each page's text."""
    out = pymupdf.open()
    texts = []
    for kind, n, scanned in pages:
        text = page_text(kind, n)
        texts.append(text)
        typed = typeset(text)
        if scanned:
            page = out.new_page(width=612, height=792)
            page.insert_image(page.rect, stream=scan(typed, seed=n * 7 + len(kind)))
        else:
            out.insert_pdf(pymupdf.open(stream=typed, filetype="pdf"))
    out.save(path, garbage=4, deflate=True)
    return texts


def main(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    truth: dict[str, list[str]] = {}
    plans = {
        "scan-en.pdf": [("en", i, True) for i in range(3)],
        "scan-fr.pdf": [("fr", i, True) for i in range(3)],
        "scan-table.pdf": [("table", i, True) for i in range(3)],
        "scan-20.pdf": [(("en", "fr", "table")[i % 3], i, True) for i in range(20)],
        "mixed.pdf": [
            ("en", 0, False),
            ("en", 1, True),
            ("en", 2, False),
            ("table", 3, True),
            ("en", 4, False),
        ],
    }
    for name, plan in plans.items():
        truth[name] = build(plan, out_dir / name)
        size = (out_dir / name).stat().st_size / 1e6
        print(f"{name}: {len(plan)} pages, {size:.1f} MB")
    (out_dir / "truth.json").write_text(json.dumps(truth, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/scans"))
