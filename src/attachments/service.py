"""Service mode for attachments - process files via remote API.

When local dependencies aren't available or when explicitly configured,
attachments can process files via a remote service.

Example:
    >>> from attachments import configure, att
    >>> configure(api_key="att_...")
    >>> att("file.pdf")  # Processed remotely if local deps missing
"""

from __future__ import annotations

import base64
from typing import Any

from .config import get_api_key, get_config


class ServiceError(Exception):
    """Error from attachments service."""

    def __init__(self, message: str, status_code: int | None = None):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _get_client():
    """Get httpx client, raising helpful error if not installed."""
    try:
        import httpx

        return httpx
    except ImportError as e:
        raise ImportError(
            "Service mode requires httpx. "
            "Install with: pip install attachments[service]"
        ) from e


def process_via_service(
    data: bytes,
    *,
    filename: str = "file",
    api_key: str | None = None,
    **options: Any,
) -> dict:
    """Process a file via the attachments service.

    Args:
        data: File bytes to process
        filename: Original filename (used for format detection)
        api_key: API key (uses configured key if not provided)
        **options: Processing options passed to the service

    Returns:
        Artifact dict with text, images, audio, video, flags

    Raises:
        ServiceError: If the service returns an error
        ImportError: If httpx is not installed
    """
    httpx = _get_client()

    key = get_api_key(api_key)
    if not key:
        raise ServiceError(
            "No API key configured. "
            "Set via configure(api_key=...) or ATTACHMENTS_API_KEY env var"
        )

    service_url = get_config("service_url")
    timeout = get_config("timeout", 60)

    # Prepare request
    files = {"file": (filename, data)}
    form_data = {k: str(v) for k, v in options.items() if v is not None}

    try:
        response = httpx.post(
            f"{service_url}/process",
            headers={"Authorization": f"Bearer {key}"},
            files=files,
            data=form_data,
            timeout=timeout,
        )
    except httpx.TimeoutException as e:
        raise ServiceError(f"Service request timed out after {timeout}s") from e
    except httpx.RequestError as e:
        raise ServiceError(f"Service request failed: {e}") from e

    if response.status_code == 401:
        raise ServiceError("Invalid API key", status_code=401)
    elif response.status_code == 402:
        raise ServiceError("API quota exceeded", status_code=402)
    elif response.status_code == 413:
        raise ServiceError("File too large for service", status_code=413)
    elif response.status_code >= 400:
        try:
            error_detail = response.json().get("error", response.text)
        except Exception:
            error_detail = response.text
        raise ServiceError(
            f"Service error: {error_detail}", status_code=response.status_code
        )

    # Parse response
    result = response.json()

    # Decode base64 images if present
    if "images" in result:
        for img in result["images"]:
            if "bytes_b64" in img:
                img["bytes"] = base64.b64decode(img.pop("bytes_b64"))

    return result


def unpack_via_service(
    url: str,
    *,
    api_key: str | None = None,
    **options: Any,
) -> list[tuple[str, bytes]]:
    """Unpack a URL via the attachments service.

    The service fetches and unpacks the URL, returning file list.
    Useful for sources that require special auth (S3, GDrive, etc.)

    Args:
        url: URL to unpack (can be s3://, gdrive://, etc.)
        api_key: API key
        **options: Unpack options

    Returns:
        List of (filename, bytes) tuples

    Raises:
        ServiceError: If the service returns an error
    """
    httpx = _get_client()

    key = get_api_key(api_key)
    if not key:
        raise ServiceError("No API key configured")

    service_url = get_config("service_url")
    timeout = get_config("timeout", 60)

    try:
        response = httpx.post(
            f"{service_url}/unpack",
            headers={"Authorization": f"Bearer {key}"},
            json={"url": url, **options},
            timeout=timeout,
        )
    except httpx.TimeoutException as e:
        raise ServiceError(f"Service request timed out after {timeout}s") from e
    except httpx.RequestError as e:
        raise ServiceError(f"Service request failed: {e}") from e

    if response.status_code >= 400:
        try:
            error_detail = response.json().get("error", response.text)
        except Exception:
            error_detail = response.text
        raise ServiceError(
            f"Service error: {error_detail}", status_code=response.status_code
        )

    # Parse response - files are base64 encoded
    result = response.json()
    files = []
    for item in result.get("files", []):
        filename = item["filename"]
        data = base64.b64decode(item["data_b64"])
        files.append((filename, data))

    return files


def check_service_health(api_key: str | None = None) -> dict:
    """Check if the service is available and API key is valid.

    Returns:
        Dict with service status info

    Example:
        >>> check_service_health()
        {'status': 'ok', 'formats': ['pdf', 'xlsx', ...], 'sources': ['s3', ...]}
    """
    httpx = _get_client()

    key = get_api_key(api_key)
    service_url = get_config("service_url")

    headers = {}
    if key:
        headers["Authorization"] = f"Bearer {key}"

    try:
        response = httpx.get(
            f"{service_url}/health",
            headers=headers,
            timeout=10,
        )
        return response.json()
    except Exception as e:
        return {"status": "error", "error": str(e)}
