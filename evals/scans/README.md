# Scanned PDFs: OCR accuracy, speed, request size

Scanned-looking PDFs whose text is known: each page is typeset with a real
font, drawn at 300 dpi in grey, then "scanned" (paper tint, slight tilt,
sensor noise, blur, JPEG at quality 75) and put back into a PDF with no
text layer.

```bash
uv run python evals/scans/make_scans.py /tmp/scans   # builds the PDFs + truth.json
uv run python evals/scans/run.py /tmp/scans          # the table below
```

| file | what |
|---|---|
| scan-en.pdf | 3 pages of English prose |
| scan-fr.pdf | 3 pages of French (accents) |
| scan-table.pdf | 3 invoices: numbers, amounts |
| scan-20.pdf | 20 pages mixing the three |
| mixed.pdf | 3 typed pages with 2 scanned pages among them |

Errors are counted on whitespace-normalised text: a word glued to its
neighbour ("Revenuegrewby") is a wrong word, as a model or a search index
sees it.

## Results (2026-10-09, attachments 1.0.0b3, default options)

48-core Threadripper (3 pages at once × 4 threads), machine shared with
other work:

| file | pages | words wrong | characters wrong | s/page | Claude request |
|---|---:|---:|---:|---:|---:|
| scan-en.pdf | 3 | 0.3% | 0.0% | 1.42 | 1.6 MB |
| scan-fr.pdf | 3 | 0.0% | 0.0% | 1.15 | 1.5 MB |
| scan-table.pdf | 3 | 0.0% | 0.0% | 0.87 | 1.3 MB |
| scan-20.pdf | 20 | 0.4% | 0.0% | 0.95 | 9.9 MB |
| mixed.pdf | 5 | 0.0% | 0.0% | 0.46 | 1.0 MB |

Same machine limited to 8 cores (2 × 4): scan-20 at 1.11 s/page. Limited
to 2 cores (like the hosted service's server): 2.07 s/page.

## Before (1.0.0b2)

RapidOCR 1.4 (`rapidocr_onnxruntime`, PP-OCRv4 models), pages read one
at a time, page pictures PNG:

| file | words wrong | characters wrong | s/page |
|---|---:|---:|---:|
| scan-en.pdf | 36.2% | 4.4% | 8.3 |
| scan-fr.pdf | 49.2% | 10.0% | 6.0 |
| scan-table.pdf | 59.9% | 6.9% | 4.5 |

Spaces between words were lost ("Revenuegrewby twelvepercent") and
French accents dropped ("réunion" read "reunion"). scan-20.pdf made a
**60 MB** Claude request (2.3 MB of PNG per page); the API accepts 32 MB.

## What was measured to choose the settings

- **Engine**: RapidOCR 3.10 with its bundled PP-OCRv6 models (offline, no
  download at first use). Same pages, same machine: 3% of words wrong with
  its defaults, against 36-60% for the old engine.
- **Per-line orientation classifier off**: with it on, 2 of 84 upright
  lines came back as garbage ("Tn og ag n Tn anag"); off, 0 of 84. It
  never rescued a turned page either (89-95% of words wrong on pages
  turned 90, 180 or 270 degrees). Whole pages are turned instead: boxes
  taller than wide mean a quarter turn, a median score under 0.8 (upright
  ~0.99, upside down ~0.65) means upside down. All four orientations: 0%
  words wrong.
- **Threads**: onnxruntime's default, a thread per core, took 2.45 s and
  94 s of processor time per page on 48 cores; 4 threads took 1.31 s and
  4.9 s. Pages at once (4 threads each): 1 → 1.31 s/page, 2 → 0.84,
  3 → 0.78, 4 → 0.77, 6 → 0.85. About 0.6 GB of memory per page being
  read. Hence 4 threads per page, up to 3 pages at once
  (`configure(ocr_workers=N)` to change).
- **Resolution**: 120 dpi 0.5% words wrong, 150 dpi 0%, 200 dpi 0.1%;
  8-point print 0% at both 150 and 200 dpi. 200 dpi kept as a margin for
  poor or tiny print (20% slower than 150).
- **Page pictures**: a scanned page is 2.3 MB as PNG, 0.38 MB as JPEG at
  quality 85, and reads the same. `image_format: auto` (the default) uses
  JPEG for pages that pictures cover at least half of, PNG for the rest.
- **Reading order**: the engine returns lines top to bottom across the
  page, mixing the two columns of an article; columns are now read one
  after the other (tables stay in rows: short cells are not columns of
  prose).
