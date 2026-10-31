"""The CSV delimiter guess: CPython's ``csv.Sniffer``, carried here.

CPython rewrote ``Sniffer`` in patch releases (3.11.17, 3.12.15, 3.13.16,
3.14): line breaks are normalized first, and a quoted field's body is
matched in linear time instead of a lazy ``.*?`` that was quadratic. A
Python with an older patch release guesses differently on some files.
Carrying the new version makes every Python, and every other
implementation of the contract (``contract/processors.md``), guess the
same delimiter from the same text.

Only what decides the delimiter is kept (``sniff`` also guesses the
quote character, double quoting and initial spaces, which the CSV
processor does not use). ``tests/test_sniffer.py`` checks it against the
standard library when the standard library has the new version.

Adapted from CPython ``Lib/csv.py``. Copyright (c) 2001-2025 Python
Software Foundation; All Rights Reserved. Used under the Python Software
Foundation License Version 2 (https://docs.python.org/3/license.html).
"""

from __future__ import annotations

import re

#: Preferred delimiters when several fit equally well (``Sniffer.preferred``).
PREFERRED = (",", "\t", ";", " ", ":")

# The body of a quoted field ends at the first quote which is not
# doubled, as it does for a reader (possessive: linear time).
_BODY = r"(?:(?P=quote){2}|(?!(?P=quote)).)*+"
_QUOTED = [
    re.compile(pattern % _BODY, re.DOTALL | re.MULTILINE)
    for pattern in (
        # ,"...",
        r'(?P<delim>[^\w\n"\'])(?P<space> ?)(?P<quote>["\'])%s(?P=quote)(?P=delim)',
        # "...",
        r'(?:^|\n)(?P<quote>["\'])%s(?P=quote)(?P<delim>[^\w\n"\'])(?P<space> ?)',
        # ,"..."
        r'(?P<delim>[^\w\n"\'])(?P<space> ?)(?P<quote>["\'])%s(?P=quote)(?:$|\n)',
        # "..."
        r'(?:^|\n)(?P<quote>["\'])%s(?P=quote)(?:$|\n)',
    )
]


def _from_quotes(data: str, delimiters: str | None) -> str:
    """A delimiter from quoted fields (``_guess_quote_and_delimiter``), or ``""``.

    Examples:
        >>> _from_quotes('"a";"b"\\n"1";"2"\\n', ",;")
        ';'
        >>> _from_quotes("no quotes", ",;")
        ''
    """
    for regexp in _QUOTED:
        matches = regexp.findall(data)
        if matches:
            break
    else:
        return ""
    groups = regexp.groupindex
    delims: dict[str, int] = {}
    if "delim" in groups:
        for m in matches:
            key = m[groups["delim"] - 1]
            if key and (delimiters is None or key in delimiters):
                delims[key] = delims.get(key, 0) + 1
    if not delims:
        return ""  # a single column of quoted data
    delim = max(delims, key=delims.get)  # type: ignore[arg-type]
    return "" if delim == "\n" else delim


def _from_frequencies(data: str, delimiters: str | None) -> str:
    """A delimiter that occurs equally often on most lines (``_guess_delimiter``)."""
    lines = list(filter(None, data.split("\n")))
    ascii_chars = [chr(c) for c in range(127)]
    chunk_length = min(10, len(lines))
    iteration = 0
    char_frequency: dict[str, dict[int, int]] = {}
    modes: dict[str, tuple[int, int]] = {}
    delims: dict[str, tuple[int, int]] = {}
    start, end = 0, chunk_length
    while start < len(lines):
        iteration += 1
        for line in lines[start:end]:
            for char in ascii_chars:
                meta = char_frequency.get(char, {})
                freq = line.count(char)
                meta[freq] = meta.get(freq, 0) + 1
                char_frequency[char] = meta
        for char in char_frequency:
            items = list(char_frequency[char].items())
            if len(items) == 1 and items[0][0] == 0:
                continue
            if len(items) > 1:
                mode = max(items, key=lambda x: x[1])
                items.remove(mode)
                modes[char] = (mode[0], mode[1] - sum(item[1] for item in items))
            else:
                modes[char] = items[0]
        total = float(min(chunk_length * iteration, len(lines)))
        consistency = 1.0
        threshold = 0.9
        while len(delims) == 0 and consistency >= threshold:
            for k, v in modes.items():
                if v[0] > 0 and v[1] > 0:
                    if (v[1] / total) >= consistency and (
                        delimiters is None or k in delimiters
                    ):
                        delims[k] = v
            consistency -= 0.01
        if len(delims) == 1:
            return next(iter(delims))
        start = end
        end += chunk_length
    if not delims:
        return ""
    for d in PREFERRED:
        if d in delims:
            return d
    return sorted((v, k) for k, v in delims.items())[-1][1]


def sniff_delimiter(sample: str, delimiters: str | None = None) -> str | None:
    """The delimiter ``csv.Sniffer().sniff(sample, delimiters)`` finds, or ``None``.

    Examples:
        >>> sniff_delimiter("a;b\\n1;2\\n", ",;\\t|")
        ';'
        >>> sniff_delimiter("a,b\\r1,2\\r", ",;")  # old Mac line ends count as lines
        ','
        >>> sniff_delimiter("one\\ntwo\\n", ",;") is None
        True
    """
    sample = sample.replace("\r\n", "\n").replace("\r", "\n")
    return (
        _from_quotes(sample, delimiters)
        or _from_frequencies(sample, delimiters)
        or None
    )
