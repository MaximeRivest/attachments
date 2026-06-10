"""Global configuration for attachments library.

Configuration can be set via:
1. Environment variables (ATTACHMENTS_API_KEY, ATTACHMENTS_SERVICE_URL, etc.)
2. Global configure() call
3. Per-call options (highest priority)

Example::

    import attachments

    attachments.configure(api_key="att_...", prefer="local")
    attachments.att("file.pdf")  # Uses local if deps available, else service
"""

from __future__ import annotations

import os
from typing import Literal

# Valid values for the "prefer" setting
PreferMode = Literal["local", "service", "local-only", "service-only"]
_VALID_PREFER = ("local", "service", "local-only", "service-only")

# Default configuration
_config: dict = {
    "api_key": None,
    "prefer": "local",  # local | service | local-only | service-only
    "service_url": "https://api.attachments.dev/v1",
    "timeout": 60,  # seconds for service requests
}


def _coerce_env_value(key: str, raw: str):
    """Validate/coerce an ``ATTACHMENTS_*`` env value like configure() input.

    Environment variables are a first-class config path, so they get the
    same typing and validation as ``configure()`` arguments: ``timeout``
    becomes a number, ``prefer`` must be a valid mode. Invalid values raise
    ``ValueError`` immediately instead of failing deep inside a request (or
    being silently treated as a different mode).

    Examples:
        >>> _coerce_env_value("timeout", "120")
        120
        >>> _coerce_env_value("timeout", "1.5")
        1.5
        >>> _coerce_env_value("prefer", "local-only")
        'local-only'
        >>> _coerce_env_value("api_key", "att_123")
        'att_123'
        >>> _coerce_env_value("timeout", "120abc")
        Traceback (most recent call last):
        ...
        ValueError: Invalid ATTACHMENTS_TIMEOUT value '120abc': expected seconds \
as a number
        >>> _coerce_env_value("prefer", "bogus-mode")  # doctest: +ELLIPSIS
        Traceback (most recent call last):
        ...
        ValueError: Invalid ATTACHMENTS_PREFER value 'bogus-mode'. Valid: ...
    """
    if key == "timeout":
        try:
            return int(raw)
        except ValueError:
            try:
                return float(raw)
            except ValueError:
                raise ValueError(
                    f"Invalid ATTACHMENTS_TIMEOUT value {raw!r}: "
                    f"expected seconds as a number"
                ) from None
    if key == "prefer":
        if raw not in _VALID_PREFER:
            raise ValueError(
                f"Invalid ATTACHMENTS_PREFER value {raw!r}. Valid: {_VALID_PREFER}"
            )
    return raw


def configure(**kwargs) -> None:
    """Set global configuration options.

    Args:
        api_key: API key for attachments service. Enables service mode.
        prefer: Processing preference:
            - "local": Try local first, fall back to service if deps missing
            - "service": Try service first, fall back to local
            - "local-only": Only use local processing, fail if deps missing
            - "service-only": Only use service, fail if no API key
        service_url: Base URL for attachments service API.
        timeout: Timeout in seconds for service requests.

    Examples:
        >>> reset_config()  # Ensure clean state
        >>> configure(api_key="test_key", prefer="local")
        >>> get_config("api_key")
        'test_key'
        >>> get_config("prefer")
        'local'

        >>> configure(prefer="invalid")  # doctest: +IGNORE_EXCEPTION_DETAIL
        Traceback (most recent call last):
        ValueError: Invalid prefer value: invalid. Valid: ...

        >>> configure(bad_key="value")  # doctest: +IGNORE_EXCEPTION_DETAIL
        Traceback (most recent call last):
        ValueError: Invalid config keys: {'bad_key'}. Valid: ...

        >>> reset_config()  # Clean up
    """
    valid_keys = set(_config.keys())
    invalid_keys = set(kwargs.keys()) - valid_keys
    if invalid_keys:
        raise ValueError(f"Invalid config keys: {invalid_keys}. Valid: {valid_keys}")

    if "prefer" in kwargs:
        if kwargs["prefer"] not in _VALID_PREFER:
            raise ValueError(
                f"Invalid prefer value: {kwargs['prefer']}. Valid: {_VALID_PREFER}"
            )

    _config.update(kwargs)


def get_config(key: str, default=None):
    """Get a configuration value.

    Checks in order:
    1. Environment variable (ATTACHMENTS_{KEY}) — coerced/validated like
       configure() input (timeout becomes a number, prefer must be valid)
    2. Global config set via configure()
    3. Default value

    Args:
        key: Configuration key (e.g., "api_key", "prefer")
        default: Default value if not found

    Returns:
        Configuration value

    Raises:
        ValueError: If an environment variable carries an invalid value
            (e.g. ``ATTACHMENTS_TIMEOUT=abc`` or an unknown
            ``ATTACHMENTS_PREFER`` mode).

    Examples:
        >>> reset_config()
        >>> get_config("prefer")
        'local'
        >>> get_config("api_key") is None
        True
        >>> get_config("missing_key", "fallback")
        'fallback'
        >>> configure(timeout=120)
        >>> get_config("timeout")
        120
        >>> reset_config()
    """
    # Check environment variable first
    env_key = f"ATTACHMENTS_{key.upper()}"
    env_value = os.environ.get(env_key)
    if env_value is not None:
        return _coerce_env_value(key, env_value)

    # Then check global config
    return _config.get(key, default)


def get_api_key(override: str | None = None) -> str | None:
    """Get API key from override, env, or config.

    Examples:
        >>> reset_config()
        >>> get_api_key() is None
        True
        >>> get_api_key("override_key")
        'override_key'
        >>> configure(api_key="configured_key")
        >>> get_api_key()
        'configured_key'
        >>> get_api_key("override_key")  # Override takes priority
        'override_key'
        >>> reset_config()
    """
    if override is not None:
        return override
    return get_config("api_key")


def get_prefer(override: str | None = None) -> PreferMode:
    """Get prefer mode from override, env, or config.

    Examples:
        >>> reset_config()
        >>> get_prefer()
        'local'
        >>> get_prefer("service")
        'service'
        >>> configure(prefer="local-only")
        >>> get_prefer()
        'local-only'
        >>> reset_config()
    """
    if override is not None:
        return override  # type: ignore
    return get_config("prefer", "local")  # type: ignore


def get_service_url(override: str | None = None) -> str:
    """Get service URL from override, env, or config.

    Examples:
        >>> reset_config()
        >>> get_service_url()
        'https://api.attachments.dev/v1'
        >>> get_service_url("http://localhost:8000")
        'http://localhost:8000'
        >>> configure(service_url="https://custom.example.com")
        >>> get_service_url()
        'https://custom.example.com'
        >>> reset_config()
    """
    if override is not None:
        return override
    return get_config("service_url", "https://api.attachments.dev/v1")


def reset_config() -> None:
    """Reset configuration to defaults. Useful for testing.

    Examples:
        >>> configure(api_key="test", prefer="service", timeout=999)
        >>> get_config("api_key")
        'test'
        >>> reset_config()
        >>> get_config("api_key") is None
        True
        >>> get_config("prefer")
        'local'
        >>> get_config("timeout")
        60
    """
    global _config
    _config = {
        "api_key": None,
        "prefer": "local",
        "service_url": "https://api.attachments.dev/v1",
        "timeout": 60,
    }
