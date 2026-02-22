"""Tests for Artifact / ImageItem TypedDicts and make_artifact helper."""

from __future__ import annotations

from attachments.types import Artifact, ImageItem, make_artifact


class TestMakeArtifact:
    def test_defaults(self):
        a = make_artifact()
        assert a["text"] == ""
        assert a["images"] == []
        assert a["audio"] == []
        assert a["video"] == []
        assert a["flags"] == {}

    def test_with_values(self):
        img: ImageItem = {
            "name": "p1.png",
            "mimetype": "image/png",
            "bytes": b"\x89PNG",
        }
        a = make_artifact(
            text="hello",
            images=[img],
            flags={"kind": "test"},
        )
        assert a["text"] == "hello"
        assert len(a["images"]) == 1
        assert a["images"][0]["name"] == "p1.png"
        assert a["flags"]["kind"] == "test"

    def test_return_type_is_artifact(self):
        a = make_artifact(text="x")
        # Runtime check – TypedDict is just a dict at runtime
        assert isinstance(a, dict)
        keys = {"text", "images", "audio", "video", "flags"}
        assert keys == set(a.keys())


class TestArtifactCompat:
    """Ensure the TypedDict is compatible with existing plain dicts."""

    def test_existing_dict_matches(self):
        legacy: dict = {
            "text": "hi",
            "images": [],
            "audio": [],
            "video": [],
            "flags": {"source": "f.txt"},
        }
        # Should be assignable to Artifact without error at runtime
        a: Artifact = legacy  # type: ignore[assignment]
        assert a["text"] == "hi"
