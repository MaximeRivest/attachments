"""Tests for ``a.lm15()`` / ``render.to_lm15_message``.

=============================================================================
TEST GUIDELINES
=============================================================================

GOOD tests:
    - The Message: role, part types and order (each page's pictures after
      its text), image bytes intact, prompt last, sources=False
    - It is READY: lm15 builds real provider requests from it, offline
      (Anthropic, OpenAI, Gemini), and a cache mark lands on the document
    - Without lm15: ImportError with the install command; nothing to send:
      ValueError

BAD tests:
    - Network calls (build_request is enough to prove the shape)
=============================================================================
"""

from __future__ import annotations

import json
import sys

import pytest

from attachments import Artifacts, make_artifact, to_lm15_message

lm15 = pytest.importorskip("lm15")


def _paged() -> Artifacts:
    images = [
        {
            "name": f"p{n}.png",
            "mimetype": "image/png",
            "bytes": f"img{n}".encode(),
            "page": n,
        }
        for n in (1, 2)
    ]
    segments = [
        {"kind": "page", "label": "page 1", "start": 0, "end": 3, "page": 1},
        {"kind": "page", "label": "page 2", "start": 5, "end": 8, "page": 2},
    ]
    art = make_artifact(
        text="one\n\ntwo",
        images=images,
        meta={"source": "report.pdf", "segments": segments},
    )
    return Artifacts([art])


def test_message_shape_and_order():
    msg = _paged().lm15("Summarize.")
    assert isinstance(msg, lm15.Message)
    assert msg.role == "user"
    assert [p.type for p in msg.parts] == ["text", "image", "text", "image", "text"]
    assert msg.parts[0].text == "## report.pdf\none"
    assert [p.bytes for p in msg.parts if p.type == "image"] == [b"img1", b"img2"]
    assert msg.parts[1].media_type == "image/png"
    assert msg.parts[-1].text == "Summarize."


def test_options_match_parts():
    a = _paged()
    assert "report.pdf" not in a.lm15(sources=False).parts[0].text
    flat = a.lm15(interleave=False)
    assert [p.type for p in flat.parts] == ["text", "image", "image"]


def test_wire_form_images_work():
    a = Artifacts.from_wire(_paged().to_wire())
    assert [p.bytes for p in a.lm15().parts if p.type == "image"] == [b"img1", b"img2"]


@pytest.mark.parametrize("provider", ["AnthropicLM", "OpenAILM", "GeminiLM"])
def test_ready_for_every_provider(provider):
    """lm15 turns the message into a real request body, offline."""
    a = _paged()
    request = lm15.Request(
        model="some-model",
        messages=(a.lm15(), lm15.Message.user("What changed?")),
        config=lm15.Config(cache=lm15.CacheConfig(prefix_until_index=0)),
    )
    body = json.loads(
        getattr(lm15, provider)(api_key="x").build_request(request, False).body
    )
    text = json.dumps(body)
    assert "## report.pdf" in text and "What changed?" in text
    if provider == "AnthropicLM":
        document = body["messages"][0]["content"]
        assert [b["type"] for b in document] == ["text", "image", "text", "image"]
        assert "cache_control" in document[-1]  # the document is the cached prefix


def test_nothing_to_send():
    with pytest.raises(ValueError, match="nothing to send"):
        Artifacts().lm15()
    assert Artifacts().lm15("Hello?").parts[0].text == "Hello?"


def test_without_lm15(monkeypatch):
    monkeypatch.setitem(sys.modules, "lm15", None)
    with pytest.raises(ImportError, match=r"pip install attachments\[lm15\]"):
        to_lm15_message(_paged())
