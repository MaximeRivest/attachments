"""Tests for attachments.render — last-mile consumers of artifact lists.

Covers render_text, to_claude_content, to_claude_messages,
to_openai_messages, and chunk: hand-built artifacts, wire-form (bytes_b64)
images, base64 round-trips, exact chunk boundaries, overlap verification,
segment packing vs window fallback, determinism, and one real att() smoke.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from attachments.render import (
    chunk,
    render_text,
    to_claude_content,
    to_claude_messages,
    to_openai_messages,
)
from attachments.types import make_artifact

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + bytes(range(32))


def _text_artifact(text: str, source: str = "doc.txt") -> dict:
    return make_artifact(text=text, meta={"source": source})


def _image_artifact(source: str = "scan.pdf", name: str = "scan-1.png") -> dict:
    return make_artifact(
        images=[{"name": name, "mimetype": "image/png", "bytes": PNG_BYTES}],
        meta={"source": source},
    )


def _body(chunk_str: str) -> str:
    """Strip the '## <source>' header line from a chunk."""
    return chunk_str.split("\n", 1)[1]


# =============================================================================
# render_text
# =============================================================================


def test_render_text_headers_and_blank_line_separation():
    artifacts = [
        _text_artifact("Alpha.", source="a.txt"),
        _text_artifact("Beta.", source="b.txt"),
    ]
    assert render_text(artifacts) == "## a.txt\nAlpha.\n\n## b.txt\nBeta."


def test_render_text_without_sources():
    artifacts = [
        _text_artifact("Alpha.", source="a.txt"),
        _text_artifact("Beta.", source="b.txt"),
    ]
    assert render_text(artifacts, include_sources=False) == "Alpha.\n\nBeta."


def test_render_text_skips_empty_and_whitespace_only_artifacts():
    artifacts = [
        _text_artifact("", source="empty.txt"),
        _text_artifact("   \n\t ", source="blank.txt"),
        _text_artifact("Real.", source="real.txt"),
    ]
    assert render_text(artifacts) == "## real.txt\nReal."


def test_render_text_empty_list_returns_empty_string():
    assert render_text([]) == ""


def test_render_text_notes_image_only_artifacts():
    art = make_artifact(
        images=[
            {"name": "p-1.png", "mimetype": "image/png", "bytes": b"x"},
            {"name": "p-2.png", "mimetype": "image/png", "bytes": b"y"},
        ],
        meta={"source": "scan.pdf"},
    )
    assert render_text([art]) == "## scan.pdf\n[image: p-1.png]\n[image: p-2.png]"
    # Without sources the image notes still appear (never silently lost).
    assert render_text([art], include_sources=False) == (
        "[image: p-1.png]\n[image: p-2.png]"
    )


def test_render_text_text_artifact_with_images_renders_text_only():
    art = make_artifact(
        text="Body.",
        images=[{"name": "fig.png", "mimetype": "image/png", "bytes": b"x"}],
        meta={"source": "doc.pdf"},
    )
    assert render_text([art]) == "## doc.pdf\nBody."


def test_render_text_missing_source_uses_placeholder():
    art = make_artifact(text="Hi.")
    assert render_text([art]) == "## (unknown)\nHi."


def test_render_text_strips_outer_whitespace_of_text():
    art = _text_artifact("\n\n  Body.  \n", source="a.txt")
    assert render_text([art]) == "## a.txt\nBody."


# =============================================================================
# to_claude_content
# =============================================================================


def test_to_claude_content_single_text_block_first():
    artifacts = [
        _text_artifact("Alpha.", source="a.txt"),
        _text_artifact("Beta.", source="b.txt"),
    ]
    blocks = to_claude_content(artifacts)
    assert len(blocks) == 1
    assert blocks[0] == {"type": "text", "text": render_text(artifacts)}


def test_to_claude_content_image_b64_round_trip():
    blocks = to_claude_content([_image_artifact()])
    image_blocks = [b for b in blocks if b["type"] == "image"]
    assert len(image_blocks) == 1
    source = image_blocks[0]["source"]
    assert source["type"] == "base64"
    assert source["media_type"] == "image/png"
    assert base64.b64decode(source["data"]) == PNG_BYTES
    # Standard base64 (not urlsafe): re-encoding matches exactly.
    assert source["data"] == base64.b64encode(PNG_BYTES).decode("ascii")


def test_to_claude_content_wire_form_bytes_b64():
    b64 = base64.b64encode(PNG_BYTES).decode("ascii")
    art = make_artifact(
        images=[{"name": "p.png", "mimetype": "image/png", "bytes_b64": b64}],
        meta={"source": "p.pdf"},
    )
    blocks = to_claude_content([art])
    image_blocks = [b for b in blocks if b["type"] == "image"]
    assert image_blocks[0]["source"]["data"] == b64
    assert base64.b64decode(image_blocks[0]["source"]["data"]) == PNG_BYTES


def test_to_claude_content_text_then_images_then_prompt():
    artifacts = [_text_artifact("Text.", source="a.txt"), _image_artifact()]
    blocks = to_claude_content(artifacts, prompt="Summarize.")
    assert [b["type"] for b in blocks] == ["text", "image", "text"]
    assert blocks[-1] == {"type": "text", "text": "Summarize."}


def test_to_claude_content_empty_inputs():
    assert to_claude_content([]) == []
    assert to_claude_content([], prompt="Hi") == [{"type": "text", "text": "Hi"}]


def test_to_claude_content_skips_images_without_payload():
    art = make_artifact(
        images=[{"name": "ghost.png", "mimetype": "image/png"}],
        meta={"source": "g.pdf"},
    )
    blocks = to_claude_content([art])
    # The [image: ...] note remains in the text block, but no image block.
    assert [b["type"] for b in blocks] == ["text"]
    assert "[image: ghost.png]" in blocks[0]["text"]


def test_to_claude_content_is_json_serializable():
    artifacts = [_text_artifact("Hello.", source="a.txt"), _image_artifact()]
    blocks = to_claude_content(artifacts, prompt="Go")
    round_tripped = json.loads(json.dumps(blocks))
    assert round_tripped == blocks


# =============================================================================
# to_claude_messages / to_openai_messages
# =============================================================================


def test_to_claude_messages_shape():
    artifacts = [_text_artifact("Hello.", source="a.txt")]
    messages = to_claude_messages(artifacts, prompt="Go")
    assert messages == [
        {
            "role": "user",
            "content": to_claude_content(artifacts, prompt="Go"),
        }
    ]


def test_to_openai_messages_shape_and_data_url_round_trip():
    artifacts = [_text_artifact("Hello.", source="a.txt"), _image_artifact()]
    messages = to_openai_messages(artifacts, prompt="Go")
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    parts = messages[0]["content"]
    assert [p["type"] for p in parts] == ["text", "image_url", "text"]
    assert parts[0] == {"type": "text", "text": render_text(artifacts)}
    url = parts[1]["image_url"]["url"]
    prefix = "data:image/png;base64,"
    assert url.startswith(prefix)
    assert base64.b64decode(url[len(prefix) :]) == PNG_BYTES
    assert parts[-1] == {"type": "text", "text": "Go"}
    assert json.loads(json.dumps(messages)) == messages


def test_to_openai_messages_empty_artifacts_prompt_only():
    messages = to_openai_messages([], prompt="Just answer.")
    assert messages == [
        {"role": "user", "content": [{"type": "text", "text": "Just answer."}]}
    ]


def test_to_claude_messages_prompt_is_optional():
    artifacts = [_text_artifact("Hello.", source="a.txt")]
    messages = to_claude_messages(artifacts)
    assert [b["type"] for b in messages[0]["content"]] == ["text"]
    assert messages == to_claude_messages(artifacts, prompt=None)


def test_to_openai_messages_prompt_is_optional():
    artifacts = [_text_artifact("Hello.", source="a.txt"), _image_artifact()]
    messages = to_openai_messages(artifacts)
    assert [p["type"] for p in messages[0]["content"]] == ["text", "image_url"]
    assert messages == to_openai_messages(artifacts, prompt=None)


# =============================================================================
# chunk — window splitting
# =============================================================================


def test_chunk_empty_inputs_return_empty_list():
    assert chunk([]) == []
    assert chunk([make_artifact()]) == []
    assert chunk([_text_artifact("   \n ")]) == []


def test_chunk_small_text_single_chunk_with_header():
    art = _text_artifact("Tiny text.", source="t.txt")
    assert chunk([art]) == ["## t.txt\nTiny text."]


def test_chunk_exact_boundary_is_one_chunk():
    text = "x" * 100
    art = _text_artifact(text, source="t.txt")
    assert chunk([art], max_chars=100, overlap=10) == [f"## t.txt\n{text}"]


def test_chunk_one_char_over_boundary_is_two_chunks():
    text = "x" * 101  # no break characters anywhere
    art = _text_artifact(text, source="t.txt")
    chunks = chunk([art], max_chars=100, overlap=10)
    assert len(chunks) == 2
    assert _body(chunks[0]) == text[:100]
    assert _body(chunks[1]) == text[90:]  # starts overlap chars before the cut


def test_chunk_overlap_verification_and_reconstruction():
    # Digits, no whitespace: forces hard cuts at exactly max_chars.
    text = "".join(str(i % 10) for i in range(250))
    art = _text_artifact(text, source="d.txt")
    chunks = chunk([art], max_chars=100, overlap=20)
    bodies = [_body(c) for c in chunks]
    assert bodies == [text[0:100], text[80:180], text[160:250]]
    for prev, nxt in zip(bodies, bodies[1:], strict=False):
        assert nxt[:20] == prev[-20:]
    # Dropping each overlap reconstructs the original exactly.
    assert bodies[0] + "".join(b[20:] for b in bodies[1:]) == text


def test_chunk_every_body_within_max_chars():
    text = ("word " * 500).strip()
    art = _text_artifact(text, source="w.txt")
    for c in chunk([art], max_chars=120, overlap=15):
        assert len(_body(c)) <= 120


def test_chunk_prefers_paragraph_boundary_in_last_20_percent():
    text = "A" * 90 + "\n\n" + "B" * 30
    art = _text_artifact(text, source="p.txt")
    chunks = chunk([art], max_chars=100, overlap=0)
    assert [_body(c) for c in chunks] == ["A" * 90 + "\n\n", "B" * 30]


def test_chunk_prefers_newline_when_no_paragraph():
    text = "A" * 90 + "\n" + "B" * 40
    art = _text_artifact(text, source="n.txt")
    chunks = chunk([art], max_chars=100, overlap=0)
    assert [_body(c) for c in chunks] == ["A" * 90 + "\n", "B" * 40]


def test_chunk_prefers_space_when_no_newline():
    text = "A" * 90 + " " + "B" * 40
    art = _text_artifact(text, source="s.txt")
    chunks = chunk([art], max_chars=100, overlap=0)
    assert [_body(c) for c in chunks] == ["A" * 90 + " ", "B" * 40]


def test_chunk_paragraph_beats_later_space():
    # Both a paragraph break and a later space sit in the last 20%:
    # the paragraph break wins even though the space is rightmost.
    text = "A" * 84 + "\n\n" + "C C" + "D" * 40  # \n\n at 84, space at 87
    art = _text_artifact(text, source="p.txt")
    chunks = chunk([art], max_chars=100, overlap=0)
    assert _body(chunks[0]) == "A" * 84 + "\n\n"


def test_chunk_ignores_boundary_outside_last_20_percent():
    # The only break is at offset 50-51 — outside the last 20% of a
    # 100-char window — so the split is a hard cut at max_chars.
    text = "A" * 50 + "\n\n" + "C" * 70
    art = _text_artifact(text, source="h.txt")
    chunks = chunk([art], max_chars=100, overlap=0)
    assert [_body(c) for c in chunks] == [text[:100], text[100:]]


def test_chunk_multiple_artifacts_in_order_with_headers():
    arts = [
        _text_artifact("First.", source="1.txt"),
        _text_artifact("", source="empty.txt"),
        _text_artifact("Second.", source="2.txt"),
    ]
    assert chunk(arts) == ["## 1.txt\nFirst.", "## 2.txt\nSecond."]


def test_chunk_invalid_max_chars_raises():
    with pytest.raises(ValueError):
        chunk([_text_artifact("hi")], max_chars=0)


def test_chunk_overlap_clamped_below_max_chars_terminates():
    text = "x" * 35
    art = _text_artifact(text, source="o.txt")
    chunks = chunk([art], max_chars=10, overlap=50)  # clamped to 9
    assert _body(chunks[0]) == text[:10]
    assert all(len(_body(c)) <= 10 for c in chunks)
    # Still covers the end of the text.
    assert _body(chunks[-1]).endswith("x")


# =============================================================================
# chunk — segment packing
# =============================================================================


def _segmented_artifact(page_texts: list[str], source: str = "doc.pdf") -> dict:
    """Build a pdf-style artifact: pages joined by \\n\\n with segments."""
    text = "\n\n".join(page_texts)
    segments, offset = [], 0
    for i, page in enumerate(page_texts):
        segments.append(
            {
                "kind": "page",
                "label": f"page {i + 1}",
                "start": offset,
                "end": offset + len(page),
            }
        )
        offset += len(page) + 2
    return make_artifact(text=text, meta={"source": source, "segments": segments})


def test_chunk_packs_whole_segments_greedily():
    art = _segmented_artifact(["x" * 40, "y" * 40, "z" * 40])
    chunks = chunk([art], max_chars=90, overlap=0)
    # Pages 1+2 fit in 90 chars (40 + 2 + 40 = 82); page 3 does not.
    assert [_body(c) for c in chunks] == ["x" * 40 + "\n\n" + "y" * 40, "z" * 40]
    assert all(c.startswith("## doc.pdf\n") for c in chunks)


def test_chunk_segments_never_split_when_they_fit():
    pages = ["a" * 30, "b" * 30, "c" * 30, "d" * 30]
    art = _segmented_artifact(pages)
    chunks = chunk([art], max_chars=70, overlap=0)
    bodies = [_body(c) for c in chunks]
    # Each page's text appears intact in exactly one chunk body.
    for page in pages:
        assert sum(body.count(page) for body in bodies) == 1
    assert bodies == ["a" * 30 + "\n\n" + "b" * 30, "c" * 30 + "\n\n" + "d" * 30]


def test_chunk_all_segments_fit_into_one_chunk():
    art = _segmented_artifact(["one", "two", "three"])
    assert chunk([art], max_chars=8000) == ["## doc.pdf\none\n\ntwo\n\nthree"]


def test_chunk_oversized_segment_falls_back_to_window_split():
    art = _segmented_artifact(["s" * 10, "q" * 150])
    chunks = chunk([art], max_chars=100, overlap=10)
    bodies = [_body(c) for c in chunks]
    # Page 1 alone (page 2 cannot join), then page 2 window-split w/ overlap.
    assert bodies == ["s" * 10, "q" * 100, "q" * 60]
    assert bodies[1][-10:] == bodies[2][:10]  # overlap inside the big segment


def test_chunk_window_fallback_when_no_segments():
    # Same text, no meta.segments: window splitting (hard cuts), not packing.
    text = "x" * 40 + "\n\n" + "y" * 40 + "\n\n" + "z" * 40
    art = _text_artifact(text, source="doc.pdf")
    bodies = [_body(c) for c in chunk([art], max_chars=90, overlap=0)]
    segmented = _segmented_artifact(["x" * 40, "y" * 40, "z" * 40])
    packed = [_body(c) for c in chunk([segmented], max_chars=90, overlap=0)]
    assert bodies != packed  # segment-aware packing actually changed the cuts


def test_chunk_segment_chunks_respect_max_chars():
    art = _segmented_artifact(["p" * 33, "q" * 33, "r" * 33, "s" * 200])
    for c in chunk([art], max_chars=80, overlap=8):
        assert len(_body(c)) <= 80


def test_chunk_is_deterministic():
    def build() -> list[dict]:
        return [
            _segmented_artifact(["x" * 40, "y" * 40, "z" * 40]),
            _text_artifact("".join(str(i % 10) for i in range(300)), source="n.txt"),
        ]

    first = chunk(build(), max_chars=90, overlap=15)
    for _ in range(3):
        assert chunk(build(), max_chars=90, overlap=15) == first


# =============================================================================
# Real-file smoke test
# =============================================================================


def test_att_readme_smoke():
    from attachments import att

    readme = Path(__file__).resolve().parents[1] / "README.md"
    artifacts = att(str(readme))
    assert artifacts and artifacts[0]["text"]

    prompt_text = render_text(artifacts)
    assert prompt_text.startswith("## ")
    assert "attachments" in prompt_text

    blocks = to_claude_content(artifacts, prompt="Summarize this repo.")
    assert blocks[0]["type"] == "text"
    assert blocks[-1] == {"type": "text", "text": "Summarize this repo."}

    messages = to_openai_messages(artifacts, prompt="Summarize this repo.")
    assert messages[0]["content"][-1]["text"] == "Summarize this repo."

    chunks = chunk(artifacts, max_chars=500, overlap=50)
    assert chunks
    assert all(c.startswith("## ") for c in chunks)
    assert all(len(_body(c)) <= 500 for c in chunks)
    assert chunk(artifacts, max_chars=500, overlap=50) == chunks
