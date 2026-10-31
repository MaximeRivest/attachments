"""The carried ``csv.Sniffer`` (``_processors/_sniffer.py``).

On a Python whose standard library has the same Sniffer (patch releases
from 3.11.17, 3.12.15, 3.13.16 and 3.14 on), the two must agree on every
sample; on older ones the standard library guesses differently on some
files, which is why the carried copy exists.
"""

from __future__ import annotations

import csv
import inspect
import random

import pytest

from attachments._processors._sniffer import sniff_delimiter

NEW_STDLIB = "replace('\\r\\n', '\\n')" in inspect.getsource(csv.Sniffer.sniff)


def _stdlib(sample: str, delimiters: str) -> str | None:
    try:
        return csv.Sniffer().sniff(sample, delimiters=delimiters).delimiter
    except csv.Error:
        return None


def _samples(n: int) -> list[str]:
    rnd = random.Random(17)
    atoms = ["a", "b", "1", "22", ",", ",", ";", "\t", "|", '"', "'", " ", "\n", "\n",
             "\r\n", "\r", "é", "x y", '""', ":"]  # fmt: skip
    out = [
        "".join(rnd.choice(atoms) for _ in range(rnd.randrange(80))) for _ in range(n)
    ]
    for _ in range(n // 4):
        sep = rnd.choice([",", ";", "\t", "|", " "])
        rows = [
            sep.join(
                rnd.choice(["x", '"y"', "3", "", '"a""b"'])
                for _ in range(rnd.randrange(1, 5))
            )
            for _ in range(rnd.randrange(3, 40))
        ]
        out.append("\n".join(rows))
    return out


@pytest.mark.skipif(not NEW_STDLIB, reason="this Python's csv.Sniffer is the older one")
def test_agrees_with_the_standard_library():
    for sample in _samples(2000):
        assert sniff_delimiter(sample, ",;\t|") == _stdlib(sample, ",;\t|"), repr(
            sample
        )


def test_old_mac_line_ends_are_lines():
    assert sniff_delimiter("a,b\r1,2\r3,4\r", ",;") == ","


def test_a_long_quoted_sample_is_fast():
    # The old lazy pattern was quadratic in the sample's length.
    sniff_delimiter('"' + "x" * 8000, ",;\t|")
