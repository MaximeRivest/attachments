"""Reading the text in pictures of pages and photos (OCR).

Engine: RapidOCR 3 with the PP-OCRv6 models bundled in its wheel, on
onnxruntime (``pip install attachments[ocr]``): local, offline, no
download at first use. Every setting below was measured on realistic
scans with known text (``evals/scans``, numbers in its README):

- **No per-line "upside down?" classifier.** On upright pages it turned 2
  of 84 good lines into garbage, and it never rescued a rotated page.
  Whole pages are turned instead (:func:`recognize`): a sideways page is
  recognised by its text boxes being taller than wide, an upside-down one
  by a low recognition score; only then is the page read again, turned.
- **4 threads per page, up to 3 pages at once.** onnxruntime's default (a
  thread per core) was slower on a 48-core machine and used 20 times the
  processor time. Each page being read holds about 0.6 GB.
- **Reading order** follows columns (:func:`order_lines`): the engine
  returns lines top to bottom across the whole page, which mixes the two
  columns of an article line by line.

The engine is created once per process and shared by the threads that
read pages (its inference is thread-safe; checked identical to reading
one page at a time).
"""

from __future__ import annotations

import contextlib
import logging
import os
import statistics
import sys
import threading
import time
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, TypeVar

T = TypeVar("T")

#: onnxruntime threads for one page (see module docstring).
THREADS_PER_PAGE = 4

#: Most pages read at once by default (each holds ~0.6 GB while read).
MAX_WORKERS = 3

#: Median line score under which a page is tried upside down too. Upright
#: text scores ~0.99; upside-down text ~0.65.
TURN_SCORE = 0.8

#: A turned reading replaces the first one only when its score is higher by
#: at least this much (upside-down pages: ~0.65 upright, ~0.99 turned).
TURN_MARGIN = 0.1

_ENGINE: Any = None
_ENGINE_LOCK = threading.Lock()


@dataclass(frozen=True)
class OcrText:
    """What was read on one picture."""

    text: str
    #: Median recognition confidence of the lines (0-1); 0 when no text.
    score: float = 0.0
    #: Clockwise degrees the picture was turned to be read (0, 90, 180, 270).
    turned: int = 0


@dataclass(frozen=True)
class Line:
    """One recognised line: its box (x0, y0, x1, y1), text and score."""

    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    score: float = 1.0

    @property
    def height(self) -> float:
        return self.y1 - self.y0


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


def usable_cores() -> int:
    """Processor cores this process may use (respects CPU affinity)."""
    try:
        return len(os.sched_getaffinity(0))
    except (AttributeError, OSError):  # macOS, Windows
        return os.cpu_count() or 1


def plan() -> tuple[int, int]:
    """``(pages at once, threads per page)`` for this machine.

    ``configure(ocr_workers=N)`` or ``ATTACHMENTS_OCR_WORKERS=N`` sets the
    pages at once; the cores are then shared between them.

    Examples:
        >>> import attachments._processors._ocr as m
        >>> real = m.usable_cores
        >>> for cores in (1, 2, 4, 8, 16, 48):
        ...     m.usable_cores = lambda: cores
        ...     print(cores, m.plan())
        1 (1, 1)
        2 (1, 2)
        4 (1, 4)
        8 (2, 4)
        16 (3, 4)
        48 (3, 4)
        >>> m.usable_cores = real
    """
    from ..config import get_config

    cores = usable_cores()
    workers = get_config("ocr_workers")
    if workers is None:
        workers = max(1, min(MAX_WORKERS, cores // THREADS_PER_PAGE))
    threads = max(1, min(THREADS_PER_PAGE, cores // workers))
    return int(workers), threads


@contextlib.contextmanager
def _quiet() -> Iterator[None]:
    """Silence onnxruntime and rapidocr while the engine loads.

    onnxruntime can print device-discovery warnings from C++ straight to
    file descriptor 2, which no Python setting reaches; fd 2 points at
    devnull meanwhile. Only ever used under ``_ENGINE_LOCK``, never while
    pages are read in threads (swapping fd 2 from several threads at once
    could leave it pointing at devnull).
    """
    loggers = [logging.getLogger(n) for n in ("RapidOCR", "rapidocr", "onnxruntime")]
    levels = [logger.level for logger in loggers]
    for logger in loggers:
        logger.setLevel(logging.CRITICAL + 1)
    saved = devnull = None
    try:
        sys.stderr.flush()
        saved = os.dup(2)
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, 2)
    except (OSError, ValueError):
        pass  # no fd 2 (embedded interpreters): the loggers are enough
    try:
        yield
    finally:
        if saved is not None:
            with contextlib.suppress(OSError):
                os.dup2(saved, 2)
            os.close(saved)
        if devnull is not None:
            os.close(devnull)
        for logger, level in zip(loggers, levels, strict=True):
            logger.setLevel(level)


def engine() -> Any:
    """The shared RapidOCR engine, created and loaded on first use.

    Raises ImportError when rapidocr or onnxruntime is not installed.
    """
    global _ENGINE
    if _ENGINE is None:
        with _ENGINE_LOCK:
            if _ENGINE is None:
                _workers, threads = plan()
                with _quiet():
                    import onnxruntime

                    onnxruntime.set_default_logger_severity(3)  # errors only
                    from rapidocr import RapidOCR

                    new = RapidOCR(
                        params={
                            "Global.use_cls": False,
                            "Global.log_level": "critical",
                            "EngineConfig.onnxruntime.intra_op_num_threads": threads,
                            "EngineConfig.onnxruntime.inter_op_num_threads": 1,
                        }
                    )
                    # Load both models now, quietly, rather than inside the
                    # first page's thread.
                    for load in ("_load_det_model", "_load_rec_model"):
                        if hasattr(new, load):
                            getattr(new, load)()
                _ENGINE = new
    return _ENGINE


# ---------------------------------------------------------------------------
# One picture
# ---------------------------------------------------------------------------


def _read_lines(image: Any) -> list[Line]:
    """Run the engine on a Pillow image: its lines, boxes and scores."""
    result = engine()(image)
    boxes = getattr(result, "boxes", None)
    texts = getattr(result, "txts", None)
    if boxes is None or not texts:
        return []
    scores = getattr(result, "scores", None) or [1.0] * len(texts)
    lines = []
    for box, text, score in zip(boxes, texts, scores, strict=False):
        xs = [float(p[0]) for p in box]
        ys = [float(p[1]) for p in box]
        if str(text).strip():
            lines.append(
                Line(
                    min(xs), min(ys), max(xs), max(ys), str(text).strip(), float(score)
                )
            )
    return lines


def _score(lines: list[Line]) -> float:
    """Median line score; 0 when nothing was read."""
    return statistics.median(x.score for x in lines) if lines else 0.0


def _confident_chars(lines: list[Line]) -> float:
    """Characters read, each weighted by its line's score."""
    return sum(len(x.text) * x.score for x in lines)


def _sideways(lines: list[Line]) -> bool:
    """Text boxes taller than wide: the page is turned a quarter.

    Most of them on a page of text; all of them when there are only one
    or two (on an upright page a lone tall box can be a vertical label).
    """
    if not lines:
        return False
    tall = sum(1 for x in lines if x.height > (x.x1 - x.x0))
    return tall == len(lines) if len(lines) < 3 else tall > len(lines) / 2


def recognize(image: Any) -> OcrText:
    """Read the text of one picture (a Pillow image), upright or turned.

    Read as it is first. A sideways page is read turned both ways, an
    upside-down one (low score) turned half a turn; a turned reading wins
    only when it is confident (``TURN_SCORE``), clearly better
    (``TURN_MARGIN``) and reads at least as much text. Upright pages are
    read once.
    """
    from PIL import Image

    def attempt(turn: int) -> tuple[list[Line], float]:
        turned = {
            0: image,
            90: image.transpose(Image.Transpose.ROTATE_270),  # clockwise
            180: image.transpose(Image.Transpose.ROTATE_180),
            270: image.transpose(Image.Transpose.ROTATE_90),
        }[turn]
        lines = _read_lines(turned)
        return lines, _score(lines)

    best_turn = 0
    best, best_score = attempt(0)
    if _sideways(best):
        candidates: tuple[int, ...] = (90, 270)
    elif best and best_score < TURN_SCORE:
        candidates = (180,)
    else:
        candidates = ()
    for turn in candidates:
        lines, score = attempt(turn)
        # Only a confident, clearly better reading turns the page: an
        # upright handwritten page reads poorly both ways, and chance must
        # not swap its text for garbage (seen on olmOCR-bench old scans).
        # It must also read at least as much text: upside down, the "6" on
        # an envelope reads as one confident "9" while the upright
        # handwriting gives many uncertain lines.
        if (
            score >= TURN_SCORE
            and score > best_score + TURN_MARGIN
            and _confident_chars(lines) >= _confident_chars(best)
        ):
            best_turn, best, best_score = turn, lines, score
    return OcrText(order_lines(best), round(best_score, 3), best_turn)


# ---------------------------------------------------------------------------
# Reading order
# ---------------------------------------------------------------------------

#: A column gutter is at least this many line heights wide.
_GUTTER = 1.2
#: Both sides of a gutter need this many lines, of this median length
#: (characters), to be columns of prose rather than the cells of a table.
_COLUMN_LINES = 3
_COLUMN_CHARS = 20
#: A gap of this many line heights between two lines starts a paragraph.
_PARAGRAPH = 0.9


def _gaps(spans: list[tuple[float, float]], minimum: float) -> list[float]:
    """Middles of the empty stretches between *spans* at least *minimum* wide."""
    spans = sorted(spans)
    gaps, reach = [], spans[0][1]
    for start, end in spans[1:]:
        if start - reach >= minimum:
            gaps.append((reach + start) / 2)
        reach = max(reach, end)
    return gaps


def _prose(lines: list[Line]) -> bool:
    return (
        len(lines) >= _COLUMN_LINES
        and statistics.median(len(x.text) for x in lines) >= _COLUMN_CHARS
    )


def _column_cut(lines: list[Line], height: float) -> float | None:
    """x of a gutter running the full height, between two columns of prose."""
    for x in _gaps([(x.x0, x.x1) for x in lines], _GUTTER * height):
        left = [line for line in lines if line.x1 <= x]
        right = [line for line in lines if line.x0 >= x]
        if _prose(left) and _prose(right):
            return x
    return None


def _bands(lines: list[Line], height: float) -> list[list[Line]]:
    """Split at horizontal gaps (a heading above columns), top to bottom."""
    cuts = _gaps([(x.y0, x.y1) for x in lines], 0.5 * height)
    bands: list[list[Line]] = [[] for _ in range(len(cuts) + 1)]
    for line in lines:
        middle = (line.y0 + line.y1) / 2
        bands[sum(1 for c in cuts if middle > c)].append(line)
    return [band for band in bands if band]


def _split(lines: list[Line], cut: float) -> tuple[list[Line], list[Line]]:
    left = [x for x in lines if (x.x0 + x.x1) / 2 < cut]
    return left, [x for x in lines if (x.x0 + x.x1) / 2 >= cut]


def _blocks(lines: list[Line], height: float) -> list[list[Line]]:
    """Lines grouped into reading blocks, in reading order.

    Columns first: a gutter through the whole region splits it, left
    block before right. Otherwise the region is cut into horizontal bands
    (so a full-width heading can sit above columns); neighbouring bands
    split by the same gutter are joined again, so a paragraph break that
    happens to line up in both columns does not interleave them. Every
    recursive call gets fewer lines, so this ends.
    """
    cut = _column_cut(lines, height)
    if cut is not None:
        left, right = _split(lines, cut)
        return _blocks(left, height) + _blocks(right, height)
    bands = _bands(lines, height)
    if len(bands) == 1:
        return [lines]
    merged: list[list[Line]] = []
    for band in bands:
        if merged and _column_cut(merged[-1] + band, height) is not None:
            merged[-1] = merged[-1] + band
        else:
            merged.append(band)
    out: list[list[Line]] = []
    for band in merged:
        out.extend(_blocks(band, height))
    return out


def _rows(lines: list[Line]) -> list[list[Line]]:
    """Lines sharing a baseline (the cells of a table row), top to bottom."""
    rows: list[list[Line]] = []
    for line in sorted(lines, key=lambda x: (x.y0 + x.y1) / 2):
        middle = (line.y0 + line.y1) / 2
        if rows:
            last = rows[-1]
            top = min(x.y0 for x in last)
            bottom = max(x.y1 for x in last)
            if top < middle < bottom:
                last.append(line)
                continue
        rows.append([line])
    return [sorted(row, key=lambda x: x.x0) for row in rows]


def _row_text(row: list[Line], height: float) -> str:
    """Cells of a row joined: one space, or three across a wide gap."""
    text = row[0].text
    for before, after in zip(row, row[1:], strict=False):
        text += ("   " if after.x0 - before.x1 > height else " ") + after.text
    return text


def order_lines(lines: list[Line]) -> str:
    """The text of recognised lines in reading order.

    Columns are read one after the other, rows top to bottom, the cells of
    a row left to right; a blank line marks a paragraph (a gap of about a
    line or more).

    Examples:
        >>> L = lambda x0, y0, text, w=600: Line(x0, y0, x0 + w, y0 + 40, text)
        >>> two_columns = [
        ...     L(100, 100, "left one is a line of prose"),
        ...     L(800, 104, "right one is a line of prose"),
        ...     L(100, 150, "left two is a line of prose"),
        ...     L(800, 154, "right two is a line of prose"),
        ...     L(100, 200, "left three is a line of prose"),
        ...     L(800, 204, "right three is a line of prose"),
        ... ]
        >>> print(order_lines(two_columns))
        left one is a line of prose
        left two is a line of prose
        left three is a line of prose
        <BLANKLINE>
        right one is a line of prose
        right two is a line of prose
        right three is a line of prose
        >>> table = [
        ...     L(100, 100, "Item", 100),
        ...     L(500, 100, "Qty", 60),
        ...     L(700, 100, "Price", 90),
        ...     L(100, 150, "Desk lamp", 160),
        ...     L(500, 150, "2", 20),
        ...     L(700, 150, "48.79", 90),
        ... ]
        >>> print(order_lines(table))
        Item   Qty   Price
        Desk lamp   2   48.79
    """
    if not lines:
        return ""
    height = statistics.median(x.height for x in lines)
    paragraphs: list[str] = []
    for block in _blocks(lines, height):
        current: list[str] = []
        previous_bottom: float | None = None
        for row in _rows(block):
            top = min(x.y0 for x in row)
            if (
                previous_bottom is not None
                and top - previous_bottom > _PARAGRAPH * height
            ):
                paragraphs.append("\n".join(current))
                current = []
            current.append(_row_text(row, height))
            previous_bottom = max(x.y1 for x in row)
        if current:
            paragraphs.append("\n".join(current))
    return "\n\n".join(paragraphs)


# ---------------------------------------------------------------------------
# Many pictures, side by side, with progress
# ---------------------------------------------------------------------------


def _progress(total: int, label: str) -> Any:
    """A progress bar on a terminal or in a notebook, else nothing.

    Shown only after a second (short jobs stay silent), never in logs or
    pipes, and not at all with ``configure(progress=False)`` or
    ``ATTACHMENTS_PROGRESS=0``.
    """
    from ..config import get_config

    if not get_config("progress") or total < 2:
        return None
    try:
        from tqdm import tqdm
    except ImportError:
        return None
    kwargs = dict(total=total, desc=label, unit="page", delay=1.0, leave=False)
    if "ipykernel" in sys.modules:  # Jupyter: stderr is not a terminal there
        try:
            import ipywidgets  # noqa: F401  (the notebook bar needs it)
            from tqdm.notebook import tqdm as notebook_tqdm

            return notebook_tqdm(**kwargs)
        except ImportError:
            return tqdm(file=sys.stderr, **kwargs)
    if not (hasattr(sys.stderr, "isatty") and sys.stderr.isatty()):
        return None
    return tqdm(file=sys.stderr, **kwargs)


def read_pages(
    pages: Iterable[tuple[int, Callable[[], Any]]],
    *,
    total: int,
    label: str,
    read: Callable[[Any], T],
    workers: int | None = None,
) -> dict[int, T]:
    """Read many pictures, several at once; ``{key: read(picture)}``.

    *pages* yields ``(key, draw)``: ``draw()`` makes what *read* takes (a
    picture of a page) and is called in this thread, in order, just before
    it is read, because PyMuPDF must not be used from several threads. At
    most one picture per worker waits, so a 500-page scan does not fill
    memory. *read* runs in worker threads. An exception from *read* stops
    the work and is raised here, after the threads finish.
    """
    if workers is None:
        workers = plan()[0]
    results: dict[int, T] = {}
    bar = _progress(total, label)
    started = time.monotonic()
    try:
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="ocr") as pool:
            pending: list[tuple[int, Future[T]]] = []

            def settle_oldest() -> None:
                key, future = pending.pop(0)
                results[key] = future.result()
                if bar is not None:
                    bar.update(1)

            for key, draw in pages:
                while len(pending) > workers:  # one drawn ahead per worker
                    settle_oldest()
                pending.append((key, pool.submit(read, draw())))
            while pending:
                settle_oldest()
    finally:
        if bar is not None:
            bar.close()
    logging.getLogger("attachments.ocr").debug(
        "%s: %d pages in %.1fs", label, len(results), time.monotonic() - started
    )
    return results


def lighton_reader(url: str) -> Callable[[Any], OcrText]:
    """A ``read`` function for :func:`read_pages` using a LightOnOCR endpoint."""
    import io

    from .image import _ocr_image_bytes_lighton

    def read(image: Any) -> OcrText:
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return OcrText(_ocr_image_bytes_lighton(buffer.getvalue(), url=url))

    return read
