"""Tests for named (specialized) processors: ``@processor(..., name=...)``.

=============================================================================
TEST GUIDELINES
=============================================================================

GOOD tests:
    - Choosing: by [processor: NAME], by detect, "default" forces the
      standard one, unknown names warn and are read without
    - base(): the standard result, with the standard options of the call,
      overrides in att()'s vocabulary, service fallback inside base
    - Options: a named processor's own options reach it and not base;
      att.options() lists the named processors
    - Failures are artifacts: a raising detect is a no, a raising or
      non-dict processor is a processing-error naming it
    - meta.extra.processor names what ran

BAD tests:
    - Re-testing the standard processors (their own test files)
=============================================================================
"""

from __future__ import annotations

from pathlib import Path

import pytest

from attachments import (
    Option,
    att,
    make_artifact,
    missing_dep_artifact,
    options,
    processor,
    register_processor,
    reset_processors,
)
from attachments._options import register_options
from attachments._processors import get_named
from attachments.core import _process_single


@pytest.fixture
def notes(tmp_path: Path) -> Path:
    path = tmp_path / "notes.txt"
    path.write_text("INVOICE 42\ntotal: 10")
    return path


def _upper(data: bytes, *, base, **_):
    art = base()
    art["text"] = art["text"].upper()
    return art


class TestChoosing:
    def test_by_name(self, notes: Path):
        processor(".txt", name="shout")(_upper)
        out = att(f"{notes}[processor: shout]")[0]
        assert out["text"] == "INVOICE 42\nTOTAL: 10"
        assert out["meta"]["extra"]["processor"] == "shout"
        assert "warnings" not in out["meta"]

    def test_not_chosen_without_name_or_detect(self, notes: Path):
        processor(".txt", name="shout")(_upper)
        out = att(str(notes))[0]
        assert out["text"] == "INVOICE 42\ntotal: 10"
        assert "processor" not in out["meta"].get("extra", {})

    def test_by_detect_and_default_forces_the_standard(self, notes: Path):
        processor(
            ".txt", name="invoice", detect=lambda data, name: data.startswith(b"INV")
        )(_upper)
        assert att(str(notes))[0]["meta"]["extra"]["processor"] == "invoice"
        standard = att(f"{notes}[processor: default]")[0]
        assert standard["text"] == "INVOICE 42\ntotal: 10"

    def test_detect_sees_bytes_and_file_name(self, notes: Path):
        seen = []
        processor(
            ".txt", name="spy", detect=lambda d, n: seen.append((d[:3], n)) or False
        )(_upper)
        att(str(notes))
        assert seen == [(b"INV", "notes.txt")]

    def test_latest_detect_wins(self, notes: Path):
        yes = lambda d, n: True  # noqa: E731
        processor(".txt", name="first", detect=yes)(_upper)
        processor(".txt", name="second", detect=yes)(_upper)
        assert att(str(notes))[0]["meta"]["extra"]["processor"] == "second"

    def test_raising_detect_counts_as_no(self, notes: Path):
        def broken(data, name):
            raise RuntimeError("bug")

        processor(".txt", name="broken", detect=broken)(_upper)
        out = att(str(notes))[0]
        assert out["text"] == "INVOICE 42\ntotal: 10"

    def test_unknown_name_warns_and_reads_without_it(self, notes: Path):
        processor(".txt", name="invoice")(_upper)
        out = att(f"{notes}[processor: invoce]")[0]
        assert out["meta"]["warnings"] == [
            "Unknown processor 'invoce' for .txt — did you mean 'invoice'? "
            "(available: default, invoice)"
        ]
        assert out["text"] == "INVOICE 42\ntotal: 10"

    def test_unknown_name_where_there_are_none(self, notes: Path):
        out = att(f"{notes}[processor: invoice]")[0]
        assert "only the standard one (default) reads it" in out["meta"]["warnings"][0]
        assert att(f"{notes}[processor: default]")[0]["meta"].get("warnings") is None

    def test_extension_without_a_standard_processor(self, tmp_path: Path):
        """A named processor for a new extension: base is what core would
        do without it (here: read as text)."""
        path = tmp_path / "a.inv"
        path.write_text("hello")
        processor(".inv", name="invoice", detect=lambda d, n: True)(_upper)
        out = att(str(path))[0]
        assert out["text"] == "HELLO"


class TestBase:
    def test_standard_options_reach_base_own_options_do_not(self):
        seen: dict = {}

        @register_processor(".doc9")
        def _standard(data: bytes, **opts):
            seen["standard"] = opts
            return make_artifact(text="standard")

        register_options(".doc9", (Option("pages", "pages"), Option("dpi", "int")))

        @processor(".doc9", name="special", options=(Option("depth", "int"),))
        def _special(data: bytes, *, base, depth=1, **opts):
            seen["special"] = {"depth": depth, **opts}
            return base()

        _process_single(
            "a.doc9",
            b"x",
            options={"processor": "special", "pages": "2-3", "depth": "4"},
        )
        assert seen["special"]["depth"] == 4
        assert seen["special"]["page_start"] == 1  # 0-based, as processors get it
        assert seen["standard"] == {
            "filename": "a.doc9",
            "page_start": 1,
            "page_end": 3,
        }

    def test_base_overrides_in_att_vocabulary(self):
        seen: list = []

        @register_processor(".doc9")
        def _standard(data: bytes, **opts):
            seen.append(opts)
            return make_artifact(text=data.decode())

        register_options(".doc9", (Option("pages", "pages"), Option("dpi", "int")))

        @processor(".doc9", name="special")
        def _special(data: bytes, *, base, **_):
            first = base(pages="5", dpi="300")
            other = base(b"other bytes")
            return make_artifact(text=f"{first['text']}|{other['text']}")

        out = _process_single(
            "a.doc9", b"x", options={"processor": "special", "pages": "1-2"}
        )
        assert out["text"] == "x|other bytes"
        assert seen[0] == {
            "filename": "a.doc9",
            "page_start": 4,
            "page_end": 5,
            "dpi": 300,
        }
        assert seen[1] == {"filename": "a.doc9", "page_start": 0, "page_end": 2}

    def test_base_falls_back_to_the_service(self, monkeypatch):
        @register_processor(".doc9")
        def _missing(data: bytes, **_):
            return missing_dep_artifact("a.doc9", "pdf")

        register_options(".doc9", (Option("pages", "pages"),))
        sent = {}

        def _service(filename, data, key, *, options=None):
            sent.update(options or {})
            return make_artifact(text="from service", meta={"via": "service"})

        monkeypatch.setattr("attachments.core._process_via_service", _service)
        processor(".doc9", name="special", options=(Option("depth", "int"),))(_upper)
        out = _process_single(
            "a.doc9",
            b"x",
            options={"processor": "special", "pages": "2", "depth": 3},
            api_key="k",
        )
        assert out["text"] == "FROM SERVICE"
        assert out["meta"]["via"] == "service"
        assert out["meta"]["extra"]["processor"] == "special"
        assert sent == {"pages": "2"}  # neither processor nor depth

    def test_without_a_base_parameter_it_gets_none(self, notes: Path):
        @processor(".txt", name="plain")
        def _plain(data: bytes, **opts):
            assert "base" not in opts
            return make_artifact(text="plain")

        assert att(f"{notes}[processor: plain]")[0]["text"] == "plain"


class TestFailures:
    def test_raising_processor_is_a_processing_error(self, notes: Path):
        @processor(".txt", name="bad")
        def _bad(data: bytes, **_):
            raise ValueError("oops")

        out = att(f"{notes}[processor: bad]")[0]
        assert out["meta"]["error"]["code"] == "processing-error"
        assert "processor 'bad'" in out["meta"]["error"]["message"]
        assert out["meta"]["extra"]["processor"] == "bad"

    def test_non_artifact_result(self, notes: Path):
        processor(".txt", name="bad")(lambda data, **_: "text")
        out = att(f"{notes}[processor: bad]")[0]
        assert "returned str, not an artifact" in out["meta"]["error"]["message"]

    @pytest.mark.parametrize(
        ("kwargs", "match"),
        [
            ({"name": "default"}, "not 'default'"),
            ({"name": "Has Space"}, "lowercase"),
            ({"detect": lambda d, n: True}, "detect= needs a name="),
        ],
    )
    def test_registration_errors(self, kwargs, match):
        with pytest.raises(ValueError, match=match):
            processor(".txt", **kwargs)

    def test_reset_removes_them(self):
        processor(".txt", name="shout")(_upper)
        reset_processors()
        assert get_named(".txt") == {}


class TestDiscovery:
    def test_options_list_the_named_processors(self):
        processor(
            ".txt",
            name="invoice",
            detect=lambda d, n: False,
            options=(Option("currency", "str", help="ISO code"),),
        )(_upper)
        listed = {o["name"]: o for o in options(".txt")}
        assert listed["processor"]["help"] == (
            "Which processor reads the file: default, invoice (chooses itself)"
        )
        assert listed["currency"]["help"] == "[processor: invoice] ISO code"
        assert "processor" not in {o["name"] for o in options(".csv")}

    def test_own_option_is_unknown_to_the_standard_one(self, notes: Path):
        processor(".txt", name="invoice", options=(Option("currency", "str"),))(_upper)
        out = att(f"{notes}[currency: EUR]")[0]
        assert "Unknown option 'currency'" in out["meta"]["warnings"][0]


def test_watermark_is_applied_after_a_named_processor(tmp_path: Path):
    pytest.importorskip("PIL")
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (400, 300), "navy").save(buf, "PNG")
    photo = tmp_path / "a.png"
    photo.write_bytes(buf.getvalue())
    seen = {}

    @processor(".png", name="special")
    def _special(data: bytes, *, base, **opts):
        seen.update(opts)
        return base()

    out = att(f"{photo}[processor: special, watermark: name]")[0]
    assert "watermark" not in seen
    assert out["meta"]["extra"]["watermark"] == "{name} · {page}"
    assert out["meta"]["extra"]["processor"] == "special"
