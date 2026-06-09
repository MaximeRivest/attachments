"""
Tests for the configuration system.

=============================================================================
TEST GUIDELINES FOR CONFIG
=============================================================================

GOOD tests for config:
    - Test configure() with valid and invalid values
    - Test environment variable precedence
    - Test get_* helpers with and without overrides
    - Test reset_config() restores defaults
    - Always clean up after modifying env vars

BAD tests for config:
    - Not using the autouse reset fixture (leaks state)
    - Testing private implementation details
    - Hardcoding config values that might change

IMPORTANT:
    The conftest.py has autouse fixtures to reset config after each test.
    If you need to test env vars, use monkeypatch to avoid pollution.

=============================================================================
"""

from __future__ import annotations

import pytest

from attachments.config import (
    configure,
    get_api_key,
    get_config,
    get_prefer,
    get_service_url,
    reset_config,
)


class TestConfigure:
    """Tests for configure() function."""

    def test_set_api_key(self):
        configure(api_key="test_key_123")
        assert get_config("api_key") == "test_key_123"

    def test_set_prefer_local(self):
        configure(prefer="local")
        assert get_config("prefer") == "local"

    def test_set_prefer_service(self):
        configure(prefer="service")
        assert get_config("prefer") == "service"

    def test_set_prefer_local_only(self):
        configure(prefer="local-only")
        assert get_config("prefer") == "local-only"

    def test_set_prefer_service_only(self):
        configure(prefer="service-only")
        assert get_config("prefer") == "service-only"

    def test_set_service_url(self):
        configure(service_url="https://custom.example.com/api")
        assert get_config("service_url") == "https://custom.example.com/api"

    def test_set_timeout(self):
        configure(timeout=120)
        assert get_config("timeout") == 120

    def test_set_multiple_options(self):
        configure(api_key="key", prefer="service", timeout=30)
        assert get_config("api_key") == "key"
        assert get_config("prefer") == "service"
        assert get_config("timeout") == 30

    def test_invalid_prefer_value(self):
        with pytest.raises(ValueError, match="Invalid prefer value"):
            configure(prefer="invalid_mode")

    def test_invalid_config_key(self):
        with pytest.raises(ValueError, match="Invalid config keys"):
            configure(nonexistent_key="value")

    def test_multiple_invalid_keys(self):
        with pytest.raises(ValueError, match="Invalid config keys"):
            configure(bad_key1="a", bad_key2="b")


class TestGetConfig:
    """Tests for get_config() function."""

    def test_default_api_key_is_none(self):
        assert get_config("api_key") is None

    def test_default_prefer_is_local(self):
        assert get_config("prefer") == "local"

    def test_default_timeout(self):
        assert get_config("timeout") == 60

    def test_custom_default(self):
        assert get_config("nonexistent", default="fallback") == "fallback"

    def test_configured_value_overrides_default(self):
        configure(timeout=999)
        assert get_config("timeout") == 999


class TestEnvVarPrecedence:
    """Tests for environment variable precedence."""

    def test_env_var_overrides_default(self, monkeypatch):
        monkeypatch.setenv("ATTACHMENTS_API_KEY", "env_key")
        assert get_config("api_key") == "env_key"

    def test_env_var_overrides_configured(self, monkeypatch):
        configure(api_key="configured_key")
        monkeypatch.setenv("ATTACHMENTS_API_KEY", "env_key")
        # Env var takes precedence
        assert get_config("api_key") == "env_key"

    def test_env_var_prefer(self, monkeypatch):
        monkeypatch.setenv("ATTACHMENTS_PREFER", "service-only")
        assert get_config("prefer") == "service-only"

    def test_env_var_service_url(self, monkeypatch):
        monkeypatch.setenv("ATTACHMENTS_SERVICE_URL", "https://env.example.com")
        assert get_config("service_url") == "https://env.example.com"


class TestGetApiKey:
    """Tests for get_api_key() helper."""

    def test_override_takes_precedence(self):
        configure(api_key="configured")
        assert get_api_key("override") == "override"

    def test_falls_back_to_config(self):
        configure(api_key="configured")
        assert get_api_key() == "configured"

    def test_returns_none_if_not_set(self):
        assert get_api_key() is None

    def test_env_var_used(self, monkeypatch):
        monkeypatch.setenv("ATTACHMENTS_API_KEY", "from_env")
        assert get_api_key() == "from_env"


class TestGetPrefer:
    """Tests for get_prefer() helper."""

    def test_override_takes_precedence(self):
        configure(prefer="local-only")
        assert get_prefer("service") == "service"

    def test_falls_back_to_config(self):
        configure(prefer="service-only")
        assert get_prefer() == "service-only"

    def test_default_is_local(self):
        assert get_prefer() == "local"


class TestGetServiceUrl:
    """Tests for get_service_url() helper."""

    def test_override_takes_precedence(self):
        configure(service_url="https://configured.com")
        assert get_service_url("https://override.com") == "https://override.com"

    def test_falls_back_to_config(self):
        configure(service_url="https://configured.com")
        assert get_service_url() == "https://configured.com"

    def test_default_url(self):
        assert "attachments" in get_service_url()


class TestResetConfig:
    """Tests for reset_config() function."""

    def test_resets_api_key(self):
        configure(api_key="test")
        reset_config()
        assert get_config("api_key") is None

    def test_resets_prefer(self):
        configure(prefer="service-only")
        reset_config()
        assert get_config("prefer") == "local"

    def test_resets_timeout(self):
        configure(timeout=999)
        reset_config()
        assert get_config("timeout") == 60

    def test_resets_service_url(self):
        configure(service_url="https://custom.com")
        reset_config()
        assert "attachments" in get_config("service_url")
