"""Python's driver for the contract cases (``contract/cases/*.json``).

``run(area, case)`` answers one case with the Python implementation, in
the JSON form every implementation's answer is compared in. The cases'
``expect`` values were drafted with this driver (``contract/cases/make.py``)
and are the contract once reviewed; ``tests/test_contract_cases.py``
checks Python against them like any other implementation.
"""

from __future__ import annotations

import base64
import re
import warnings
from typing import Any

from attachments import Artifacts
from attachments._imagesize import image_size
from attachments._limits import CLAUDE, OPENAI, RequestLimitWarning, request_problems
from attachments._options import get_options, resolve_options
from attachments._pages import PageSelectionError, describe_pages, parse_pages
from attachments.dsl import format_dsl, parse_dsl
from attachments.render import chunk, estimate_tokens, image_tokens
from attachments.types import AttachmentsError


def _artifacts(case: dict) -> Artifacts:
    """The case's artifacts; a long text is written ``{"repeat": c, "times": n}``."""
    items = [
        {**a, "text": a["text"]["repeat"] * a["text"]["times"]}
        if isinstance(a.get("text"), dict)
        else a
        for a in case["artifacts"]
    ]
    return Artifacts.from_wire(items)


def _expand(part: dict) -> dict:
    """A limits case writes big payloads as ``{"repeat": c, "times": n}``."""
    out = dict(part)
    for key in ("data", "text"):
        value = part.get(key)
        if isinstance(value, dict):
            out[key] = value["repeat"] * value["times"]
    return out


def _warning_kinds(caught: list[warnings.WarningMessage]) -> list[str]:
    kinds = []
    for w in caught:
        if issubclass(w.category, RequestLimitWarning):
            kinds.append("request-limit")
        elif "carry their file name" in str(w.message):
            kinds.append("named-labels")
        else:  # pragma: no cover - a new warning the contract does not know
            kinds.append(f"other: {w.message}")
    return kinds


def _lm15_json(message: Any) -> dict:
    parts = []
    for part in message.parts:
        if part.type == "text":
            parts.append({"type": "text", "text": part.text})
        else:
            parts.append(
                {"type": "image", "media_type": part.media_type, "data": part.data}
            )
    return {"role": message.role, "parts": parts}


def _present(case: dict) -> dict:
    a = _artifacts(case)
    args = dict(case.get("args") or {})
    call = case["call"]
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            if call == "text":
                value: Any = a.to_text(**args)
            elif call == "parts":
                value = a.parts(**args)
            elif call == "claude":
                value = a.claude(args.pop("prompt", None), **args)
            elif call == "openai":
                value = a.openai(args.pop("prompt", None), **args)
            elif call == "lm15":
                value = _lm15_json(a.lm15(args.pop("prompt", None), **args))
            else:  # pragma: no cover
                raise AssertionError(call)
        except ValueError:
            return {"throws": True}
    out: dict[str, Any] = {"value": value}
    kinds = _warning_kinds(caught)
    if kinds:
        out["warnings"] = kinds
    return out


def _chunk(case: dict) -> dict:
    try:
        return {"value": chunk(_artifacts(case), **(case.get("args") or {}))}
    except ValueError:
        return {"throws": True}


def _tokens(case: dict) -> dict:
    try:
        if case["call"] == "estimate":
            return {
                "value": estimate_tokens(_artifacts(case), **(case.get("args") or {}))
            }
        return {
            "value": image_tokens(
                case["width"], case["height"], tier=case.get("tier", "high")
            )
        }
    except ValueError:
        return {"throws": True}


def _imagesize(case: dict) -> dict:
    size = image_size(base64.b64decode(case["bytes_b64"]))
    return {"value": list(size) if size else None}


def _limits(case: dict) -> dict:
    limits = {"claude": CLAUDE, "openai": OPENAI}[case["provider"]]
    return {"value": request_problems([_expand(p) for p in case["parts"]], limits)}


def _wire(case: dict) -> dict:
    try:
        if case["call"] == "from_wire":
            return {"value": Artifacts.from_wire(case["input"]).to_wire()}
        if case["call"] == "artifact_from_wire":
            return {"value": Artifacts.from_wire([case["input"]]).to_wire()[0]}
    except (TypeError, ValueError):
        return {"throws": True}
    raise AssertionError(case["call"])  # pragma: no cover


def _dsl(case: dict) -> dict:
    if case["call"] == "format":
        options = {
            k: tuple(v) if isinstance(v, list) else v
            for k, v in case["options"].items()
        }
        text = format_dsl(case["source"], options)
        source, parsed = parse_dsl(text)
        parsed = {k: list(v) if isinstance(v, tuple) else v for k, v in parsed.items()}
        return {"value": text, "reparsed": {"source": source, "options": parsed}}
    raise AssertionError(case["call"])  # pragma: no cover


def _pages(case: dict) -> dict:
    try:
        selection = parse_pages(case["value"])
    except PageSelectionError:
        return {"throws": True}
    out: dict[str, Any] = {"text": str(selection)}
    if "total" in case:
        out["indices"] = [i + 1 for i in selection.indices(case["total"])]
    return out


_UNKNOWN = re.compile(r"^Unknown option '(.*?)' for .*? — did you mean '(.*?)'\?")
_UNKNOWN_BARE = re.compile(r"^Unknown option '(.*?)' for ")
_INVALID = re.compile(r"^Invalid value for option '(.*?)' on ")


def _options(case: dict) -> dict:
    schema = get_options(case["key"])
    by_param = {(o.param or o.name): o.name for o in schema}
    raw = {
        k: tuple(v)
        if isinstance(v, list) and len(v) == 2 and all(type(x) is int for x in v)
        else v
        for k, v in case["raw"].items()
    }
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        kwargs, messages = resolve_options(schema, raw, context=case["key"])
    resolved: dict[str, Any] = {}
    pages = {k: kwargs.pop(k) for k in list(kwargs) if k.startswith("page_")}
    if pages:
        selection = pages.get("page_selection")
        resolved["pages"] = (
            str(selection) if selection is not None else describe_pages(pages)
        )
    for key, value in kwargs.items():
        resolved[by_param.get(key, key)] = value
    unknown, invalid = [], []
    for message in messages:
        if m := _UNKNOWN.match(message):
            unknown.append({"key": m.group(1), "suggest": m.group(2)})
        elif m := _UNKNOWN_BARE.match(message):
            unknown.append({"key": m.group(1), "suggest": None})
        elif m := _INVALID.match(message):
            invalid.append(m.group(1))
        else:  # pragma: no cover
            raise AssertionError(message)
    return {"resolved": resolved, "unknown": unknown, "invalid": invalid}


def _summary(case: dict) -> dict:
    a = _artifacts(case)
    out: dict[str, Any] = {"repr": repr(a), "errors": a.errors}
    try:
        a.raise_for_errors()
        out["error_message"] = None
    except AttachmentsError as e:
        out["error_message"] = str(e)
    return out


AREAS = {
    "present": _present,
    "chunk": _chunk,
    "tokens": _tokens,
    "imagesize": _imagesize,
    "limits": _limits,
    "wire": _wire,
    "dsl": _dsl,
    "pages": _pages,
    "options": _options,
    "summary": _summary,
}


def run(area: str, case: dict) -> dict:
    """Python's answer to one case, in the contract's JSON form."""
    return AREAS[area](case)
