"""
Tests for the Artifacts container (attachments._artifacts).

=============================================================================
TEST GUIDELINES FOR ARTIFACTS
=============================================================================

GOOD tests:
    - repr is a bounded summary (never dumps text/bytes — even with a
      multi-MB image attached)
    - str()/.text == render_text() (v1 muscle memory: print(ctx))
    - Properties (.images/.errors), shortcuts (.claude/.openai/.chunk)
    - list-subclass behavior: slices/concat stay Artifacts, single index
      stays a plain dict, json.dumps still works
    - _repr_markdown_ thumbnail capping (count and per-image size) and
      wire-form (bytes_b64) handling
    - att() returns Artifacts on success AND error paths

BAD tests:
    - Re-testing render_text/to_*_messages/chunk internals (test_render.py)
    - IR shape conformance (test_conformance.py)

=============================================================================
"""

from __future__ import annotations

import base64
import json

from attachments import Artifacts, att, render_text
from attachments.types import ERROR_PARSE, error_artifact, make_artifact

ONE_MIB = 1024 * 1024


def _text_artifact(text: str, source: str = "a.txt") -> dict:
    return make_artifact(text=text, meta={"source": source})


def _image_artifact(
    source: str = "p.pdf", *, name: str = "p.png", payload: bytes = b"\x89PNG"
) -> dict:
    return make_artifact(
        images=[{"name": name, "mimetype": "image/png", "bytes": payload}],
        meta={"source": source},
    )


# =============================================================================
# repr — summary line + error lines, never text/bytes
# =============================================================================


def test_repr_summary_line_counts():
    arts = Artifacts(
        [
            _text_artifact("hello world"),
            _image_artifact(),
            error_artifact("broken.pdf", ERROR_PARSE, "not a PDF"),
        ]
    )
    assert (
        repr(arts).splitlines()[0]
        == "<Artifacts: 3 artifacts | 11 chars | ~3 tokens | 1 image | 1 error>"
    )


def test_repr_singular_and_omits_zero_sections():
    arts = Artifacts([_text_artifact("hi")])
    assert repr(arts) == "<Artifacts: 1 artifact | 2 chars | ~1 tokens>"


def test_repr_thousands_separator():
    arts = Artifacts([_text_artifact("x" * 14210)])
    assert repr(arts) == "<Artifacts: 1 artifact | 14,210 chars | ~3.6k tokens>"


def test_repr_error_lines_with_source_code_and_truncated_message():
    long_message = "boom " * 100  # 500 chars
    arts = Artifacts(
        [
            error_artifact("a.pdf", ERROR_PARSE, "short"),
            error_artifact("b.pdf", "unpack-error", long_message),
        ]
    )
    lines = repr(arts).splitlines()
    assert lines[0] == "<Artifacts: 2 artifacts | 0 chars | ~0 tokens | 2 errors>"
    assert lines[1] == "  ! a.pdf: parse-error — short"
    # Over-long messages are middle-truncated to 160 chars with an ellipsis.
    prefix = "  ! b.pdf: unpack-error — "
    assert lines[2].startswith(prefix + "boom ")
    assert "…" in lines[2]
    assert len(lines[2]) == len(prefix) + 160
    assert len(lines) == 3


def test_repr_error_truncation_keeps_the_pip_install_remedy():
    """The actionable fix at the END of dep messages must survive clipping."""
    remedy = "Install with: pip install attachments[pdf]"
    message = (
        "Processing 'a-quite-long-filename-from-some-deep-directory.pdf' requires "
        "optional dependencies for 'pdf' (missing: pypdf|PyPDF2, pymupdf, and a "
        "bunch of padding to push this over the cap). " + remedy
    )
    arts = Artifacts([error_artifact("x.pdf", "missing-dependency", message)])
    line = repr(arts).splitlines()[1]
    assert line.endswith(remedy)
    assert "…" in line
    md_line = arts._repr_markdown_().splitlines()[2]
    assert md_line.endswith(remedy)


def test_repr_caps_error_lines_and_points_to_errors():
    """60 distinct failures must not produce a 61-line repr (cap at 10 + note)."""
    arts = Artifacts(
        [
            error_artifact(f"bad{i:02d}.pdf", ERROR_PARSE, f"broken {i:02d}")
            for i in range(60)
        ]
    )
    lines = repr(arts).splitlines()
    assert lines[0] == "<Artifacts: 60 artifacts | 0 chars | ~0 tokens | 60 errors>"
    assert len(lines) == 12  # summary + 10 error lines + overflow note
    assert lines[1] == "  ! bad00.pdf: parse-error — broken 00"
    assert lines[10] == "  ! bad09.pdf: parse-error — broken 09"
    assert lines[11] == "  … +50 more errors (see .errors)"
    # .errors still exposes everything.
    assert len(arts.errors) == 60


def test_repr_no_overflow_note_at_exactly_the_cap():
    arts = Artifacts(
        [error_artifact(f"bad{i}.pdf", ERROR_PARSE, f"broken {i}") for i in range(10)]
    )
    lines = repr(arts).splitlines()
    assert len(lines) == 11
    assert "more error" not in lines[-1]


# =============================================================================
# repr dedupe — identical lines collapse to one "(xN)" line, unique cap
# =============================================================================


def test_repr_dedupes_identical_error_lines():
    """60 identical failures collapse to ONE line with (x60), no overflow."""
    arts = Artifacts(
        [error_artifact(f"bad{i:02d}.pdf", ERROR_PARSE, "broken") for i in range(60)]
    )
    lines = repr(arts).splitlines()
    assert len(lines) == 2
    assert lines[1] == "  ! parse-error — broken (x60)"
    assert len(arts.errors) == 60  # .errors keeps every entry


def test_repr_dedupes_identical_note_lines_40_scanned_pdfs():
    """A directory of 40 scanned PDFs reprs as ONE note line with (x40)."""
    note = (
        "No text layer (scanned?) - pip install attachments[ocr], "
        "or the free hosted tier: attachments.dev"
    )
    arts = Artifacts(
        [
            make_artifact(meta={"source": f"scan-{i:02d}.pdf", "note": note})
            for i in range(40)
        ]
    )
    lines = repr(arts).splitlines()
    assert len(lines) == 2
    assert lines[1] == f"  * {note} (x40)"
    assert "more note" not in repr(arts)


def test_repr_dedupe_preserves_first_seen_order_for_mixed_notes():
    arts = Artifacts(
        [
            make_artifact(meta={"source": "a.pdf", "note": "alpha"}),
            make_artifact(meta={"source": "b.pdf", "note": "beta"}),
            make_artifact(meta={"source": "c.pdf", "note": "alpha"}),
        ]
    )
    lines = repr(arts).splitlines()
    assert lines[1] == "  * alpha (x2)"
    assert lines[2] == "  * b.pdf: beta"


def test_repr_singleton_note_keeps_its_source():
    arts = Artifacts([make_artifact(meta={"source": "scan.pdf", "note": "hint"})])
    assert repr(arts).splitlines()[1] == "  * scan.pdf: hint"


def test_repr_cap_counts_unique_lines():
    """One message repeated 30x + 11 unique ones -> 1 (x30) line + 10 + overflow."""
    arts = Artifacts(
        [error_artifact(f"dup{i}.pdf", ERROR_PARSE, "same") for i in range(30)]
        + [
            error_artifact(f"u{i:02d}.pdf", ERROR_PARSE, f"odd {i:02d}")
            for i in range(11)
        ]
    )
    lines = repr(arts).splitlines()
    assert lines[1] == "  ! parse-error — same (x30)"
    assert lines[2] == "  ! u00.pdf: parse-error — odd 00"
    assert lines[10] == "  ! u08.pdf: parse-error — odd 08"
    assert lines[11] == "  … +2 more errors (see .errors)"
    assert len(lines) == 12


def test_repr_dedupe_is_on_clipped_content():
    """Messages identical after clipping collapse together."""
    remedy = "Install with: pip install attachments[pdf]"
    long_a = "x" * 200 + " stuff " + "y" * 200 + " " + remedy
    long_b = "x" * 200 + " STUFF " + "y" * 200 + " " + remedy  # differs mid-clip
    arts = Artifacts(
        [
            error_artifact("a.pdf", "missing-dependency", long_a),
            error_artifact("b.pdf", "missing-dependency", long_b),
        ]
    )
    lines = repr(arts).splitlines()
    assert len(lines) == 2  # the clipped renderings are identical -> one line
    assert lines[1].endswith(f"{remedy} (x2)")


def test_repr_markdown_dedupes_identical_error_admonitions():
    arts = Artifacts(
        [error_artifact(f"bad{i:02d}.pdf", ERROR_PARSE, "broken") for i in range(40)]
    )
    md = arts._repr_markdown_()
    assert md.count("> ⚠️") == 1
    assert "> ⚠️ parse-error — broken (x40)" in md
    assert "more error" not in md


def test_repr_never_leaks_bytes_or_text():
    """A 5MB fake image and huge text must not blow up the repr."""
    arts = Artifacts(
        [
            make_artifact(
                text="t" * 100_000,
                images=[
                    {
                        "name": "huge.png",
                        "mimetype": "image/png",
                        "bytes": b"\xff" * (5 * ONE_MIB),
                    }
                ],
                meta={"source": "huge.pdf"},
            )
        ]
    )
    rendered = repr(arts)
    assert len(rendered) < 2000
    assert "tttt" not in rendered
    assert "\\xff" not in rendered


# =============================================================================
# .tokens — fast ceil(chars/4) estimate + compact repr formatting
# =============================================================================


def test_tokens_is_ceil_of_total_chars_over_four():
    assert Artifacts([]).tokens == 0
    assert Artifacts([_text_artifact("abcd")]).tokens == 1
    assert Artifacts([_text_artifact("abcde")]).tokens == 2
    # Summed across artifacts BEFORE the ceil (2 + 2 chars -> 1 token).
    assert Artifacts([_text_artifact("ab"), _text_artifact("cd")]).tokens == 1
    # Error-only artifacts have no text.
    assert Artifacts([error_artifact("x.pdf", ERROR_PARSE, "bad")]).tokens == 0


def test_tokens_formatting_boundaries_in_repr():
    # 999 tokens (3996 chars) — exact count, no suffix.
    arts = Artifacts([_text_artifact("x" * 3996)])
    assert repr(arts) == "<Artifacts: 1 artifact | 3,996 chars | ~999 tokens>"
    # 1000 tokens (4000 chars) — 'k' suffix, '.0' stripped.
    arts = Artifacts([_text_artifact("x" * 4000)])
    assert repr(arts) == "<Artifacts: 1 artifact | 4,000 chars | ~1k tokens>"


def test_tokens_million_formatting_in_repr():
    arts = Artifacts([_text_artifact("x" * 4_800_000)])  # 1.2M tokens
    assert repr(arts) == "<Artifacts: 1 artifact | 4,800,000 chars | ~1.2M tokens>"


def test_tokens_segment_sits_between_chars_and_images():
    arts = Artifacts([_image_artifact()])
    assert repr(arts) == "<Artifacts: 1 artifact | 0 chars | ~0 tokens | 1 image>"


def test_repr_markdown_summary_includes_tokens():
    arts = Artifacts([_text_artifact("abcd")])
    assert "1 artifact | 4 chars | ~1 tokens" in arts._repr_markdown_()


def test_chunk_shortcut_passes_max_tokens():
    arts = Artifacts([_text_artifact("alpha beta gamma", source="t.txt")])
    assert arts.chunk(max_tokens=3, overlap=0) == arts.chunk(max_chars=12, overlap=0)


# =============================================================================
# str / properties
# =============================================================================


def test_str_is_render_text():
    arts = Artifacts([_text_artifact("Alpha."), _image_artifact()])
    assert str(arts) == render_text(arts)
    assert "## a.txt" in str(arts)


def test_text_property_matches_str():
    arts = Artifacts([_text_artifact("Alpha.")])
    assert arts.text == str(arts) == "## a.txt\nAlpha."


def test_images_property_flattens_across_artifacts():
    arts = Artifacts(
        [
            _image_artifact(name="a.png"),
            _text_artifact("no images"),
            _image_artifact(name="b.png"),
        ]
    )
    assert [img["name"] for img in arts.images] == ["a.png", "b.png"]


def test_errors_property_shape():
    arts = Artifacts(
        [
            _text_artifact("fine"),
            error_artifact("f.pdf", ERROR_PARSE, "bad"),
            make_artifact(meta={"error": {"code": "x", "message": "y"}}),
        ]
    )
    assert arts.errors == [
        {"source": "f.pdf", "code": "parse-error", "message": "bad"},
        {"source": "(unknown)", "code": "x", "message": "y"},
    ]


# =============================================================================
# .claude() / .openai() / .chunk() — prompt optional end-to-end
# =============================================================================


def test_claude_without_prompt_has_no_trailing_prompt_block():
    arts = Artifacts([_text_artifact("hi")])
    blocks = arts.claude()[0]["content"]
    assert [b["type"] for b in blocks] == ["text"]
    assert blocks[0]["text"] == arts.text


def test_claude_with_prompt_appends_text_block():
    arts = Artifacts([_text_artifact("hi")])
    blocks = arts.claude("Summarize.")[0]["content"]
    assert blocks[-1] == {"type": "text", "text": "Summarize."}


def test_openai_without_and_with_prompt():
    arts = Artifacts([_text_artifact("hi")])
    assert [p["type"] for p in arts.openai()[0]["content"]] == ["text"]
    parts = arts.openai("Go")[0]["content"]
    assert parts[-1] == {"type": "text", "text": "Go"}


def test_chunk_shortcut_passes_kwargs():
    arts = Artifacts([_text_artifact("alpha beta gamma", source="t.txt")])
    assert arts.chunk(max_chars=12, overlap=0) == [
        "## t.txt\nalpha beta ",
        "## t.txt\ngamma",
    ]


# =============================================================================
# list behavior — slices/concat stay Artifacts; elements stay dicts
# =============================================================================


def test_slice_returns_artifacts_single_index_returns_dict():
    arts = Artifacts([_text_artifact("x"), _text_artifact("y")])
    assert type(arts[:1]) is Artifacts
    assert type(arts[::-1]) is Artifacts
    assert type(arts[0]) is dict


def test_concat_returns_artifacts_both_ways():
    a = Artifacts([_text_artifact("x")])
    b = Artifacts([_text_artifact("y")])
    assert type(a + b) is Artifacts
    assert len(a + b) == 2
    # Plain list on either side still lands in the family.
    assert type(a + [_text_artifact("z")]) is Artifacts
    assert type([_text_artifact("z")] + a) is Artifacts


def test_json_dumps_still_works():
    arts = Artifacts([_text_artifact("hi")])
    assert json.loads(json.dumps(arts))[0]["text"] == "hi"


def test_att_returns_artifacts_on_success_and_error_paths(tmp_path):
    f = tmp_path / "note.txt"
    f.write_text("hello")
    ok = att(str(f))
    assert type(ok) is Artifacts and not ok.errors
    bad = att(str(tmp_path / "missing.nope"))
    assert type(bad) is Artifacts
    assert bad.errors and bad.errors[0]["code"] == "unpack-error"


# =============================================================================
# _repr_markdown_ — summary, admonitions, preview, capped thumbnails
# =============================================================================


def test_repr_markdown_summary_errors_and_preview_truncation():
    arts = Artifacts(
        [
            _text_artifact("z" * 700, source="big.txt"),
            error_artifact("broken.pdf", ERROR_PARSE, "not a PDF"),
        ]
    )
    md = arts._repr_markdown_()
    assert md.startswith(
        "### Artifacts — 2 artifacts | 700 chars | ~175 tokens | 1 error"
    )
    assert "> ⚠️ `broken.pdf`: parse-error — not a PDF" in md
    assert "```text" in md
    # Preview is capped at 600 chars of the assembled text (headers count).
    assert arts.text[:600] in md
    assert arts.text[:601] not in md
    remaining = len(arts.text) - 600
    assert f"… ({remaining} more chars)" in md


def test_repr_markdown_caps_error_admonitions_and_points_to_errors():
    arts = Artifacts(
        [
            error_artifact(f"bad{i:02d}.pdf", ERROR_PARSE, f"broken {i:02d}")
            for i in range(60)
        ]
    )
    md = arts._repr_markdown_()
    assert md.count("> ⚠️") == 10
    assert "> … +50 more errors — see `.errors`" in md


def test_repr_markdown_fence_survives_backticks_in_preview():
    """Text containing ``` must not escape the preview fence (CommonMark)."""
    text = "intro\n```bash\npip install x\n```\n# not a real heading\ntail"
    arts = Artifacts([_text_artifact(text, source="README.md")])
    md = arts._repr_markdown_()
    # The fence is longer than any backtick run in the preview...
    assert "````text\n" in md
    body = md.split("````text\n", 1)[1]
    preview, _, after = body.partition("\n````")
    # ...so the whole preview (inner ``` included) stays inside the block.
    assert "# not a real heading" in preview
    assert "```bash" in preview
    assert "# not a real heading" not in after


def test_repr_markdown_fence_grows_past_longer_backtick_runs():
    arts = Artifacts([_text_artifact("a ````` run", source="t.md")])
    md = arts._repr_markdown_()
    assert "``````text\n" in md
    assert md.rstrip().endswith("``````")


def test_repr_markdown_plain_text_keeps_three_backtick_fence():
    arts = Artifacts([_text_artifact("no backticks here", source="t.txt")])
    md = arts._repr_markdown_()
    assert "```text\n" in md
    assert "````" not in md


def test_repr_markdown_caps_thumbnails_at_four_and_notes_more():
    arts = Artifacts(
        [_image_artifact(name=f"img-{i}.png", payload=b"\x89P") for i in range(6)]
    )
    md = arts._repr_markdown_()
    assert md.count("![") == 4
    assert "+2 more images" in md


def test_repr_markdown_skips_oversized_images():
    arts = Artifacts(
        [
            _image_artifact(name="small.png", payload=b"ok"),
            _image_artifact(name="big.png", payload=b"\xff" * (ONE_MIB + 1)),
        ]
    )
    md = arts._repr_markdown_()
    assert "![small.png](data:image/png;base64," in md
    assert "![big.png]" not in md
    assert "+1 more image" in md
    assert len(md) < 5000  # the 1MB+ payload never leaks into the markdown


def test_repr_markdown_handles_wire_form_bytes_b64():
    b64 = base64.b64encode(b"\x89PNG").decode("ascii")
    arts = Artifacts(
        [
            make_artifact(
                images=[{"name": "w.png", "mimetype": "image/png", "bytes_b64": b64}],
                meta={"source": "w.pdf"},
            )
        ]
    )
    assert f"![w.png](data:image/png;base64,{b64})" in arts._repr_markdown_()


def test_repr_markdown_wire_form_oversized_is_skipped():
    b64 = base64.b64encode(b"\xff" * (ONE_MIB + 8)).decode("ascii")
    arts = Artifacts(
        [
            make_artifact(
                images=[{"name": "w.png", "mimetype": "image/png", "bytes_b64": b64}],
                meta={"source": "w.pdf"},
            )
        ]
    )
    md = arts._repr_markdown_()
    assert "![w.png]" not in md
    assert "+1 more image" in md
