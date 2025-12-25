"""Global configuration for attachments library.

Configuration can be set via:
1. Environment variables (ATTACHMENTS_API_KEY, ATTACHMENTS_SERVICE_URL, etc.)
2. Global configure() call
3. Per-call options (highest priority)

Example:
    >>> import attachments
    >>> attachments.configure(api_key="att_...", prefer="local")
    >>> attachments.att("file.pdf")  # Uses local if deps available, else service
"""

from __future__ import annotations

import os
from typing import Literal

# Valid values for the "prefer" setting
PreferMode = Literal["local", "service", "local-only", "service-only"]

# Default configuration
_config: dict = {
    "api_key": None,
    "prefer": "local",  # local | service | local-only | service-only
    "service_url": "https://api.attachments.dev/v1",
    "timeout": 60,  # seconds for service requests
}


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

    Example:
        >>> configure(api_key="att_...", prefer="local")
    """
    valid_keys = set(_config.keys())
    invalid_keys = set(kwargs.keys()) - valid_keys
    if invalid_keys:
        raise ValueError(f"Invalid config keys: {invalid_keys}. Valid: {valid_keys}")

    if "prefer" in kwargs:
        valid_prefer = ("local", "service", "local-only", "service-only")
        if kwargs["prefer"] not in valid_prefer:
            raise ValueError(
                f"Invalid prefer value: {kwargs['prefer']}. Valid: {valid_prefer}"
            )

    _config.update(kwargs)


def get_config(key: str, default=None):
    """Get a configuration value.

    Checks in order:
    1. Environment variable (ATTACHMENTS_{KEY})
    2. Global config set via configure()
    3. Default value

    Args:
        key: Configuration key (e.g., "api_key", "prefer")
        default: Default value if not found

    Returns:
        Configuration value
    """
    # Check environment variable first
    env_key = f"ATTACHMENTS_{key.upper()}"
    env_value = os.environ.get(env_key)
    if env_value is not None:
        return env_value

    # Then check global config
    return _config.get(key, default)


def get_api_key(override: str | None = None) -> str | None:
    """Get API key from override, env, or config."""
    if override is not None:
        return override
    return get_config("api_key")


def get_prefer(override: str | None = None) -> PreferMode:
    """Get prefer mode from override, env, or config."""
    if override is not None:
        return override  # type: ignore
    return get_config("prefer", "local")  # type: ignore


def get_service_url(override: str | None = None) -> str:
    """Get service URL from override, env, or config."""
    if override is not None:
        return override
    return get_config("service_url", "https://api.attachments.dev/v1")


def reset_config() -> None:
    """Reset configuration to defaults. Useful for testing."""
    global _config
    _config = {
        "api_key": None,
        "prefer": "local",
        "service_url": "https://api.attachments.dev/v1",
        "timeout": 60,
    }
