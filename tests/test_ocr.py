"""OCR: reading order, turned pages, pages read side by side, settings."""

from __future__ import annotations

import io
import threading

import pytest

from attachments import configure, reset_config
from attachments._processors import _ocr
from attachments._processors._ocr import Line, OcrText, order_lines, read_pages
from attachments.deps import check_dep

needs_ocr = pytest.mark.skipif(not check_dep("ocr").available, reason="needs rapidocr")


def prose(x0: float, y0: float, text: str, width: float = 600) -> Line:
    return Line(x0, y0, x0 + width, y0 + 40, text)


class TestReadingOrder:
    def test_two_columns_are_read_one_after_the_other(self):
        lines = []
        for row in range(6):
            lines.append(prose(100, 100 + 50 * row, f"left line {row} of the article"))
            lines.append(prose(800, 100 + 50 * row, f"right line {row} of the article"))
        text = order_lines(lines)
        assert text.index("left line 5") < text.index("right line 0")
        assert text.splitlines()[0] == "left line 0 of the article"

    def test_aligned_paragraph_breaks_do_not_interleave_columns(self):
        # A paragraph gap at the same height in both columns cuts the page
        # into bands; the columns must still be read whole.
        lines = []
        for y in (100, 150, 200, 330, 380, 430):
            lines.append(prose(100, y, f"left at {y} is a line of prose"))
            lines.append(prose(800, y, f"right at {y} is a line of prose"))
        text = order_lines(lines)
        assert text.index("left at 430") < text.index("right at 100")
        assert "left at 200 is a line of prose\n\nleft at 330" in text  # paragraph

    def test_heading_above_columns_comes_first(self):
        lines = [prose(100, 20, "A heading across the whole page width", 1300)]
        for row in range(4):
            lines.append(prose(100, 120 + 50 * row, f"left {row} is a line of prose"))
            lines.append(prose(800, 120 + 50 * row, f"right {row} is a line of prose"))
        text = order_lines(lines)
        assert text.startswith("A heading across the whole page width\n\nleft 0")
        assert text.index("left 3") < text.index("right 0")

    def test_table_cells_stay_in_rows(self):
        # Short cells with wide gaps are a table, not columns of prose.
        lines = []
        for row, (item, qty, price) in enumerate(
            [
                ("Item", "Qty", "Price"),
                ("Desk lamp", "2", "48.79"),
                ("Stapler", "12", "9.10"),
            ]
        ):
            y = 100 + 50 * row
            lines += [
                prose(100, y, item, 160),
                prose(500, y, qty, 40),
                prose(800, y, price, 90),
            ]
        assert (
            order_lines(lines)
            == "Item   Qty   Price\nDesk lamp   2   48.79\nStapler   12   9.10"
        )

    def test_nothing_read_is_empty_text(self):
        assert order_lines([]) == ""


def _marked(size=(300, 200)):
    """A white picture with a black corner at the top left (its 'upright')."""
    from PIL import Image

    image = Image.new("RGB", size, "white")
    for x in range(10):
        for y in range(10):
            image.putpixel((x, y), (0, 0, 0))
    return image


def _corner(image) -> str:
    """Where the black mark ended up after turning."""
    w, h = image.size
    corners = {"tl": (2, 2), "tr": (w - 3, 2), "bl": (2, h - 3), "br": (w - 3, h - 3)}
    return next(name for name, xy in corners.items() if image.getpixel(xy) == (0, 0, 0))


class TestTurnedPages:
    """recognize() turns a page only when the first reading says it must."""

    @pytest.fixture
    def fake_engine(self, monkeypatch):
        """Reads well only when the mark is top left; sideways boxes when
        the picture is taller than wide (a quarter turn)."""
        calls = []

        def read_lines(image):
            calls.append(_corner(image))
            upright = _corner(image) == "tl"
            score = 0.99 if upright else 0.6
            if image.size[1] > image.size[0]:  # turned a quarter
                return [Line(0, i * 50, 30, i * 50 + 200, "x", score) for i in range(4)]
            return [
                Line(0, i * 50, 400, i * 50 + 30, f"line {i}", score) for i in range(4)
            ]

        monkeypatch.setattr(_ocr, "_read_lines", read_lines)
        return calls

    def test_upright_page_is_read_once(self, fake_engine):
        result = _ocr.recognize(_marked())
        assert (result.turned, len(fake_engine)) == (0, 1)
        assert result.text.startswith("line 0")

    def test_upside_down_page_is_turned_half(self, fake_engine):
        from PIL import Image

        result = _ocr.recognize(_marked().transpose(Image.Transpose.ROTATE_180))
        assert result.turned == 180
        assert result.score == 0.99

    @pytest.mark.parametrize(
        ("transpose", "turn"), [("ROTATE_90", 90), ("ROTATE_270", 270)]
    )
    def test_sideways_page_is_turned_back(self, fake_engine, transpose, turn):
        from PIL import Image

        sideways = _marked().transpose(getattr(Image.Transpose, transpose))
        result = _ocr.recognize(sideways)
        assert result.turned == turn
        assert result.text.startswith("line 0")


def test_poor_reading_both_ways_is_not_turned(monkeypatch):
    """Handwriting reads poorly upright and upside down: keep it upright."""

    def read_lines(image):
        score = 0.62 if _corner(image) == "tl" else 0.7  # turned: a bit higher
        return [Line(0, i * 50, 400, i * 50 + 30, f"line {i}", score) for i in range(4)]

    monkeypatch.setattr(_ocr, "_read_lines", read_lines)
    result = _ocr.recognize(_marked())
    assert result.turned == 0 and result.text.startswith("line 0")


def test_one_confident_symbol_does_not_turn_a_page(monkeypatch):
    """Upside down, a "6" reads as one confident "9": not a reason to turn."""

    def read_lines(image):
        if _corner(image) == "tl":
            return [
                Line(0, i * 50, 400, i * 50 + 30, "To the Governor of", 0.6)
                for i in range(4)
            ]
        return [Line(0, 0, 30, 30, "9", 0.99)]

    monkeypatch.setattr(_ocr, "_read_lines", read_lines)
    assert _ocr.recognize(_marked()).turned == 0


class TestReadPages:
    def test_results_by_key_and_bounded_drawing(self):
        drawn: list[int] = []
        read_count = 0
        lock = threading.Lock()
        most_waiting = 0

        def draw(i):
            drawn.append(i)
            return i

        def read(i):
            nonlocal read_count, most_waiting
            with lock:
                most_waiting = max(most_waiting, len(drawn) - read_count)
                read_count += 1
            return OcrText(f"page {i}")

        results = read_pages(
            ((i, (lambda i=i: draw(i))) for i in range(20)),
            total=20,
            label="t",
            read=read,
            workers=2,
        )
        assert sorted(results) == list(range(20))
        assert results[7].text == "page 7"
        assert drawn == list(range(20))  # drawn in order, in this thread
        assert most_waiting <= 4  # never the whole document in memory

    def test_a_failure_is_raised_after_the_threads_stop(self):
        def read(i):
            if i == 3:
                raise RuntimeError("engine broke")
            return OcrText("ok")

        with pytest.raises(RuntimeError, match="engine broke"):
            read_pages(
                ((i, lambda i=i: i) for i in range(6)), total=6, label="t", read=read
            )

    def test_no_progress_bar_outside_a_terminal(self, capsys):
        read_pages(
            ((i, lambda i=i: i) for i in range(3)), total=3, label="t", read=OcrText
        )
        assert capsys.readouterr().err == ""

    def test_progress_can_be_turned_off(self, monkeypatch):
        monkeypatch.setattr("sys.stderr.isatty", lambda: True, raising=False)
        configure(progress=False)
        try:
            assert _ocr._progress(10, "t") is None
        finally:
            reset_config()


class TestSettings:
    def test_ocr_workers_sets_pages_at_once(self, monkeypatch):
        monkeypatch.setattr(_ocr, "usable_cores", lambda: 16)
        configure(ocr_workers=1)
        try:
            assert _ocr.plan() == (1, 4)
        finally:
            reset_config()

    @pytest.mark.parametrize("bad", [0, -1, 1.5, "two", True])
    def test_bad_ocr_workers_are_refused(self, bad):
        with pytest.raises(ValueError, match="ocr_workers"):
            configure(ocr_workers=bad)
        reset_config()

    def test_environment_variables(self, monkeypatch):
        from attachments.config import get_config

        monkeypatch.setenv("ATTACHMENTS_OCR_WORKERS", "2")
        monkeypatch.setenv("ATTACHMENTS_PROGRESS", "0")
        assert get_config("ocr_workers") == 2
        assert get_config("progress") is False
        monkeypatch.setenv("ATTACHMENTS_PROGRESS", "maybe")
        with pytest.raises(ValueError, match="ATTACHMENTS_PROGRESS"):
            get_config("progress")


def _typeset(text: str, *, width=1400, height=500):
    """A picture of *text* in a real font (PyMuPDF), like a clean scan."""
    pymupdf = pytest.importorskip("pymupdf")
    from PIL import Image

    doc = pymupdf.open()
    page = doc.new_page(width=width / 2, height=height / 2)
    page.insert_textbox(
        pymupdf.Rect(20, 20, width / 2 - 20, height / 2 - 20),
        text,
        fontname="tiro",
        fontsize=14,
    )
    pix = page.get_pixmap(dpi=144)
    return Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")


@needs_ocr
class TestRealEngine:
    TEXT = (
        "The quick brown fox jumps over the lazy dog.\n"
        "Résumé of the café meeting, 2026."
    )

    def test_words_keep_their_spaces_and_accents(self):
        result = _ocr.recognize(_typeset(self.TEXT))
        assert "quick brown fox jumps over the lazy dog" in result.text
        assert "Résumé" in result.text and "café" in result.text
        assert result.turned == 0 and result.score > 0.9

    def test_sideways_page_is_read(self):
        from PIL import Image

        sideways = _typeset(self.TEXT).transpose(Image.Transpose.ROTATE_90)
        result = _ocr.recognize(sideways)
        assert "quick brown fox jumps over the lazy dog" in result.text
        assert result.turned == 90
