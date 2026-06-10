"""
Smoke tests for the att.help() discovery layer (attachments._help).

=============================================================================
TEST GUIDELINES FOR HELP
=============================================================================

GOOD tests:
    - help prints (capsys), returns None, and reflects the LIVE registry
    - att.help is wired up in __init__

BAD tests:
    - Asserting the full help text byte-for-byte (it tracks the registry)

=============================================================================
"""

from __future__ import annotations

import attachments
from attachments import att


def test_att_help_prints_one_screen_and_returns_none(capsys):
    assert att.help() is None
    out = capsys.readouterr().out
    assert out  # printed, not returned
    first_line = out.splitlines()[0]
    assert first_line.startswith(f"attachments {attachments.__version__}")
    # Live registry groups
    for group in ("text/code", "pdf", "office", "html", "images"):
        assert group in out
    assert ".pdf" in out and ".xlsx" in out and ".png" in out
    # Sources, examples, and pointers
    assert "github://" in out
    assert "att.options('.pdf')" in out
    assert "docs/dsl-options.md" in out
    assert "spec/" in out
    # One screen, give or take
    assert len(out.splitlines()) <= 30


def test_att_help_is_the_help_function():
    from attachments._help import att_help

    assert att.help is att_help


def test_help_picks_up_custom_processors(capsys):
    from attachments import register_processor, reset_processors
    from attachments.types import make_artifact

    def proc(data: bytes, **options) -> dict:
        return make_artifact(text="x")

    try:
        register_processor(".zzcustom", proc)
        att.help()
        assert ".zzcustom" in capsys.readouterr().out
    finally:
        reset_processors()
