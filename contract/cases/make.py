"""Write the contract's cases: ``python contract/cases/make.py``.

Each area's inputs are written here, by hand, from the rules in
``contract/*.md``: the situations each rule is about, its edges, and
the text that trips implementations (characters outside the BMP,
white space that languages disagree on, ties in rounding). Their
expected answers are then drafted by running the Python implementation
(``tests/_contract.py``) and are marked ``draft`` until a person has
read them against the rules (``REVIEWED`` below). A Python bug found that
way is fixed in Python, never kept in a case.

``./check`` fails when the committed files differ from what this script
writes, so a case changes only by changing this script.
"""

from __future__ import annotations

import base64
import json
import random
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from _contract import run  # noqa: E402

#: Areas a person has read case by case against the rules. Until then a
#: file says ``"review": "draft"``: it pins today's behavior, and a
#: difference from it is a question to ask, not yet an answer.
REVIEWED: set[str] = set()


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def png(width: int, height: int) -> bytes:
    """The first 33 bytes of a PNG: signature and IHDR, enough for its size."""
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        + struct.pack(">II", width, height)
        + b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    )


def jpeg(width: int, height: int, *, progressive: bool = False, app: int = 0) -> bytes:
    """SOI, an optional APP1 of *app* bytes, then a frame header."""
    out = b"\xff\xd8"
    if app:
        out += b"\xff\xe1" + struct.pack(">H", app + 2) + b"\x00" * app
    sof = 0xC2 if progressive else 0xC0
    out += bytes([0xFF, sof]) + struct.pack(">HBHHB", 11, 8, height, width, 1)
    return out + b"\x01\x11\x00"


def gif(width: int, height: int) -> bytes:
    return b"GIF89a" + struct.pack("<HH", width, height) + b"\x00\x00\x00"


def webp(kind: str, width: int, height: int) -> bytes:
    head = b"RIFF\x00\x00\x00\x00WEBP"
    if kind == "VP8 ":
        body = b"VP8 " + b"\x00" * 10 + struct.pack("<HH", width, height)
    elif kind == "VP8L":
        w, h = width - 1, height - 1
        bits = w | (h << 14)
        body = b"VP8L" + b"\x00" * 4 + b"\x2f" + struct.pack("<I", bits) + b"\x00" * 5
    else:
        body = (
            b"VP8X"
            + b"\x00" * 8
            + (width - 1).to_bytes(3, "little")
            + (height - 1).to_bytes(3, "little")
        )
    return head + body


def bmp(width: int, height: int, *, core: bool = False) -> bytes:
    head = b"BM" + b"\x00" * 12
    if core:
        return (
            head
            + struct.pack("<I", 12)
            + struct.pack("<HH", width, height)
            + b"\x00" * 6
        )
    return head + struct.pack("<I", 40) + struct.pack("<ii", width, height)


def image(
    name: str | None,
    data: bytes | None,
    *,
    page: int | None = None,
    mimetype: str | None = "image/png",
    b64_only: bool = True,
) -> dict:
    item: dict = {}
    if name is not None:
        item["name"] = name
    if mimetype is not None:
        item["mimetype"] = mimetype
    if data is not None:
        item["bytes_b64"] = b64(data)
    if page is not None:
        item["page"] = page
    return item


def art(
    text: str | dict = "",
    *,
    source: str | None = None,
    images: list | None = None,
    **meta,
) -> dict:
    m = dict(meta)
    if source is not None:
        m = {"source": source, **m}
    return {"text": text, "images": images or [], "audio": [], "video": [], "meta": m}


def seg(start: int, end: int, page: int | None = None, kind: str = "page") -> dict:
    s = {
        "kind": kind,
        "label": f"{kind} {page}" if page else kind,
        "start": start,
        "end": end,
    }
    if page is not None:
        s["page"] = page
    return s


def paged(
    pages: list[str],
    *,
    sep: str = "\n\n",
    image_pages: list,
    source: str,
    labelled: bool = True,
) -> dict:
    """A document whose pages are *pages*, joined by *sep*, with segments."""
    text, segments, at = "", [], 0
    for i, page_text in enumerate(pages, 1):
        if i > 1:
            text += sep
            at += len(sep)
        segments.append(seg(at, at + len(page_text), i if labelled else None))
        text += page_text
        at += len(page_text)
    images = [
        image(f"p{p}.png" if p else "loose.png", png(10, 10), page=p)
        for p in image_pages
    ]
    return art(text, source=source, images=images, segments=segments)


# ---------------------------------------------------------------------------
# present: text, parts, claude, openai, lm15
# ---------------------------------------------------------------------------

PICTURE = png(40, 30)

SCENES: dict[str, list[dict]] = {
    "one text": [art("Alpha beta.", source="notes.txt")],
    "outer white space is not content": [art("\n\n  Alpha.\t\n ", source="a.txt")],
    "two documents and a failure": [
        art("First.", source="a.txt"),
        art(source="broken.pdf", error={"code": "parse-error", "message": "not a PDF"}),
        art("Second.", source="b.md"),
    ],
    "an empty artifact shows nothing": [
        art(source="empty.txt"),
        art("x", source="x.txt"),
    ],
    "a photo": [art(source="cat.png", images=[image("cat.png", PICTURE)])],
    "pictures without a name or type": [
        art(
            source="s.pdf",
            images=[image(None, PICTURE), image("t.bin", PICTURE, mimetype=None)],
        )
    ],
    "an image without data is skipped": [
        art(
            "Text.",
            source="d.pdf",
            images=[image("ghost.png", None), image("p.png", PICTURE)],
        )
    ],
    "no source": [
        {"text": "orphan", "images": [], "audio": [], "video": [], "meta": {}}
    ],
    "a folder overview": [
        art("docs/\n└── cat.png", source="docs/", kind="directory"),
        art(source="docs/cat.png", images=[image("cat.png", PICTURE)]),
    ],
    "pages and their pictures": [
        paged(["one", "two", "three"], image_pages=[1, 3], source="r.pdf")
    ],
    "a picture for a page with no text segment": [
        art(
            "one\n\nthree",
            source="r.pdf",
            segments=[seg(0, 3, 1), seg(5, 10, 3)],
            images=[
                image("p2.png", PICTURE, page=2),
                image("loose.png", PICTURE),
                image("p9.png", PICTURE, page=9),
                image("p1.png", PICTURE, page=1),
            ],
        )
    ],
    "pictures before the first page": [
        {
            **paged(["a", "b"], image_pages=[1], source="r.pdf"),
            "meta": {"source": "r.pdf", "segments": [seg(0, 1, 2), seg(3, 4, 3)]},
            "images": [image("p1.png", PICTURE, page=1)],
        }
    ],
    "segments without page numbers": [
        paged(["one", "two"], image_pages=[1], source="r.pdf", labelled=False)
    ],
    "pictures without page numbers": [
        paged(["one", "two"], image_pages=[None, None], source="r.pdf")
    ],
    "white space between pages": [
        paged(
            ["  one  ", "\n", "three\n"],
            sep="\n\x0c\n",
            image_pages=[1, 2, 3],
            source="w.pdf",
        )
    ],
    "characters outside the basic plane": [
        paged(["😀 un", "𝔡𝔢𝔲𝔵", "trois é"], image_pages=[2, 3], source="u.pdf")
    ],
    "white space languages disagree on": [
        art("\x1c\x1d\x85text\u3000\ufeff", source="ws.txt"),
        art("\ufeff", source="bom.txt"),
        art("\x1f", source="unit.txt"),
    ],
    "pictures whose label shows the file name": [
        art(
            "t",
            source="r.pdf",
            images=[image("p1.png", PICTURE, page=1)],
            extra={"watermark": "{name} · {page}"},
        )
    ],
    "a picture of an odd type": [
        art(source="x.bmp", images=[image("x.bmp", bmp(10, 10), mimetype="image/bmp")])
    ],
    "nothing at all": [],
}


def present_cases() -> list[dict]:
    cases = []
    for scene, artifacts in SCENES.items():
        for sources in (True, False):
            cases.append(
                {
                    "name": f"{scene}: text, sources={sources}",
                    "artifacts": artifacts,
                    "call": "text",
                    "args": {"sources": sources},
                }
            )
            for interleave in (True, False):
                for prompt in (None, "Q?"):
                    args: dict = {"sources": sources, "interleave": interleave}
                    if prompt is not None:
                        args["prompt"] = prompt
                    cases.append(
                        {
                            "name": f"{scene}: parts, sources={sources}, "
                            f"interleave={interleave}, prompt={prompt!r}",
                            "artifacts": artifacts,
                            "call": "parts",
                            "args": args,
                        }
                    )
        for call in ("claude", "openai", "lm15"):
            for prompt in (None, "", "Summarize."):
                args = {} if prompt is None else {"prompt": prompt}
                cases.append(
                    {
                        "name": f"{scene}: {call}, prompt={prompt!r}",
                        "artifacts": artifacts,
                        "call": call,
                        "args": args,
                    }
                )
            cases.append(
                {
                    "name": f"{scene}: {call}, no names, not interleaved",
                    "artifacts": artifacts,
                    "call": call,
                    "args": {"prompt": "Q", "sources": False, "interleave": False},
                }
            )
    return cases


# ---------------------------------------------------------------------------
# chunk
# ---------------------------------------------------------------------------


def chunk_cases() -> list[dict]:
    prose = (
        "Para one is here.\n\nPara two follows it, a bit longer.\n"
        "A new line.\n\nThe third paragraph ends it all with many words."
    )
    pages = paged(
        ["Page one text.", "Page two is longer than one.", "Three."],
        image_pages=[],
        source="d.pdf",
    )
    astral = art("😀" * 30 + " " + "𝔡" * 30, source="e.txt")
    cases = []
    for max_chars in (None, 10, 25, 40, 1000):
        for overlap in (0, 5, 200):
            args: dict = {"overlap": overlap}
            if max_chars is not None:
                args["max_chars"] = max_chars
            for name, a in (
                ("prose", art(prose, source="p.txt")),
                ("pages", pages),
                ("astral", astral),
            ):
                cases.append(
                    {
                        "name": f"{name}, max_chars={max_chars}, overlap={overlap}",
                        "artifacts": [a],
                        "args": args,
                    }
                )
    unbroken = art("x" * 23, source="x.txt")
    cases += [
        {
            "name": "a hard cut when no separator fits",
            "artifacts": [unbroken],
            "args": {"max_chars": 10, "overlap": 3},
        },
        {
            "name": "max_tokens is four characters a token",
            "artifacts": [art(prose, source="p.txt")],
            "args": {"max_tokens": 5, "overlap": 0},
        },
        {
            "name": "the smaller of max_chars and max_tokens wins",
            "artifacts": [art(prose, source="p.txt")],
            "args": {"max_chars": 30, "max_tokens": 5, "overlap": 0},
        },
        {
            "name": "no names",
            "artifacts": [pages, art(prose, source="p.txt")],
            "args": {"max_chars": 30, "overlap": 0, "sources": False},
        },
        {
            "name": "a folder overview is a chunk only with names",
            "artifacts": [
                art("docs/\n└── a.txt", source="docs/", kind="directory"),
                art("hello", source="docs/a.txt"),
            ],
            "args": {"sources": False},
        },
        {
            "name": "white space only is nothing",
            "artifacts": [art(" \n\t ", source="w.txt")],
            "args": {},
        },
        {
            "name": "segments out of range are clamped",
            "artifacts": [
                art(
                    "abcdefghij",
                    source="c.txt",
                    segments=[seg(-5, 4, 1), seg(4, 99, 2), seg(7, 3, 3)],
                )
            ],
            "args": {"max_chars": 6, "overlap": 0},
        },
        {
            "name": "a segment larger than the cap is windowed",
            "artifacts": [
                art("aaaa bbbb cccc dddd", source="c.txt", segments=[seg(0, 19, 1)])
            ],
            "args": {"max_chars": 8, "overlap": 2},
        },
        {
            "name": "max_chars 0 is refused",
            "artifacts": [art("x", source="x")],
            "args": {"max_chars": 0},
        },
        {
            "name": "max_tokens 0 is refused",
            "artifacts": [art("x", source="x")],
            "args": {"max_tokens": 0},
        },
        {
            "name": "overlap is clamped below the cap",
            "artifacts": [art("abcdefghijkl", source="x")],
            "args": {"max_chars": 5, "overlap": 50},
        },
        {
            "name": "negative overlap is none",
            "artifacts": [art("abcdefghijkl", source="x")],
            "args": {"max_chars": 5, "overlap": -3},
        },
        {"name": "nothing", "artifacts": [], "args": {}},
    ]
    return cases


# ---------------------------------------------------------------------------
# tokens and image sizes
# ---------------------------------------------------------------------------


def tokens_cases() -> list[dict]:
    rng = random.Random(15)
    sizes = [
        (1000, 1000),
        (1546, 2000),
        (3000, 100),
        (100, 3000),
        (1, 1),
        (28, 28),
        (29, 29),
        (1075, 1520),
        (2576, 2576),
        (2577, 10),
        (5000, 2),
        (2, 5000),
        (8000, 6000),
        (4784, 1),
        (0, 10),
        (10, -1),
        (3, 2),
        (7, 3),
    ]
    sizes += [(rng.randint(1, 9000), rng.randint(1, 9000)) for _ in range(120)]
    cases = [
        {
            "name": f"{w}x{h} {tier}",
            "call": "image_tokens",
            "width": w,
            "height": h,
            "tier": tier,
        }
        for w, h in sizes
        for tier in ("high", "standard")
    ]
    cases.append(
        {
            "name": "an unknown tier is refused",
            "call": "image_tokens",
            "width": 10,
            "height": 10,
            "tier": "huge",
        }
    )
    pictures = [
        image("a.png", png(1000, 750)),
        image("b.jpg", jpeg(300, 200), mimetype="image/jpeg"),
        image("c.bin", b"not a picture", mimetype="image/png"),
        image("d", None),
    ]
    cases += [
        {
            "name": "text is characters / 4, rounded up",
            "call": "estimate",
            "artifacts": [art("abcdefghi", source="a"), art("😀😀", source="b")],
            "args": {},
        },
        {
            "name": "pictures by their header; an unreadable one costs the most",
            "call": "estimate",
            "artifacts": [art("x", source="p.pdf", images=pictures)],
            "args": {},
        },
        {
            "name": "pictures, standard tier",
            "call": "estimate",
            "artifacts": [art("x", source="p.pdf", images=pictures)],
            "args": {"tier": "standard"},
        },
        {"name": "nothing", "call": "estimate", "artifacts": [], "args": {}},
        {
            "name": "an unknown tier is refused (estimate)",
            "call": "estimate",
            "artifacts": [art("x", source="p.pdf", images=pictures[:1])],
            "args": {"tier": "low"},
        },
        {
            "name": "an unknown tier is refused, even with no pictures",
            "call": "estimate",
            "artifacts": [art("x", source="p.txt")],
            "args": {"tier": "low"},
        },
    ]
    return cases


def imagesize_cases() -> list[dict]:
    samples = {
        "png": png(512, 256),
        "png, truncated": png(512, 256)[:20],
        "jpeg": jpeg(640, 480),
        "jpeg, progressive": jpeg(33, 44, progressive=True),
        "jpeg, after metadata": jpeg(1200, 900, app=3000),
        "jpeg, fill bytes": b"\xff\xd8\xff\xff" + jpeg(5, 6)[2:],
        "jpeg, no frame": b"\xff\xd8\xff\xd9\x00\x00",
        "jpeg, not a marker": b"\xff\xd8\x00\x00\x00\x00",
        "gif": gif(16, 32),
        "gif, too short": b"GIF89a\x10",
        "webp lossy": webp("VP8 ", 300, 200),
        "webp lossless": webp("VP8L", 123, 456),
        "webp extended": webp("VP8X", 4000, 3000),
        "webp, unknown chunk": b"RIFF\0\0\0\0WEBPABCD" + b"\0" * 20,
        "bmp": bmp(64, -48),
        "bmp, OS/2": bmp(17, 19, core=True),
        "bmp, too short": b"BM\0\0",
        "zero width": png(0, 10),
        "nothing": b"",
        "text": b"not an image",
    }
    return [{"name": k, "bytes_b64": b64(v)} for k, v in samples.items()]


def limits_cases() -> list[dict]:
    def img(media: str, data) -> dict:
        return {"type": "image", "media_type": media, "data": data}

    big = {"repeat": "A", "times": 33_000_000}
    eleven = {"repeat": "A", "times": 11_000_000}
    side = b64(png(9000, 100))
    mid = b64(png(2500, 2500))
    text = {"type": "text", "text": 'é"\\\n\x01😀' * 3}
    return [
        {"name": "fits", "provider": "claude", "parts": [text]},
        {
            "name": "too big a request and picture",
            "provider": "claude",
            "parts": [img("image/png", big)],
        },
        {
            "name": "two big jpegs",
            "provider": "claude",
            "parts": [img("image/jpeg", eleven), img("image/jpeg", eleven), text],
        },
        {
            "name": "an odd type",
            "provider": "openai",
            "parts": [img("image/bmp", "Qk0=")],
        },
        {
            "name": "an odd type, Claude",
            "provider": "claude",
            "parts": [img("image/tiff", "AAAA"), img("image/bmp", "Qk0=")],
        },
        {
            "name": "too many pictures",
            "provider": "claude",
            "parts": [img("image/png", b64(png(10, 10)))] * 101,
        },
        {
            "name": "a side too long",
            "provider": "claude",
            "parts": [img("image/png", side)],
        },
        {
            "name": "sides when there are many pictures",
            "provider": "claude",
            "parts": [img("image/png", mid)] * 21,
        },
        {
            "name": "sides when there are few pictures",
            "provider": "claude",
            "parts": [img("image/png", mid)] * 20,
        },
        {
            "name": "the text's JSON size counts",
            "provider": "claude",
            "parts": [{"type": "text", "text": {"repeat": "é", "times": 5_400_000}}],
        },
        {
            "name": "exactly at the limit",
            "provider": "claude",
            "parts": [img("image/jpeg", {"repeat": "A", "times": 10_000_000})] * 3
            + [img("image/jpeg", {"repeat": "A", "times": 1_999_400})],
        },
        {
            "name": "one byte over",
            "provider": "claude",
            "parts": [img("image/jpeg", {"repeat": "A", "times": 10_000_000})] * 3
            + [img("image/jpeg", {"repeat": "A", "times": 1_999_401})],
        },
        {
            "name": "a size that rounds to even",
            "provider": "claude",
            "parts": [img("image/jpeg", {"repeat": "A", "times": 32_249_700})],
        },
    ]


# ---------------------------------------------------------------------------
# wire
# ---------------------------------------------------------------------------


def wire_cases() -> list[dict]:
    good = art(
        "hi",
        source="a.pdf",
        images=[image("p.png", PICTURE, page=1)],
        kind="pdf",
        extra={"n": [1, {"x": None}]},
    )
    cases = [
        {"name": "a round trip keeps everything", "call": "from_wire", "input": [good]},
        {
            "name": "missing keys are filled, source is not invented",
            "call": "from_wire",
            "input": [{"text": "x"}, {}],
        },
        {"name": "not a list", "call": "from_wire", "input": {"text": "hi"}},
        {"name": "an item that is not an object", "call": "from_wire", "input": ["hi"]},
        {
            "name": "text that is not a string",
            "call": "artifact_from_wire",
            "input": {"text": 3},
        },
        {
            "name": "images that are not a list",
            "call": "artifact_from_wire",
            "input": {"images": {}},
        },
        {
            "name": "an image that is not an object",
            "call": "artifact_from_wire",
            "input": {"images": [1]},
        },
        {
            "name": "meta that is not an object",
            "call": "artifact_from_wire",
            "input": {"meta": []},
        },
        {
            "name": "bytes_b64 that is not a string",
            "call": "artifact_from_wire",
            "input": {"images": [{"name": "x", "bytes_b64": 5}]},
        },
        {
            "name": "an image with no data stays without",
            "call": "artifact_from_wire",
            "input": {"images": [{"name": "x", "mimetype": "image/png"}]},
        },
    ]
    for value, label in (
        ("aGk=", "padded"),
        ("", "empty"),
        ("aGl=", "spare bits"),
        ("ab==", "two pads"),
        ("aGk", "missing padding"),
        ("aGk==", "too much padding"),
        ("=", "only padding"),
        ("a", "one character"),
        ("aG=k", "padding inside"),
        ("aGk=\n", "a newline"),
        (" aGk=", "a space"),
        ("aGk=aGk=", "two pieces"),
        ("aG-k", "url-safe alphabet"),
        ("YQ===", "three pads"),
    ):
        cases.append(
            {
                "name": f"base64: {label}",
                "call": "artifact_from_wire",
                "input": {
                    "images": [
                        {"name": "x", "mimetype": "image/png", "bytes_b64": value}
                    ]
                },
            }
        )
    return cases


# ---------------------------------------------------------------------------
# dsl format, pages, options
# ---------------------------------------------------------------------------


def dsl_cases() -> list[dict]:
    samples = [
        ("file.pdf", {}),
        ("file.pdf", {"pages": [1, 4], "images": True}),
        ("f.csv", {"name": "a, b", "id": "42"}),
        ("f.csv", {"q": 'say "hi"', "w": "it's"}),
        ("x", {"t": "true", "n": "-3", "f": "1.5", "r": "2-3", "s": " pad ", "e": ""}),
        ("x", {"b": False, "i": -7, "z": 0, "fl": 2.5}),
        ("x", {"br": "a]b", "bl": "a[b", "c": "a:b"}),
        ("x", {"u": "π 😀", "k": "Sales"}),
    ]
    return [
        {
            "name": f"format {src} {opts}",
            "call": "format",
            "source": src,
            "options": opts,
        }
        for src, opts in samples
    ]


def pages_cases() -> list[dict]:
    values = [
        4,
        "3",
        "2-5",
        "7-",
        "-1",
        "-3-",
        "2--2",
        "1,3,5",
        " 1 - 3 , 5,-2- ",
        "5,1-2,2",
        [2, 5],
        [2, 5, 7],
        0,
        "0",
        "5-2",
        "-2--4",
        "a",
        "",
        ",",
        True,
        "1,,3",
        "1-3-5",
        1.5,
        None,
        "10-",
        "-10",
    ]
    cases = []
    for v in values:
        for total in (1, 5, 10):
            cases.append({"name": f"{v!r} of {total}", "value": v, "total": total})
    return cases


def options_cases() -> list[dict]:
    raws = [
        (".pdf", {"pages": [1, 4], "images": True, "dpi": 150}),
        (".pdf", {"page": "1,3,-1", "pw": "secret", "max_dim": "1568"}),
        (".pdf", {"pagez": 1, "imagez": True, "zzzzzz": 1}),
        (".pdf", {"images": "auto", "ocr": "always", "tables": "yes"}),
        (".pdf", {"images": "maybe", "dpi": "high", "dpi_": 3, "pages": 0}),
        (".pdf", {"dpi": True, "max_pages": 2.5, "password": 1234}),
        (".xlsx", {"sheet": 2, "rows": "50", "max_rows": 10}),
        (".xlsx", {"sheet": True, "limit": "-5"}),
        (".csv", {"sep": ";", "delimiter": ",", "rows": 3}),
        (".html", {"select": [1, 4], "css": "h1, p", "links": "off"}),
        (".html", {"select": [1, 4]}),
        (".pdf", {"password": [3, 4], "ocr_engine": False}),
        (".pptx", {"slides": "2-", "images": False}),
        (
            "file://",
            {"glob": "*.py", "ignore": "tests/", "max_size": "2MB", "tree": "auto"},
        ),
        (
            "file://",
            {"include": "*.md", "max_files": 3, "hidden": "on", "files": "nope"},
        ),
        ("github://", {"branch": "dev", "tag": "v1", "ref": "main"}),
        (".unknown-ext", {"anything": 1}),
    ]
    return [{"name": f"{key} {raw}", "key": key, "raw": raw} for key, raw in raws]


# ---------------------------------------------------------------------------
# summary (the printed one-line summary and the error raised on failures)
# ---------------------------------------------------------------------------


def summary_cases() -> list[dict]:
    long = "x" * 300 + " Install with: pip install attachments[pdf]"
    many = [
        art(source=f"f{i}.pdf", error={"code": "parse-error", "message": f"bad {i}"})
        for i in range(12)
    ]
    return [
        {"name": "one text", "artifacts": [art("hello", source="a.txt")]},
        {
            "name": "thousands and a picture",
            "artifacts": [
                art("x" * 12_345, source="a.txt", images=[image("p", png(1000, 1000))])
            ],
        },
        {
            "name": "thousands of tokens that round to even",
            "artifacts": [art("x" * 13_000, source="a")],
        },
        {
            "name": "millions of tokens that round to even",
            "artifacts": [art({"repeat": "y", "times": 9_000_000}, source="b")],
        },
        {
            "name": "an error with a long message is cut in the middle",
            "artifacts": [
                art("ok", source="a.txt"),
                art(
                    source="b.pdf",
                    error={"code": "missing-dependency", "message": long},
                ),
            ],
        },
        {
            "name": "the same error twice collapses",
            "artifacts": [
                art(source="a.pdf", error={"code": "parse-error", "message": "bad"}),
                art(source="b.pdf", error={"code": "parse-error", "message": "bad"}),
            ],
        },
        {"name": "more than ten errors", "artifacts": many},
        {
            "name": "warnings and notes",
            "artifacts": [
                art(
                    "t",
                    source="a.pdf",
                    warnings=["Unknown option 'pagez'"],
                    note="hint",
                ),
                art(source="b.pdf", note="hint"),
                art(source="c.pdf", note="other"),
            ],
        },
        {"name": "nothing", "artifacts": []},
        {
            "name": "an error without a source",
            "artifacts": [
                {
                    "text": "",
                    "images": [],
                    "audio": [],
                    "video": [],
                    "meta": {"error": {"code": "unpack-error", "message": "gone"}},
                }
            ],
        },
    ]


AREAS = {
    "present": present_cases,
    "chunk": chunk_cases,
    "tokens": tokens_cases,
    "imagesize": imagesize_cases,
    "limits": limits_cases,
    "wire": wire_cases,
    "dsl": dsl_cases,
    "pages": pages_cases,
    "options": options_cases,
    "summary": summary_cases,
}


def main() -> None:
    for area, make in AREAS.items():
        cases = make()
        names = [c["name"] for c in cases]
        duplicates = {n for n in names if names.count(n) > 1}
        if duplicates:
            raise SystemExit(f"{area}: duplicate case names {sorted(duplicates)}")
        for case in cases:
            case["expect"] = run(area, case)
        doc = {
            "area": area,
            "review": "reviewed" if area in REVIEWED else "draft",
            "cases": cases,
        }
        path = HERE / f"{area}.json"
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
        print(f"{path.relative_to(ROOT)}: {len(cases)} cases")


if __name__ == "__main__":
    main()
