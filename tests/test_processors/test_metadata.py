"""Photos lose what they say about their owner (GPS, dates, camera), not
their pixels or colour profile."""

from __future__ import annotations

import io

import pytest

from attachments import att
from attachments._processors._metadata import strip_metadata

Image = pytest.importorskip("PIL.Image")
ImageCms = pytest.importorskip("PIL.ImageCms")

ICC = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
XMP = b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF/></x:xmpmeta>'


def _exif():
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"  # camera make
    gps = exif.get_ifd(0x8825)
    gps[1], gps[2] = "N", (45.0, 30.0, 0.0)
    gps[3], gps[4] = "W", (73.0, 34.0, 0.0)
    return exif


def _photo(fmt: str, **kw) -> bytes:
    image = Image.effect_noise((64, 48), 40).convert("RGB")
    buffer = io.BytesIO()
    image.save(buffer, fmt, exif=_exif(), icc_profile=ICC, xmp=XMP, **kw)
    return buffer.getvalue()


def _pixels(data: bytes) -> bytes:
    return Image.open(io.BytesIO(data)).convert("RGB").tobytes()


@pytest.mark.parametrize(
    ("fmt", "mimetype", "kw"),
    [
        ("JPEG", "image/jpeg", {}),
        ("JPEG", "image/jpeg", {"progressive": True}),
        ("PNG", "image/png", {}),
        ("WEBP", "image/webp", {"lossless": True}),
    ],
)
def test_location_goes_pixels_and_colours_stay(fmt, mimetype, kw):
    data = _photo(fmt, **kw)
    clean, removed = strip_metadata(data, mimetype)
    assert "exif" in removed
    assert b"PhoneMaker" not in clean
    cleaned = Image.open(io.BytesIO(clean))
    assert not cleaned.getexif()
    assert cleaned.info.get("icc_profile") == ICC
    assert _pixels(clean) == _pixels(data)


def test_jpeg_trailer_and_comment_go():
    data = _photo("JPEG")
    data = data[:2] + b"\xff\xfe\x00\x0bmy secret" + data[2:] + b"vendor trailer"
    clean, removed = strip_metadata(data, "image/jpeg")
    assert removed == ["comment", "exif", "trailing data", "xmp"]
    assert clean.endswith(b"\xff\xd9")
    assert _pixels(clean) == _pixels(data)


@pytest.mark.parametrize(
    "broken",
    [b"\xff\xd8\xff\xe1\xff\xff", b"\x89PNG\r\n\x1a\n\x00\x00", b"RIFF\0\0\0\0WEBPX"],
)
def test_damaged_files_are_left_alone(broken):
    mimetype = {b"\xff": "image/jpeg", b"\x89": "image/png", b"R": "image/webp"}[
        broken[:1]
    ]
    assert strip_metadata(broken, mimetype) == (broken, [])


def test_att_strips_by_default_and_keeps_on_request(tmp_path):
    path = tmp_path / "phone.jpg"
    path.write_bytes(_photo("JPEG"))
    plain = att(str(path))[0]
    assert b"PhoneMaker" not in plain["images"][0]["bytes"]
    assert plain["meta"]["extra"]["metadata_removed"] == ["exif", "xmp"]
    kept = att(f"{path}[metadata: true]")[0]
    assert kept["images"][0]["bytes"] == path.read_bytes()


def test_resized_photo_has_no_metadata_either(tmp_path):
    path = tmp_path / "phone.jpg"
    path.write_bytes(_photo("JPEG"))
    shrunk = att(f"{path}[max_dim: 32]")[0]["images"][0]["bytes"]
    assert b"PhoneMaker" not in shrunk and not Image.open(io.BytesIO(shrunk)).getexif()


def test_photos_inside_word_and_powerpoint(tmp_path):
    docx = pytest.importorskip("docx")
    pptx = pytest.importorskip("pptx")
    photo = tmp_path / "phone.jpg"
    photo.write_bytes(_photo("JPEG"))

    document = docx.Document()
    document.add_picture(str(photo))
    document.save(tmp_path / "report.docx")
    deck = pptx.Presentation()
    deck.slides.add_slide(deck.slide_layouts[6]).shapes.add_picture(str(photo), 0, 0)
    deck.save(tmp_path / "deck.pptx")

    for name in ("report.docx", "deck.pptx"):
        images = att(f"{tmp_path / name}[embedded_images: true]").images
        assert images, name
        assert all(b"PhoneMaker" not in im["bytes"] for im in images), name
