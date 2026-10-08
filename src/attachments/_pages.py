"""Page selections: ``pages: 2-4``, ``1,3,5``, ``-1`` (the last page), ``-3-``.

One syntax for every format with pages or slides (PDF; PowerPoint and its
older/OpenDocument cousins). A selection is a comma-separated list of items:

========  ===========================================
``3``     page 3
``2-5``   pages 2 to 5
``7-``    page 7 to the end
``-1``    the last page (``-2``: the one before it)
``-3-``   the last three pages
``2--2``  page 2 to the second-to-last page
========  ===========================================

Pages are 1-based, read in document order, each at most once
(``pages: 5,1,5`` reads 1 then 5). Items outside the document are ignored;
a selection with no page inside it is reported by the processor. The
document's length is only known to the processor, so negative items are
resolved there (:meth:`PageSelection.indices`).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

_ITEM = re.compile(r"^(-?\d+)(?:\s*-\s*(-?\d+)?)?$")


class PageSelectionError(ValueError):
    """A ``pages`` value that is not a page selection."""


@dataclass(frozen=True)
class PageSelection:
    """Items ``(first, last)``, 1-based; negative = from the end; ``last``
    ``None`` = to the end."""

    items: tuple[tuple[int, int | None], ...]

    def indices(self, total: int) -> list[int]:
        """0-based page indices for a document of *total* pages, in order.

        Examples:
            >>> parse_pages("1,3,5").indices(4)
            [0, 2]
            >>> parse_pages("-1").indices(10), parse_pages("-3-").indices(10)
            ([9], [7, 8, 9])
            >>> parse_pages("5,1-2,2").indices(10)
            [0, 1, 4]
            >>> parse_pages("2--2").indices(5)
            [1, 2, 3]
        """

        def absolute(n: int) -> int:
            return n if n > 0 else total + 1 + n

        chosen: set[int] = set()
        for first, last in self.items:
            start = absolute(first)
            end = total if last is None else absolute(last)
            chosen.update(range(max(start, 1), min(end, total) + 1))
        return [page - 1 for page in sorted(chosen)]

    def as_range(self) -> tuple[int, int | None] | None:
        """``(page_start, page_end)`` 0-based/exclusive if one plain range.

        Examples:
            >>> parse_pages("2-4").as_range(), parse_pages("3").as_range()
            ((1, 4), (2, 3))
            >>> parse_pages("7-").as_range(), parse_pages("1,3").as_range()
            ((6, None), None)
        """
        if len(self.items) != 1:
            return None
        first, last = self.items[0]
        if first < 1 or (last is not None and last < 1):
            return None
        return first - 1, last

    def __str__(self) -> str:
        """Canonical text, e.g. ``1-3,5,-1``.

        Examples:
            >>> str(parse_pages(" 1 - 3 , 5,-2- "))
            '1-3,5,-2-'
        """

        def item(first: int, last: int | None) -> str:
            if last is None:
                return f"{first}-"
            return str(first) if last == first else f"{first}-{last}"

        return ",".join(item(f, last) for f, last in self.items)


_HELP = (
    "a page selection: a 1-based page (3), a range (2-5, 7-), a list written "
    'as text ("1,3,5") or pages counted from the end (-1 = last, -3- = last three)'
)


def parse_pages(value: Any) -> PageSelection:
    """Parse a ``pages`` value: int, string, ``(first, last)`` pair, or a list.

    Examples:
        >>> parse_pages(4).items, parse_pages((2, 5)).items
        (((4, 4),), ((2, 5),))
        >>> parse_pages([2, 5]).items  # a two-number list is a range (wire form)
        ((2, 5),)
        >>> parse_pages("1,3,5").items  # lists are written as text
        ((1, 1), (3, 3), (5, 5))
        >>> parse_pages("0")
        Traceback (most recent call last):
        ...
        attachments._pages.PageSelectionError: pages must be a page selection: ...
    """
    if isinstance(value, PageSelection):
        return value
    if isinstance(value, bool):
        raise PageSelectionError(f"pages must be {_HELP}, got {value!r}")
    if isinstance(value, int):
        items: list[Any] = [str(value)]
    elif (
        isinstance(value, tuple | list)
        and len(value) == 2
        and all(isinstance(v, int) and not isinstance(v, bool) for v in value)
    ):
        # The DSL's range form (JSON turns the tuple into a list): 2-5.
        items = [f"{value[0]}-{value[1]}"]
    elif isinstance(value, str):
        items = value.split(",")
    else:
        raise PageSelectionError(f"pages must be {_HELP}, got {value!r}")

    parsed: list[tuple[int, int | None]] = []
    for raw in items:
        text = raw.strip()
        if not text:
            continue
        match = _ITEM.match(text)
        if not match:
            raise PageSelectionError(f"pages must be {_HELP}, got {value!r}")
        first = int(match.group(1))
        open_end = match.group(2) is None and "-" in text.lstrip("-")
        last = None if open_end else int(match.group(2) or first)
        if first == 0 or last == 0:
            raise PageSelectionError(
                f"pages must be {_HELP} (pages count from 1), got {value!r}"
            )
        if first > 0 and last is not None and last > 0 and last < first:
            raise PageSelectionError(
                f"pages must be {_HELP}; {text!r} ends before it starts"
            )
        parsed.append((first, last))
    if not parsed:
        raise PageSelectionError(f"pages must be {_HELP}, got {value!r}")
    return PageSelection(tuple(parsed))


#: Given a document's page count, the 0-based pages to read, in order.
PagePicker = Callable[[int], list[int]]


def page_picker(
    page_start: int = 0,
    page_end: int | None = None,
    max_pages: int | None = None,
    selection: PageSelection | None = None,
) -> PagePicker:
    """The pages to read: a selection (``1,3,-1``) or a plain range, capped.

    Examples:
        >>> page_picker(1, 3)(10), page_picker(max_pages=2)(10)
        ([1, 2], [0, 1])
        >>> page_picker(selection=parse_pages("1,-1"), max_pages=5)(10)
        [0, 9]
        >>> page_picker(8, 20)(10)
        [8, 9]
    """

    def pick(total: int) -> list[int]:
        if selection is not None:
            indices = selection.indices(total)
        else:
            start = max(0, int(page_start or 0))
            stop = total if page_end is None else min(int(page_end), total)
            indices = list(range(start, max(start, stop)))
        return indices if max_pages is None else indices[: int(max_pages)]

    return pick


def picker_from_options(options: dict[str, Any]) -> PagePicker | None:
    """The page picker a processor's resolved options ask for, if any.

    Reads ``page_start`` / ``page_end`` (a plain range) or ``page_selection``
    (lists, pages counted from the end), as the ``pages`` option emits them.
    Raises :class:`PageSelectionError` for an invalid ``page_selection``.

    Examples:
        >>> picker_from_options({}) is None
        True
        >>> picker_from_options({"page_selection": "1,-1"})(5)
        [0, 4]
        >>> picker_from_options({"page_start": 1, "page_end": 2})(5)
        [1]
    """
    selection = options.get("page_selection")
    start = options.get("page_start")
    end = options.get("page_end")
    if selection is None and not start and end is None:
        return None
    return page_picker(
        start or 0,
        end,
        None,
        parse_pages(selection) if selection is not None else None,
    )


def describe_pages(options: dict[str, Any]) -> str:
    """The requested pages as the user would write them (for messages).

    Examples:
        >>> describe_pages({"page_selection": "1,-1"})
        '1,-1'
        >>> (
        ...     describe_pages({"page_start": 8, "page_end": 9}),
        ...     describe_pages({"page_start": 6}),
        ... )
        ('9', '7-')
    """
    selection = options.get("page_selection")
    if selection is not None:
        return str(parse_pages(selection))
    first = int(options.get("page_start") or 0) + 1
    end = options.get("page_end")
    if end is None:
        return f"{first}-"
    return str(first) if int(end) == first else f"{first}-{int(end)}"
