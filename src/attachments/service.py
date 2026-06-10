"""Service mode for attachments - process files via remote API.

When local dependencies aren't available or when explicitly configured,
attachments can process files via a remote service.

Example::

    from attachments import configure, att

    configure(api_key="att_...")
    att("file.pdf")  # Processed remotely if local deps missing
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

from .config import get_api_key, get_config, service_configured

log = logging.getLogger("attachments.service")


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


def _auth_headers(key: str | None) -> dict[str, str]:
    """Bearer header when a key is set; empty for keyless servers.

    Examples:
        >>> _auth_headers("k")
        {'Authorization': 'Bearer k'}
        >>> _auth_headers(None)
        {}
    """
    return {"Authorization": f"Bearer {key}"} if key else {}


def process_via_service(
    data: bytes,
    *,
    filename: str = "file",
    api_key: str | None = None,
    options: dict[str, Any] | None = None,
) -> dict:
    """Process a file via the attachments service.

    Options travel as a plain dict (never ``**kwargs``) so option keys like
    ``filename`` or ``api_key`` can never collide with this function's own
    parameters.

    Args:
        data: File bytes to process
        filename: Original filename (used for format detection)
        api_key: API key (uses configured key if not provided)
        options: Processing options passed to the service

    Returns:
        Artifact dict with text, images, audio, video, meta

    Raises:
        ServiceError: If the service returns an error
        ImportError: If httpx is not installed
    """
    httpx = _get_client()

    key = get_api_key(api_key)
    if not service_configured(api_key):
        raise ServiceError(
            "Service not configured. Set configure(api_key=...) for the hosted "
            "service, or configure(service_url=...) for a keyless/self-hosted "
            "server."
        )

    service_url = get_config("service_url")
    timeout = get_config("timeout", 60)

    # Prepare request. Options travel RAW (the server resolves them against
    # its processor schemas). Every value is JSON-encoded so its parsed type
    # survives the multipart form encoding: the server decodes each field
    # with json.loads, and the DSL guarantee that a quoted value stays a
    # string ('3' vs 3, 'null' vs null) must hold over the wire exactly as
    # it does locally (spec/dsl-grammar.md, normalization rule 1).
    files = {"file": (filename, data)}
    form_data = {
        k: json.dumps(v, default=str)
        for k, v in (options or {}).items()
        if v is not None
    }

    log.debug(
        "POST %s/process  filename=%s  size=%d",
        service_url,
        filename,
        len(data),
    )
    try:
        response = httpx.post(
            f"{service_url}/process",
            headers=_auth_headers(key),
            files=files,
            data=form_data,
            timeout=timeout,
        )
    except httpx.TimeoutException as e:
        raise ServiceError(f"Service request timed out after {timeout}s") from e
    except httpx.RequestError as e:
        raise ServiceError(f"Service request failed: {e}") from e

    log.debug("service responded %d", response.status_code)
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
    if not service_configured(api_key):
        raise ServiceError(
            "Service not configured. Set configure(api_key=...) or "
            "configure(service_url=...)."
        )

    service_url = get_config("service_url")
    timeout = get_config("timeout", 60)

    try:
        response = httpx.post(
            f"{service_url}/unpack",
            headers=_auth_headers(key),
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


def unpack_bytes_via_service(
    data: bytes,
    *,
    filename: str,
    api_key: str | None = None,
) -> list[tuple[str, bytes]]:
    """Unpack archive bytes via the attachments service.

    Posts the raw archive (zip/tar) as multipart form data to ``/unpack``;
    the server explodes it with its bomb-guarded archive machinery and
    returns the member files. Non-archive bytes are rejected by the server
    with HTTP 400 (raised here as :class:`ServiceError`).

    Args:
        data: Raw archive bytes (zip or tar family)
        filename: Archive filename (used as the virtual path prefix)
        api_key: API key (uses configured key if not provided)

    Returns:
        List of (filename, bytes) tuples

    Raises:
        ServiceError: If the service returns an error
        ImportError: If httpx is not installed

    Example::

        from attachments.service import unpack_bytes_via_service

        files = unpack_bytes_via_service(
            open("bundle.zip", "rb").read(), filename="bundle.zip"
        )
        # [("bundle.zip/a.txt", b"..."), ("bundle.zip/b.csv", b"...")]
    """
    httpx = _get_client()

    key = get_api_key(api_key)
    if not service_configured(api_key):
        raise ServiceError(
            "Service not configured. Set configure(api_key=...) or "
            "configure(service_url=...)."
        )

    service_url = get_config("service_url")
    timeout = get_config("timeout", 60)

    log.debug(
        "POST %s/unpack  filename=%s  size=%d",
        service_url,
        filename,
        len(data),
    )
    try:
        response = httpx.post(
            f"{service_url}/unpack",
            headers=_auth_headers(key),
            files={"file": (filename, data)},
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
        files.append((item["filename"], base64.b64decode(item["data_b64"])))
    return files


def check_service_health(api_key: str | None = None) -> dict:
    """Check if the service is available and API key is valid.

    Returns:
        Dict with service status info

    Example::

        check_service_health()
        # Returns: {'status': 'ok', 'formats': ['pdf', 'xlsx', ...], ...}
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
