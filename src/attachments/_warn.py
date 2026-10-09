"""Warnings that point at the caller's line, not at this library."""

from __future__ import annotations

import os
import sys

_PACKAGE = os.path.dirname(os.path.abspath(__file__))


def caller_stacklevel() -> int:
    """``stacklevel`` for ``warnings.warn`` naming the first frame outside
    this package (the user's line), however deep the call came from."""
    level, frame = 1, sys._getframe(1)
    while frame is not None and os.path.abspath(frame.f_code.co_filename).startswith(
        _PACKAGE
    ):
        frame = frame.f_back
        level += 1
    return level
