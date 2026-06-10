"""Tests for the IR types: TypedDicts, error codes, and artifact helpers."""

from __future__ import annotations

from attachments.types import (
    ERROR_INVALID_OPTION,
    ERROR_MISSING_DEPENDENCY,
    ERROR_PARSE,
    ERROR_PASSWORD_REQUIRED,
    ERROR_PROCESSING,
    ERROR_SERVICE,
    ERROR_UNPACK,
    HEAVY_FEATURES,
    Artifact,
    ImageItem,
    error_artifact,
    is_missing_dependency,
    make_artifact,
    missing_dep_artifact,
    normalize_artifact,
)


class TestErrorCodes:
    """Error code constants are frozen by spec/IR-CONTRACT.md."""

    def test_values(self):
        assert ERROR_MISSING_DEPENDENCY == "missing-dependency"
        assert ERROR_PASSWORD_REQUIRED == "password-required"
        assert ERROR_PARSE == "parse-error"
        assert ERROR_UNPACK == "unpack-error"
        assert ERROR_SERVICE == "service-error"
        assert ERROR_INVALID_OPTION == "invalid-option"
        assert ERROR_PROCESSING == "processing-error"


class TestMakeArtifact:
    def test_defaults(self):
        a = make_artifact()
        assert a["text"] == ""
        assert a["images"] == []
        assert a["audio"] == []
        assert a["video"] == []
        assert a["meta"] == {}

    def test_with_values(self):
        img: ImageItem = {
            "name": "p1.png",
            "mimetype": "image/png",
            "bytes": b"\x89PNG",
        }
        a = make_artifact(
            text="hello",
            images=[img],
            meta={"kind": "test"},
        )
        assert a["text"] == "hello"
        assert len(a["images"]) == 1
        assert a["images"][0]["name"] == "p1.png"
        assert a["meta"]["kind"] == "test"

    def test_return_type_is_artifact(self):
        a = make_artifact(text="x")
        # Runtime check – TypedDict is just a dict at runtime
        assert isinstance(a, dict)
        keys = {"text", "images", "audio", "video", "meta"}
        assert keys == set(a.keys())


class TestErrorArtifact:
    def test_structure(self):
        a = error_artifact("broken.pdf", ERROR_PARSE, "not a PDF")
        assert a["text"] == ""
        assert a["images"] == []
        assert a["meta"]["source"] == "broken.pdf"
        assert a["meta"]["error"] == {"code": "parse-error", "message": "not a PDF"}

    def test_no_extra_meta_keys(self):
        a = error_artifact("f.txt", ERROR_PROCESSING, "boom")
        assert set(a["meta"].keys()) == {"source", "error"}


class TestMissingDepArtifact:
    def test_known_feature_includes_install_hint(self):
        a = missing_dep_artifact("report.docx", "docx")
        error = a["meta"]["error"]
        assert error["code"] == ERROR_MISSING_DEPENDENCY
        assert "pip install attachments[docx]" in error["message"]
        assert a["meta"]["source"] == "report.docx"

    def test_unknown_feature_falls_back_to_generic_hint(self):
        a = missing_dep_artifact("f.xyz", "xyz-format")
        error = a["meta"]["error"]
        assert error["code"] == ERROR_MISSING_DEPENDENCY
        assert "pip install" in error["message"]
        assert "xyz-format" in error["message"]


class TestHeavyVsLightMissingDepMessages:
    """Give until they ask: the hosted tier is mentioned ONLY for features
    whose local install is genuinely heavy (ocr, audio); light extras keep
    today's pip-install-only message byte-identical."""

    HOSTED_SENTENCE = (
        "Or use the free hosted tier: configure(service_url="
        '"https://api.attachments.dev/v1") - details at attachments.dev.'
    )

    def test_heavy_features_constant(self):
        assert HEAVY_FEATURES == frozenset({"ocr", "audio"})

    def test_heavy_features_mention_hosted_tier_after_local_remedy(self):
        for feature in sorted(HEAVY_FEATURES):
            message = missing_dep_artifact("f.bin", feature)["meta"]["error"]["message"]
            assert "pip install" in message
            assert message.endswith(self.HOSTED_SENTENCE)
            # Local remedy comes FIRST, the hosted tier second.
            assert message.index("pip install") < message.index("attachments.dev")

    def test_light_feature_message_is_byte_identical_to_plain_remedy(self):
        """Light extras never advertise — exact, byte-identical message."""
        from attachments.deps import check_dep

        for feature in ("pdf", "xlsx", "docx", "html"):
            status = check_dep(feature)
            missing = (
                f" (missing: {', '.join(status.missing)})" if status.missing else ""
            )
            expected = (
                f"Processing 'doc.bin' requires optional dependencies "
                f"for {feature!r}{missing}. Install with: {status.install_hint}"
            )
            a = missing_dep_artifact("doc.bin", feature)
            assert a["meta"]["error"]["message"] == expected
            assert "attachments.dev" not in a["meta"]["error"]["message"]

    def test_unknown_feature_stays_byte_identical_and_ad_free(self):
        a = missing_dep_artifact("f.xyz", "xyz-format")
        assert a["meta"]["error"]["message"] == (
            "Processing 'f.xyz' requires optional dependencies "
            "for 'xyz-format'. Install with: pip install attachments[xyz-format]"
        )


class TestIsMissingDependency:
    """Typed check — the only sanctioned fallback signal."""

    def test_true_for_missing_dep_artifact(self):
        assert is_missing_dependency(missing_dep_artifact("f.pdf", "pdf")) is True

    def test_true_for_handcrafted_code(self):
        a = error_artifact("f.pdf", ERROR_MISSING_DEPENDENCY, "no pypdf")
        assert is_missing_dependency(a) is True

    def test_false_for_other_error_codes(self):
        a = error_artifact("f.pdf", ERROR_PARSE, "corrupt file")
        assert is_missing_dependency(a) is False

    def test_false_for_success_artifact(self):
        assert is_missing_dependency(make_artifact(text="fine")) is False

    def test_false_for_empty_dict(self):
        assert is_missing_dependency({}) is False

    def test_false_for_legacy_string_error(self):
        # A non-dict error value must never be treated as missing-dep
        a = {"meta": {"error": "pypdf not installed"}}
        assert is_missing_dependency(a) is False


class TestNormalizeArtifact:
    def test_fills_required_keys(self):
        result = normalize_artifact({"text": "hello"}, "test.txt")

        assert result["text"] == "hello"
        assert result["images"] == []
        assert result["audio"] == []
        assert result["video"] == []
        assert result["meta"]["source"] == "test.txt"

    def test_fills_all_keys_from_empty(self):
        result = normalize_artifact({}, "f.bin")
        assert set(result.keys()) == {"text", "images", "audio", "video", "meta"}
        assert result["meta"] == {"source": "f.bin"}

    def test_preserves_existing_values(self):
        artifact = {
            "text": "hello",
            "images": [{"name": "img"}],
            "meta": {"kind": "text"},
        }
        result = normalize_artifact(artifact, "test.txt")

        assert result["text"] == "hello"
        assert len(result["images"]) == 1
        assert result["meta"]["kind"] == "text"
        assert result["meta"]["source"] == "test.txt"

    def test_does_not_override_existing_source(self):
        artifact = {"meta": {"source": "original.txt"}}
        result = normalize_artifact(artifact, "other.txt")
        assert result["meta"]["source"] == "original.txt"


class TestArtifactCompat:
    """Ensure the TypedDict is compatible with plain dicts at runtime."""

    def test_plain_dict_matches(self):
        plain: dict = {
            "text": "hi",
            "images": [],
            "audio": [],
            "video": [],
            "meta": {"source": "f.txt"},
        }
        a: Artifact = plain  # type: ignore[assignment]
        assert a["text"] == "hi"
