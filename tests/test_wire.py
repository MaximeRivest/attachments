"""Tests for the public wire form: Artifacts.to_wire / from_wire and the
artifact_to_wire / artifact_from_wire functions the server, the service
client and the CLI share.

Covers:
    - Round trip through real JSON text gives back an equal Artifacts
    - to_wire never modifies its input (the server's old encoder did)
    - Output validates against spec/artifact.schema.json
    - Bad data fails loudly (invalid base64, wrong types, non-list)
    - CLI --json emits the wire form (bytes_b64), not raw base64 under "bytes"
    - The service client turns an invalid response into ServiceError
"""

from __future__ import annotations

import base64
import copy
import json
from pathlib import Path

import jsonschema
import pytest

from attachments import (
    Artifacts,
    artifact_from_wire,
    artifact_to_wire,
    att,
    cli,
    configure,
)
from attachments.deps import check_dep
from attachments.service import ServiceError, process_via_service
from attachments.types import error_artifact, make_artifact

SCHEMA = json.loads(
    (
        Path(__file__).resolve().parent.parent / "spec" / "artifact.schema.json"
    ).read_text()
)
VALIDATOR = jsonschema.Draft202012Validator(SCHEMA)


def _with_image(payload: bytes = b"\x89PNG\r\n") -> Artifacts:
    return Artifacts(
        [
            make_artifact(
                text="page text",
                images=[
                    {
                        "name": "p-1.png",
                        "mimetype": "image/png",
                        "bytes": payload,
                        "page": 1,
                    }
                ],
                meta={
                    "source": "p.pdf",
                    "kind": "pdf",
                    "segments": [
                        {
                            "kind": "page",
                            "label": "page 1",
                            "start": 0,
                            "end": 9,
                            "page": 1,
                        }
                    ],
                    "extra": {"pages": 1},
                },
            ),
            error_artifact("missing.pdf", "unpack-error", "not found"),
        ]
    )


def test_round_trip_through_json_text_is_equal():
    a = _with_image()
    text = json.dumps(a.to_wire())
    b = Artifacts.from_wire(json.loads(text))
    assert isinstance(b, Artifacts)
    assert b == a
    assert b.images[0]["bytes"] == b"\x89PNG\r\n"


def test_json_dumps_fails_on_raw_artifacts_with_images_but_not_on_wire():
    a = _with_image()
    with pytest.raises(TypeError):
        json.dumps(a)
    json.dumps(a.to_wire())


def test_to_wire_never_modifies_the_original():
    a = _with_image()
    before = copy.deepcopy(list(a))
    wire = a.to_wire()
    assert list(a) == before
    wire[0]["meta"]["extra"]["pages"] = 99  # no shared nested state either
    assert a[0]["meta"]["extra"]["pages"] == 1


def test_wire_images_carry_bytes_b64_only_in_the_same_key_position():
    image = _with_image().to_wire()[0]["images"][0]
    assert list(image) == ["name", "mimetype", "bytes_b64", "page"]
    assert base64.b64decode(image["bytes_b64"]) == b"\x89PNG\r\n"


def test_every_wire_item_validates_against_the_schema():
    for item in _with_image().to_wire():
        VALIDATOR.validate(item)


@pytest.mark.skipif(not check_dep("pdf-images").available, reason="PyMuPDF needed")
def test_real_pdf_round_trip(tmp_path):
    pymupdf = pytest.importorskip("pymupdf")
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "hello")
    path = tmp_path / "r.pdf"
    doc.save(path)
    doc.close()

    a = att(f"{path}[images: true, dpi: 36]")
    data = json.loads(json.dumps(a.to_wire()))
    for item in data:
        VALIDATOR.validate(item)
    assert Artifacts.from_wire(data) == a


def test_from_wire_rejects_invalid_base64_loudly():
    data = _with_image().to_wire()
    data[0]["images"][0]["bytes_b64"] = "not base64!"
    with pytest.raises(ValueError, match="p.pdf: image 'p-1.png' has invalid base64"):
        Artifacts.from_wire(data)


@pytest.mark.parametrize(
    "item, error",
    [
        ({"text": 3, "meta": {"source": "x"}}, ValueError),
        ({"images": {}, "meta": {"source": "x"}}, ValueError),
        ({"images": ["x"], "meta": {"source": "x"}}, ValueError),
        ({"meta": []}, ValueError),
        (
            {"images": [{"name": "i", "bytes_b64": 5}], "meta": {"source": "x"}},
            ValueError,
        ),
        ("not a dict", TypeError),
    ],
)
def test_from_wire_rejects_wrong_types(item, error):
    with pytest.raises(error):
        artifact_from_wire(item)


def test_from_wire_requires_a_list():
    with pytest.raises(TypeError, match="expects a list"):
        Artifacts.from_wire({"text": "x"})


def test_from_wire_fills_missing_required_keys():
    art = artifact_from_wire({"text": "hi", "meta": {"source": "a.txt"}})
    assert art == make_artifact(text="hi", meta={"source": "a.txt"})


def test_from_wire_never_invents_a_source():
    # The service may omit meta.source; att() then sets the real file name
    # with setdefault, which a placeholder would block.
    art = artifact_from_wire({"text": "hi"})
    assert art["meta"] == {}
    assert art["images"] == [] and art["audio"] == [] and art["video"] == []


def test_service_response_without_source_gets_the_real_file_name(monkeypatch):
    from attachments.core import _process_via_service

    configure(api_key="key", service_url="http://svc")
    reply = {"text": "ok", "images": [], "audio": [], "video": [], "meta": {}}
    monkeypatch.setattr("attachments.service._get_client", lambda: _Client(reply))
    from attachments.types import normalize_artifact

    art = normalize_artifact(_process_via_service("q3.pdf", b"x", "key"), "q3.pdf")
    assert art["meta"]["source"] == "q3.pdf"
    assert art["meta"]["via"] == "service"


def test_in_process_bytes_win_when_both_keys_are_present():
    image = {
        "name": "i.png",
        "mimetype": "image/png",
        "bytes": b"real",
        "bytes_b64": "c3RhbGU=",
    }
    art = make_artifact(images=[image], meta={"source": "i.png"})
    wire = artifact_to_wire(art)
    assert wire["images"][0] == {
        "name": "i.png",
        "mimetype": "image/png",
        "bytes_b64": "cmVhbA==",
    }
    assert artifact_from_wire({**wire, "images": [image]})["images"][0] == {
        "name": "i.png",
        "mimetype": "image/png",
        "bytes": b"real",
    }


@pytest.mark.skipif(not check_dep("image").available, reason="Pillow needed")
def test_cli_json_emits_the_wire_form(tmp_path, capsys):
    from PIL import Image

    png = tmp_path / "dot.png"
    Image.new("RGB", (3, 2), "blue").save(png)
    code = cli.main([str(png), "--json"])
    data = json.loads(capsys.readouterr().out)
    assert code == 0
    for item in data:
        VALIDATOR.validate(item)
    assert "bytes" not in data[0]["images"][0]
    assert Artifacts.from_wire(data).images[0]["bytes"] == png.read_bytes()


class _Response:
    status_code = 200
    text = ""

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _Client:
    def __init__(self, payload):
        self.payload = payload

    def post(self, url, **kwargs):
        return _Response(self.payload)


def test_service_invalid_artifact_is_a_service_error(monkeypatch):
    configure(api_key="key", service_url="http://svc")
    bad = {"text": "", "images": [{"name": "p.png", "bytes_b64": "%%"}], "meta": {}}
    monkeypatch.setattr("attachments.service._get_client", lambda: _Client(bad))
    with pytest.raises(ServiceError, match="invalid artifact"):
        process_via_service(b"x", filename="a.pdf")
