"""Python against the contract's cases (``contract/cases/*.json``).

The same files every implementation is checked against; ``_contract.py``
and ``_contract_reading.py`` are Python's drivers. A failure here means
Python and the contract disagree: fix Python, or change the rule and its
case in ``contract/cases/make.py`` (never by editing a JSON file).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from _contract import AREAS, run
from _contract_reading import AREAS as READING
from _contract_reading import EXTENSIONS

CASES_DIR = Path(__file__).resolve().parent.parent / "contract" / "cases"


def _load() -> list[tuple[str, dict, dict]]:
    out = []
    for area in [*READING, *AREAS]:
        doc = json.loads((CASES_DIR / f"{area}.json").read_text())
        out.extend((area, case, doc) for case in doc["cases"])
    return out


CASES = _load()


@pytest.mark.parametrize(
    ("area", "case", "doc"), CASES, ids=[f"{a}: {c['name']}" for a, c, _ in CASES]
)
def test_case(area: str, case: dict, doc: dict) -> None:
    missing = set(case.get("requires", ())) - EXTENSIONS
    if missing:
        pytest.skip(f"needs {', '.join(sorted(missing))}")
    if area in READING:
        assert READING[area](case, doc) == case["expect"]
    else:
        assert run(area, case) == case["expect"]


def test_every_area_has_cases() -> None:
    assert {a for a, _, _ in CASES} == set(AREAS) | set(READING)
