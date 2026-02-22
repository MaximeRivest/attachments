"""Type definitions for the attachments library.

Provides :class:`Artifact` and :class:`ImageItem` as :class:`TypedDict`
definitions so that downstream consumers get autocomplete, type checking,
and clear documentation of the artifact structure.

Every processor must return an ``Artifact``-shaped dict.  The helper
:func:`make_artifact` builds one with correct defaults.

Example::

    from attachments.types import Artifact

    def my_processor(data: bytes, **opts) -> Artifact:
        return {
            "text": data.decode(),
            "images": [],
            "audio": [],
            "video": [],
            "flags": {"kind": "custom"},
        }
"""

from __future__ import annotations

from typing import Any, TypedDict


class ImageItem(TypedDict, total=False):
    """A single image extracted from a document.

    Required keys: ``name``, ``mimetype``, ``bytes``.
    Optional keys: ``page``, ``bytes_b64`` (used during JSON transport).
    """

    name: str
    mimetype: str
    bytes: bytes
    page: int
    bytes_b64: str  # present only during JSON serialisation


class Artifact(TypedDict):
    """Universal output format returned by every processor and by :func:`att`.

    Keys
    ----
    text : str
        Extracted text content (may be empty on error).
    images : list[ImageItem]
        Images extracted from the source (e.g. rendered PDF pages).
    audio : list[dict[str, Any]]
        Reserved for future audio extraction.
    video : list[dict[str, Any]]
        Reserved for future video extraction.
    flags : dict[str, Any]
        Metadata about the processing run.  Common keys:

        * ``source`` – original filename / path
        * ``error`` – human-readable error message (if failed)
        * ``note`` – informational message (e.g. "no processor available")
        * ``kind`` – format hint ("pdf", "text", "table", …)
        * ``via`` – "service" when processed remotely
    """

    text: str
    images: list[ImageItem]
    audio: list[dict[str, Any]]
    video: list[dict[str, Any]]
    flags: dict[str, Any]


def make_artifact(
    *,
    text: str = "",
    images: list[ImageItem] | None = None,
    audio: list[dict[str, Any]] | None = None,
    video: list[dict[str, Any]] | None = None,
    flags: dict[str, Any] | None = None,
) -> Artifact:
    """Create an :class:`Artifact` dict with safe defaults.

    This is the recommended way for processors to build their return value.

    Examples:
        >>> a = make_artifact(text="hello", flags={"kind": "text"})
        >>> a["text"]
        'hello'
        >>> a["images"]
        []
        >>> a["flags"]["kind"]
        'text'
    """
    return {
        "text": text,
        "images": images if images is not None else [],
        "audio": audio if audio is not None else [],
        "video": video if video is not None else [],
        "flags": flags if flags is not None else {},
    }
