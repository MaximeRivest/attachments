"""
Tests for the dependency detection system.

=============================================================================
TEST GUIDELINES FOR DEPS
=============================================================================

GOOD tests for deps:
    - Test check_dep returns correct structure (DepStatus)
    - Test check_deps returns all expected features
    - Test require() raises ImportError with helpful message
    - Test suggest_install generates correct pip commands
    - Test cache clearing works

BAD tests for deps:
    - Testing that specific deps ARE installed (environment-dependent)
    - Mocking importlib.util.find_spec (fragile, tests implementation)
    - Not clearing cache between tests that modify import behavior

NOTES:
    - These tests verify the structure and behavior, not actual availability
    - Actual dep availability varies by environment
    - Use clear_cache() if you mock import behavior

=============================================================================
"""

from __future__ import annotations

import pytest

from attachments.deps import (
    DEPENDENCY_MAP,
    DepStatus,
    check_dep,
    check_deps,
    clear_cache,
    has_local,
    has_service,
    require,
    suggest_install,
)


class TestCheckDep:
    """Tests for check_dep() function."""

    def test_returns_dep_status(self):
        result = check_dep("pdf")
        assert isinstance(result, DepStatus)

    def test_dep_status_has_required_fields(self):
        result = check_dep("pdf")
        assert hasattr(result, "available")
        assert hasattr(result, "modules")
        assert hasattr(result, "missing")
        assert hasattr(result, "install_hint")

    def test_available_is_bool(self):
        result = check_dep("pdf")
        assert isinstance(result.available, bool)

    def test_modules_is_tuple(self):
        result = check_dep("pdf")
        assert isinstance(result.modules, tuple)

    def test_missing_is_tuple(self):
        result = check_dep("pdf")
        assert isinstance(result.missing, tuple)

    def test_install_hint_is_string(self):
        result = check_dep("pdf")
        assert isinstance(result.install_hint, str)
        assert "pip install" in result.install_hint

    def test_invalid_feature_raises(self):
        with pytest.raises(ValueError, match="Unknown feature"):
            check_dep("nonexistent_feature")

    def test_all_known_features(self):
        """Every feature in DEPENDENCY_MAP should work."""
        for feature in DEPENDENCY_MAP:
            result = check_dep(feature)
            assert isinstance(result, DepStatus)

    @pytest.mark.parametrize(
        "feature,expected_modules",
        [
            ("pdf", ("pypdf|PyPDF2", "pymupdf")),
            ("xlsx", ("openpyxl",)),
            ("service", ("httpx",)),
        ],
    )
    def test_expected_modules(self, feature: str, expected_modules: tuple):
        result = check_dep(feature)
        assert result.modules == expected_modules


class TestCheckDeps:
    """Tests for check_deps() function."""

    def test_returns_dict(self):
        result = check_deps()
        assert isinstance(result, dict)

    def test_all_values_are_bool(self):
        result = check_deps()
        for feature, available in result.items():
            assert isinstance(available, bool), f"{feature} is not bool"

    def test_contains_expected_features(self):
        result = check_deps()
        expected = ["pdf", "xlsx", "docx", "service", "s3"]
        for feature in expected:
            assert feature in result, f"Missing {feature}"

    def test_matches_dependency_map(self):
        result = check_deps()
        assert set(result.keys()) == set(DEPENDENCY_MAP.keys())


class TestRequire:
    """Tests for require() function."""

    def test_invalid_feature_raises_value_error(self):
        """Unknown feature raises ValueError, not ImportError."""
        with pytest.raises(ValueError, match="Unknown feature"):
            require("nonexistent")

    def test_missing_dep_raises_import_error(self, monkeypatch):
        """If deps are missing, ImportError is raised."""
        # Clear cache and mock to simulate missing dep
        clear_cache()

        # We can't easily mock find_spec, so we test with a feature
        # that's definitely not installed in most envs
        # Skip this test if audio IS installed (unlikely)
        status = check_dep("audio")
        if not status.available:
            with pytest.raises(ImportError, match="Missing dependencies"):
                require("audio")

    def test_import_error_includes_install_hint(self, monkeypatch):
        """ImportError message includes install instructions."""
        status = check_dep("audio")
        if not status.available:
            with pytest.raises(ImportError, match="pip install"):
                require("audio")


class TestHasService:
    """Tests for has_service() helper."""

    def test_returns_bool(self):
        result = has_service()
        assert isinstance(result, bool)

    def test_matches_check_dep(self):
        expected = check_dep("service").available
        assert has_service() == expected


class TestHasLocal:
    """Tests for has_local() helper."""

    def test_returns_bool(self):
        result = has_local("pdf")
        assert isinstance(result, bool)

    def test_matches_check_dep(self):
        for feature in ["pdf", "xlsx", "docx"]:
            expected = check_dep(feature).available
            assert has_local(feature) == expected

    def test_invalid_feature_raises(self):
        with pytest.raises(ValueError):
            has_local("nonexistent")


class TestSuggestInstall:
    """Tests for suggest_install() function."""

    def test_single_feature(self):
        result = suggest_install(["pdf"])
        assert result == "pip install attachments[pdf]"

    def test_multiple_features(self):
        result = suggest_install(["pdf", "xlsx", "docx"])
        assert result == "pip install attachments[pdf,xlsx,docx]"

    def test_empty_list(self):
        result = suggest_install([])
        assert result == ""

    def test_invalid_features_ignored(self):
        result = suggest_install(["invalid", "also_invalid"])
        assert result == ""

    def test_mixed_valid_invalid(self):
        result = suggest_install(["pdf", "invalid", "xlsx"])
        assert result == "pip install attachments[pdf,xlsx]"

    def test_preserves_order(self):
        result = suggest_install(["xlsx", "pdf", "docx"])
        assert result == "pip install attachments[xlsx,pdf,docx]"


class TestClearCache:
    """Tests for clear_cache() function."""

    def test_no_error(self):
        """clear_cache() should not raise."""
        clear_cache()  # Should not raise

    def test_can_call_multiple_times(self):
        """Multiple calls should be safe."""
        clear_cache()
        clear_cache()
        clear_cache()


class TestDepStatusNamedTuple:
    """Tests for DepStatus structure."""

    def test_can_access_by_name(self):
        status = check_dep("pdf")
        _ = status.available
        _ = status.modules
        _ = status.missing
        _ = status.install_hint

    def test_can_access_by_index(self):
        status = check_dep("pdf")
        _ = status[0]  # available
        _ = status[1]  # modules
        _ = status[2]  # missing
        _ = status[3]  # install_hint

    def test_can_unpack(self):
        available, modules, missing, hint = check_dep("pdf")
        assert isinstance(available, bool)
        assert isinstance(modules, tuple)


class TestDependencyMapCompleteness:
    """Tests to ensure DEPENDENCY_MAP is well-formed."""

    def test_all_entries_have_modules(self):
        for feature, (modules, hint) in DEPENDENCY_MAP.items():
            assert len(modules) > 0, f"{feature} has no modules"

    def test_all_entries_have_hints(self):
        for feature, (modules, hint) in DEPENDENCY_MAP.items():
            assert "pip install" in hint, f"{feature} missing pip hint"

    def test_no_empty_module_names(self):
        for feature, (modules, hint) in DEPENDENCY_MAP.items():
            for module in modules:
                assert module.strip(), f"{feature} has empty module"
