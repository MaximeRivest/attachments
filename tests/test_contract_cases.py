"""Python against the contract's cases (``contract/cases/*.json``).

The same files every implementation is checked against; ``_contract.py``
is Python's driver. A failure here means Python and the contract
disagree: fix Python, or change the rule and its case in
``contract/cases/make.py`` (never by editing a JSON file).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from _contract import AREAS, run

CASES_DIR = Path(__file__).resolve().parent.parent / "contract" / "cases"


def _load() -> list[tuple[str, dict]]:
    out = []
    for area in AREAS:
        doc = json.loads((CASES_DIR / f"{area}.json").read_text())
        out.extend((area, case) for case in doc["cases"])
    return out


CASES = _load()


@pytest.mark.parametrize(
    ("area", "case"), CASES, ids=[f"{a}: {c['name']}" for a, c in CASES]
)
def test_case(area: str, case: dict) -> None:
    assert run(area, case) == case["expect"]


def test_every_area_has_cases() -> None:
    assert {a for a, _ in CASES} == set(AREAS)
