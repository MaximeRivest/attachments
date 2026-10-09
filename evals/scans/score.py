"""Score OCR output against the known text of each page.

Character error rate (CER) and word error rate (WER) on whitespace-
normalised text: a word glued to its neighbour ("page1line2") counts as
wrong, which is how a model or a search index sees it.
"""

from __future__ import annotations


def _distance(a: list | str, b: list | str) -> int:
    """Levenshtein distance (insert, delete, substitute all cost 1)."""
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        current = [i]
        for j, y in enumerate(b, 1):
            current.append(
                min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (x != y))
            )
        previous = current
    return previous[-1]


def words(text: str) -> list[str]:
    return text.split()


def cer(truth: str, got: str) -> float:
    t, g = " ".join(words(truth)), " ".join(words(got))
    return _distance(t, g) / max(1, len(t))


def wer(truth: str, got: str) -> float:
    t, g = words(truth), words(got)
    return _distance(t, g) / max(1, len(t))
