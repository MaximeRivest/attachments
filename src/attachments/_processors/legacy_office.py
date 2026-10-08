"""Old Office and OpenDocument files, converted by LibreOffice.

``.doc`` and ``.odt`` become ``.docx``, ``.ppt`` and ``.odp`` become
``.pptx``, ``.ods`` becomes ``.xlsx``; the converted file is then read by
the regular processor, so the text, tables, slide segments, images and
every option are exactly those of the modern format (``att("old.doc",
images=True)`` works like ``.docx``). ``.xls`` has its own reader (xlrd).

LibreOffice is a program, not a Python package: without it these files
come back with a ``missing-dependency`` error that says how to install it
(which also lets a configured service do the work instead).

Each conversion runs in a fresh temporary folder with its own LibreOffice
profile — two conversions at once would otherwise fight over the user's
profile lock — and is killed after ``ATTACHMENTS_LIBREOFFICE_TIMEOUT``
seconds (default 120). Starting LibreOffice costs about 2 seconds per file.
LibreOffice does not run document macros when converting.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .._options import get_options, register_options
from ..deps import find_libreoffice
from ..types import ERROR_PARSE, error_artifact, missing_dep_artifact
from . import processors, register_processor

log = logging.getLogger("attachments.processors.legacy_office")

#: Old/open format -> modern format read by an existing processor.
CONVERSIONS = {
    ".doc": ".docx",
    ".odt": ".docx",
    ".ppt": ".pptx",
    ".odp": ".pptx",
    ".ods": ".xlsx",
}

TIMEOUT_ENV = "ATTACHMENTS_LIBREOFFICE_TIMEOUT"
DEFAULT_TIMEOUT = 120.0


class ConversionError(RuntimeError):
    pass


def _timeout() -> float:
    try:
        return max(1.0, float(os.environ.get(TIMEOUT_ENV, DEFAULT_TIMEOUT)))
    except ValueError:
        return DEFAULT_TIMEOUT


def convert(data: bytes, source_ext: str, target_ext: str, soffice: str) -> bytes:
    """Convert *data* with LibreOffice; returns the converted file's bytes."""
    with tempfile.TemporaryDirectory(prefix="attachments-lo-") as tmp:
        work = Path(tmp)
        # A fixed, plain name: the user's file name never reaches a command line.
        src = work / f"input{source_ext}"
        src.write_bytes(data)
        out_dir = work / "out"
        command = [
            soffice,
            f"-env:UserInstallation={(work / 'profile').as_uri()}",
            "--headless",
            "--norestore",
            "--nolockcheck",
            "--nodefault",
            "--nologo",
            "--convert-to",
            target_ext.lstrip("."),
            "--outdir",
            str(out_dir),
            str(src),
        ]
        popen: dict[str, Any] = {}
        if os.name == "posix":
            popen["start_new_session"] = True  # kill helpers with the group
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            env={**os.environ, "HOME": tmp},
            **popen,
        )
        try:
            _, stderr = process.communicate(timeout=_timeout())
        except subprocess.TimeoutExpired:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            process.communicate()
            raise ConversionError(
                f"LibreOffice did not finish within {_timeout():.0f} s "
                f"(raise {TIMEOUT_ENV})"
            ) from None
        result = out_dir / f"input{target_ext}"
        if not result.is_file():
            detail = stderr.decode("utf-8", "replace").strip().splitlines()
            tail = detail[-1] if detail else f"exit code {process.returncode}"
            raise ConversionError(f"LibreOffice could not convert the file: {tail}")
        return result.read_bytes()


def legacy_office_processor(
    data: bytes, *, filename: str | None = None, **options: Any
) -> dict[str, Any]:
    """Read an old Office / OpenDocument file through its modern format."""
    source = filename or "document"
    ext = os.path.splitext(source)[1].lower()
    target = CONVERSIONS.get(ext)
    if target is None:  # registered under an unexpected key
        return error_artifact(source, ERROR_PARSE, f"no conversion for {ext!r}")
    soffice = find_libreoffice()
    if soffice is None:
        return missing_dep_artifact(source, "libreoffice")
    try:
        converted = convert(data, ext, target, soffice)
    except (ConversionError, OSError) as e:
        log.warning("LibreOffice conversion failed for %s: %s", source, e)
        return error_artifact(source, ERROR_PARSE, f"Failed to read {ext} file: {e}")
    artifact = processors[target](converted, filename=source, **options)
    extra = artifact.setdefault("meta", {}).setdefault("extra", {})
    extra["converted_from"] = ext
    extra["converter"] = "libreoffice"
    return artifact


for _ext, _target in CONVERSIONS.items():
    register_processor(_ext, legacy_office_processor)
    # The same options as the modern format the file becomes.
    register_options(_ext, get_options(_target))
