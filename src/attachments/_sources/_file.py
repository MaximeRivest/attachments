"""``SourceFile``: one resolved file, still a plain ``(name, bytes)`` pair.

``unpack()`` returns a list of ``(filename, bytes)`` tuples — a public,
frozen contract (custom handlers return exactly that). Some sources know
more about a file than its name: an HTTP download knows the address it
came from (after redirects) and whether the server contradicted the
name. ``SourceFile`` carries that as attributes on a tuple that is still
exactly ``(name, data)``: it unpacks, compares and serializes like the
plain pair, so nothing that consumes ``unpack()`` output changes.
"""

from __future__ import annotations

from collections.abc import Iterable


class SourceFile(tuple):
    """A ``(name, data)`` pair with optional provenance.

    Attributes:
        url: Address the bytes were fetched from (final URL after
            redirects); ``None`` for local files and archive members.
        warnings: Messages for the resulting artifact's ``meta.warnings``.

    Examples:
        >>> f = SourceFile("page.html", b"<p>hi</p>", url="https://x.org/page")
        >>> name, data = f
        >>> name, f.url
        ('page.html', 'https://x.org/page')
        >>> f == ("page.html", b"<p>hi</p>")
        True
        >>> SourceFile("a.txt", b"").url is None
        True
    """

    url: str | None
    warnings: tuple[str, ...]

    def __new__(
        cls,
        name: str,
        data: bytes,
        *,
        url: str | None = None,
        warnings: Iterable[str] = (),
    ) -> SourceFile:
        self = super().__new__(cls, (name, data))
        self.url = url
        self.warnings = tuple(warnings)
        return self

    def __getnewargs__(self) -> tuple[str, bytes]:  # pickling/copying
        return (self[0], self[1])

    @property
    def name(self) -> str:
        return self[0]

    @property
    def data(self) -> bytes:
        return self[1]

    def __repr__(self) -> str:
        extra = f", url={self.url!r}" if self.url else ""
        return f"SourceFile({self[0]!r}, <{len(self[1])} bytes>{extra})"
