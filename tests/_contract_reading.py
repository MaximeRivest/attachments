"""Python's driver for the reading cases (contract/reading.md).

Like ``_contract.py``: ``AREAS[area](case)`` is Python's answer in the
contract's JSON form. Artifacts are compared in wire form without error
messages (codes are pinned, wording is not: install advice differs by
language).
"""

from __future__ import annotations

import base64
import contextlib
import io
import logging
import os
import tempfile
import warnings
from pathlib import Path
from typing import Any

from attachments import att, reset_config
from attachments._mentions import find_mentions
from attachments._processors.text import text_processor
from attachments._sources._ignore import (
    IgnoreEngine,
    _decide,
    compile_rules,
    looks_like_key,
)
from attachments._sources.local import _looks_like_glob, _pattern_regex, _split_pattern
from attachments.types import artifact_to_wire
from attachments.utils import detect_extension, is_text_bytes

#: What this implementation has of the contract's declared extensions.
EXTENSIONS = {"archive/bz2-xz"}


def normalize(artifacts: list[dict]) -> list[dict]:
    """Wire form, error messages left out."""
    out = []
    for artifact in artifacts:
        wire = artifact_to_wire(artifact)
        error = wire.get("meta", {}).get("error")
        if isinstance(error, dict):
            wire["meta"]["error"] = {"code": error.get("code")}
        out.append(wire)
    return out


def write_fixture(root: Path, files: dict[str, Any]) -> None:
    for rel, spec in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(spec, str):
            path.write_bytes(spec.encode("utf-8"))
        elif "b64" in spec:
            path.write_bytes(base64.b64decode(spec["b64"]))
        elif "link" in spec:
            os.symlink(spec["link"], path)
        elif spec.get("dir"):
            path.mkdir(exist_ok=True)


_FIXTURES: dict[str, Path] = {}


def fixture(name: str, files: dict[str, Any]) -> Path:
    """The fixture written once per test run, in a folder of its own."""
    if name not in _FIXTURES:
        root = Path(tempfile.mkdtemp(prefix="attachments-contract-"))
        write_fixture(root, files)
        _FIXTURES[name] = root
    return _FIXTURES[name]


@contextlib.contextmanager
def isolated(cwd: Path | None = None):
    """No settings from the environment or earlier calls; *cwd* current."""
    saved = {
        k: os.environ.pop(k) for k in list(os.environ) if k.startswith("ATTACHMENTS_")
    }
    reset_config()
    previous = os.getcwd()
    logging.disable(logging.CRITICAL)
    try:
        if cwd is not None:
            os.chdir(cwd)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            yield
    finally:
        logging.disable(logging.NOTSET)
        os.chdir(previous)
        os.environ.update(saved)
        reset_config()


def _input(spec: Any) -> Any:
    if isinstance(spec, list):
        return [_input(s) for s in spec]
    if isinstance(spec, str):
        return spec
    if "bytes_b64" in spec:
        f = io.BytesIO(base64.b64decode(spec["bytes_b64"]))
        if spec.get("name") is not None:
            f.name = spec["name"]
        return f
    if "bare_bytes_b64" in spec:
        return base64.b64decode(spec["bare_bytes_b64"])
    if "number" in spec:
        return spec["number"]
    raise AssertionError(spec)


def run_att(case: dict, cwd: Path | None = None) -> dict:
    with isolated(cwd):
        result = att(
            _input(case["input"]), prefer="local-only", **(case.get("options") or {})
        )
    return {"artifacts": normalize(result)}


def _trees(case: dict, fixtures: dict[str, dict]) -> dict:
    root = fixture(case["fixture"], fixtures[case["fixture"]])
    return run_att(case, cwd=root)


def _ignore(case: dict) -> dict:
    if case["call"] == "decide":
        return {
            "value": _decide(
                compile_rules(case["patterns"]), case["path"], case["is_dir"]
            )
        }
    if case["call"] == "check":
        e = case["engine"]
        engine = IgnoreEngine(
            extra=e.get("extra", []),
            defaults=e.get("defaults", True),
            hidden=e.get("hidden", False),
        )
        return {"value": engine.check(case["path"], is_dir=case["is_dir"])}
    if case["call"] == "key":
        return {"value": looks_like_key(base64.b64decode(case["bytes_b64"]))}
    raise AssertionError(case["call"])


def _globs(case: dict) -> dict:
    if case["call"] == "split":
        base, components = _split_pattern(case["pattern"])
        return {"value": [base, components]}
    if case["call"] == "match":
        regex = _pattern_regex(case["components"], case["hidden"])
        return {"value": bool(regex.fullmatch(case["path"]))}
    if case["call"] == "is_pattern":
        return {"value": _looks_like_glob(case["text"])}
    raise AssertionError(case["call"])


def _text(case: dict) -> dict:
    data = base64.b64decode(case["bytes_b64"])
    if case["call"] == "text":
        artifact = text_processor(data, filename="t.txt")
        return {"value": {"text": artifact["text"], "meta": artifact["meta"]}}
    if case["call"] == "sniff":
        return {"value": detect_extension(data)}
    if case["call"] == "is_text":
        return {"value": is_text_bytes(data)}
    raise AssertionError(case["call"])


def _mentions(case: dict) -> dict:
    return {
        "value": [
            {"text": m.text, "explicit": m.explicit, "url": m.url}
            for m in find_mentions(case["prompt"])
        ]
    }


AREAS = {
    "inputs": lambda case, doc: run_att(case),
    "archives": lambda case, doc: run_att(case),
    "trees": lambda case, doc: _trees(case, doc["fixtures"]),
    "ignore": lambda case, doc: _ignore(case),
    "globs": lambda case, doc: _globs(case),
    "text": lambda case, doc: _text(case),
    "mentions": lambda case, doc: _mentions(case),
}


# ---------------------------------------------------------------------------
# Scripted HTTP servers: a fake service and a fake web
# ---------------------------------------------------------------------------

import json  # noqa: E402
import threading  # noqa: E402
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # noqa: E402

from attachments import configure  # noqa: E402
from attachments._options import Option, register_options, reset_options  # noqa: E402
from attachments._processors import processors as _processors  # noqa: E402
from attachments._processors import reset_processors  # noqa: E402
from attachments._sources._guards import private_url_guard  # noqa: E402
from attachments.types import error_artifact, make_artifact  # noqa: E402


def parse_multipart(content_type: str, body: bytes) -> dict:
    """The parts as the Python server reads them: file name, fields as JSON."""
    boundary = content_type.split("boundary=", 1)[1].strip('"').encode()
    out: dict[str, Any] = {"filename": None, "fields": {}, "file_b64": None}
    for part in body.split(b"--" + boundary):
        if b"\r\n\r\n" not in part:
            continue
        head, content = part.split(b"\r\n\r\n", 1)
        if content.endswith(b"\r\n"):
            content = content[:-2]
        headers = head.decode("utf-8", "replace")
        if 'filename="' in headers:
            start = headers.index('filename="') + 10
            out["filename"] = headers[start : headers.index('"', start)]
            out["file_b64"] = base64.b64encode(content).decode()
        elif 'name="' in headers:
            start = headers.index('name="') + 6
            out["fields"][headers[start : headers.index('"', start)]] = json.loads(
                content
            )
    return out


class Scripted:
    """A server on 127.0.0.1 answering from a script, recording requests."""

    def __init__(self, answer):
        self.requests: list[dict] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def _answer(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length)
                status, headers, payload = answer(self, body)
                self.send_response(status)
                for k, v in headers.items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            do_GET = do_POST = _answer

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.outer = outer

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def fake_service(answers: list[dict]) -> Scripted:
    queue = list(answers)
    service: Scripted

    def answer(handler, body):
        service.requests.append(
            {
                "method": handler.command,
                "path": handler.path,
                "auth": handler.headers.get("Authorization"),
                **parse_multipart(handler.headers.get("Content-Type", ""), body),
            }
        )
        reply = (
            queue.pop(0)
            if queue
            else {"status": 500, "json": {"error": "no answer left"}}
        )
        payload = (
            json.dumps(reply["json"]).encode()
            if "json" in reply
            else reply["body"].encode()
        )
        return reply["status"], {"Content-Type": "application/json"}, payload

    service = Scripted(answer)
    return service


def fake_web(routes: dict[str, dict]) -> Scripted:
    def answer(handler, body):
        route = routes.get(handler.path, {"status": 404, "body": "no route"})
        payload = (
            base64.b64decode(route["body_b64"])
            if "body_b64" in route
            else route.get("body", "").encode()
        )
        return route["status"], dict(route.get("headers", {})), payload

    return Scripted(answer)


def replace_base(value: Any, base: str, name: str) -> Any:
    if isinstance(value, str):
        return value.replace(base, name)
    if isinstance(value, list):
        return [replace_base(v, base, name) for v in value]
    if isinstance(value, dict):
        return {k: replace_base(v, base, name) for k, v in value.items()}
    return value


def _fake_processor(behavior: str):
    def fn(data: bytes, *, filename=None, **kwargs):
        if behavior == "text":
            extra = {k: kwargs[k] for k in ("password", "dpi") if k in kwargs}
            meta: dict[str, Any] = {"kind": "text"}
            if extra:
                meta["extra"] = extra
            return make_artifact(text=data.decode("utf-8", "replace"), meta=meta)
        if behavior == "missing":
            return error_artifact(
                filename, "missing-dependency", "the fake reader is missing"
            )
        if behavior == "partial":
            return make_artifact(
                text="partial text",
                meta={
                    "extra": {"missing_dependency": "image"},
                    "warnings": ["pictures not made"],
                },
            )
        if behavior == "parse-error":
            return error_artifact(filename, "parse-error", "bad")
        if behavior == "throw":
            raise RuntimeError("boom")
        if behavior == "missing-module":
            raise ModuleNotFoundError("No module named 'fakelib'", name="fakelib")
        raise AssertionError(behavior)

    return fn


def _routing(case: dict, doc: dict) -> dict:
    root = Path(tempfile.mkdtemp(prefix="attachments-routing-"))
    _processors[".fake"] = _fake_processor(case["behavior"])
    register_options(".fake", tuple(Option(**o) for o in doc["fake_options"]))
    service = fake_service(case["service"]["answers"]) if "service" in case else None
    try:
        with isolated(root):
            settings: dict[str, Any] = {}
            if service is not None:
                settings["service_url"] = service.base + (
                    "/v1" if case["service"]["v1"] else ""
                )
            if "api_key" in case:
                settings["api_key"] = case["api_key"]
            configure(**settings)
            spec = case["input"]
            if "text" in spec:
                (root / spec["file"]).write_bytes(base64.b64decode(spec["bytes_b64"]))
                given: Any = spec["text"]
            else:
                given = _input(spec)
            result = att(given, prefer=case["prefer"], **case["options"])
        return {
            "artifacts": normalize(result),
            "requests": service.requests if service is not None else [],
        }
    finally:
        if service is not None:
            service.close()
        reset_processors()
        reset_options()


def _downloads(case: dict, doc: dict) -> dict:
    web = fake_web(doc["routes"])
    try:
        with isolated(), private_url_guard(case["block_private"]):
            result = att(
                web.base + case["path"], prefer="local-only", **case["options"]
            )
        return {"artifacts": replace_base(normalize(result), web.base, "http://HOST")}
    finally:
        web.close()


def _naming(case: dict) -> dict:
    from attachments._sources._guards import _sanitize_member_name
    from attachments._sources.http import (
        _filename_from_content_disposition,
        _github_raw_url,
        _name_for_content_type,
    )

    if case["call"] == "disposition":
        return {"value": _filename_from_content_disposition(case["value"])}
    if case["call"] == "type":
        name, warning = _name_for_content_type(
            case["filename"], case["content_type"], case["url"]
        )
        return {"value": [name, warning]}
    if case["call"] == "raw":
        return {"value": _github_raw_url(case["url"])}
    return {"value": _sanitize_member_name(case["value"])}


AREAS["routing"] = _routing
AREAS["downloads"] = _downloads
AREAS["naming"] = lambda case, doc: _naming(case)
