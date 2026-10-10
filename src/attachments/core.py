"""Core processing pipeline for attachments.

This module provides the main `att()` function that orchestrates:
1. Unpacking input sources into (filename, bytes) pairs
2. Routing each file to the appropriate processor
3. Processing with local deps or service fallback
4. Normalizing output to consistent artifact format
"""

from __future__ import annotations

import difflib
import logging
import os
from collections.abc import Iterable, Mapping
from typing import Any

from ._artifacts import Artifacts
from ._options import (
    Option,
    get_options,
    resolve_options,
    source_option_schemas,
    warn_option,
)
from ._processors import STANDARD, NamedProcessor, get_named, processors
from ._sources import (
    InvalidSourceOption,
    extra_unpack_handlers,
    resolve,
)
from ._sources.archives import RAW_ARCHIVE_SUFFIXES
from ._sources.local import TREE_OPTIONS
from ._watermark import WATERMARK, apply_watermark
from .config import get_api_key, get_prefer, service_configured
from .dsl import parse_dsl
from .types import (
    ERROR_INVALID_OPTION,
    ERROR_MISSING_DEPENDENCY,
    ERROR_PROCESSING,
    ERROR_SERVICE,
    ERROR_UNPACK,
    Processor,
    error_artifact,
    is_missing_dependency,
    make_artifact,
    normalize_artifact,
)
from .utils import detect_extension, is_text_bytes

log = logging.getLogger("attachments.core")


def _route_processor(filename: str, data: bytes) -> tuple[Processor | None, str]:
    """Find the appropriate processor (and its registry key) for a file.

    Routing order:
    1. Filename extension lookup in the processor registry.
    2. Magic-byte content sniffing (``utils.detect_extension``) — only
       routes when the sniffed extension has a registered processor.
    3. Text heuristic fallback (``__text__``).

    Returns ``(None, ext)`` if no processor is found (which will trigger
    service fallback). The key is used to look up the declared option
    schema for this processor. Routing is pure: nothing is recorded in
    ``meta`` here.
    """
    ext = os.path.splitext(filename)[1].lower()
    proc = processors.get(ext)
    if proc is not None:
        return proc, ext
    sniffed = detect_extension(data)
    if sniffed is not None:
        proc = processors.get(sniffed)
        if proc is not None:
            return proc, sniffed
    if is_text_bytes(data):
        proc = processors.get("__text__")
        if proc is not None:
            return proc, "__text__"
    return None, ext


def _empty_artifact(source: str, note: str) -> dict:
    """Create an empty artifact with an informational note (not an error).

    Examples:
        >>> artifact = _empty_artifact("test.bin", "no processor available")
        >>> artifact["meta"]["note"]
        'no processor available'
        >>> artifact["text"]
        ''
    """
    return make_artifact(meta={"source": source, "note": note})


def _artifact_from_exception(source: str, exc: Exception, context: str) -> dict:
    """Convert a processor exception into a typed error artifact.

    ImportError means a missing optional dependency; anything else is a
    generic processing error. Missing-dependency messages always include
    the pip install remedy (IR contract).

    Examples:
        >>> a = _artifact_from_exception("f.xyz", ImportError("no mod"), "local")
        >>> a["meta"]["error"]["code"]
        'missing-dependency'
        >>> "pip install" in a["meta"]["error"]["message"]
        True
        >>> a = _artifact_from_exception("f.xyz", ValueError("bad"), "local")
        >>> a["meta"]["error"]["code"]
        'processing-error'
        >>> a["meta"]["error"]["message"]
        'local processing failed: bad'
    """
    if isinstance(exc, ImportError):
        # exc.name is set when the import machinery raised the error;
        # fall back to the bundle extra covering all built-in processors.
        missing = getattr(exc, "name", None)
        remedy = (
            f"pip install {missing}"
            if missing
            else "pip install attachments[all-local]"
        )
        return error_artifact(
            source,
            ERROR_MISSING_DEPENDENCY,
            f"{context} processing failed: {exc}. "
            f"Missing optional dependency — install with: {remedy}",
        )
    return error_artifact(
        source, ERROR_PROCESSING, f"{context} processing failed: {exc}"
    )


def _attach_warnings(artifact: dict, warnings: list[str]) -> dict:
    """Append option-resolution warnings to ``meta.warnings``.

    The list is created only when there is something to report (IR
    contract: optional meta keys are absent, never empty placeholders).

    Examples:
        >>> a = make_artifact(text="ok")
        >>> _attach_warnings(a, [])["meta"]
        {}
        >>> _attach_warnings(a, ["Unknown option 'x' for .pdf"])["meta"]["warnings"]
        ["Unknown option 'x' for .pdf"]
    """
    if warnings:
        meta = artifact.setdefault("meta", {})
        meta.setdefault("warnings", []).extend(warnings)
    return artifact


def _option_context(filename: str, proc_key: str) -> str:
    """Human-readable owner name for option warnings.

    Examples:
        >>> _option_context("report.pdf", ".pdf")
        '.pdf'
        >>> _option_context("LICENSE", "__text__")
        'text'
    """
    ext = os.path.splitext(filename)[1].lower()
    if ext:
        return ext
    return "text" if proc_key == "__text__" else proc_key


#: The option that picks a named processor (handled here, not by processors).
PROCESSOR_KEY = "processor"

#: Options that make pictures on request, in the order a hint names them.
_PICTURE_OPTIONS = ("images", "screenshot", "outputs")

#: Processor kwargs a ``pages`` option resolves to (``resolve_options``).
_PAGE_PARAMS = ("page_start", "page_end", "page_selection")


def _choose_named(
    table: dict[str, NamedProcessor],
    data: bytes,
    filename: str,
    requested: Any,
    context: str,
    warnings: list[str],
) -> NamedProcessor | None:
    """The named processor for this file, or ``None`` for the standard one.

    ``[processor: NAME]`` chooses by name (``default``: the standard one).
    Otherwise, or when NAME is unknown (a warning, as for any wrong
    option), the most recently registered processor whose ``detect`` says
    yes. A ``detect`` that raises counts as no (and is logged).
    """
    if requested is not None:
        wanted = str(requested).strip().lower()
        if wanted == STANDARD:
            return None
        if wanted in table:
            return table[wanted]
        names = [STANDARD, *table]
        message = f"Unknown processor '{requested}' for {context}"
        close = difflib.get_close_matches(wanted, names, n=1)
        if close:
            message += f" — did you mean '{close[0]}'?"
        message += f" (available: {', '.join(names)})"
        warnings.append(message)
        warn_option(message)
    for entry in reversed(table.values()):
        if entry.detect is None:
            continue
        try:
            if entry.detect(data, filename):
                return entry
        except Exception as e:
            log.warning(
                "detect of processor %r failed on %s: %s", entry.name, filename, e
            )
    return None


def _option_names(options: Iterable[Option]) -> set[str]:
    """Every spelling that reaches *options*: names, aliases, params."""
    names: set[str] = set()
    for option in options:
        names.update((option.name, *option.aliases))
        if option.param:
            names.add(option.param)
    return names


def _option_params(options: Iterable[Option]) -> set[str]:
    """The processor kwargs *options* resolve to."""
    params: set[str] = set()
    for option in options:
        if option.type == "pages":
            params.update(_PAGE_PARAMS)
        else:
            params.add(option.param or option.name)
    return params


def _pictures_hint(schema: Iterable[Option]) -> str | None:
    """How to ask this format for pictures (``"images: true"``), if it can.

    Examples:
        >>> from attachments._options import get_options
        >>> _pictures_hint(get_options(".pdf")), _pictures_hint(get_options(".png"))
        ('images: true', None)
    """
    for name in _PICTURE_OPTIONS:
        for option in schema:
            if option.name == name:
                return option.example or f"{name}: true"
    return None


def _process_single(
    filename: str,
    data: bytes,
    *,
    options: dict[str, Any] | None = None,
    api_key: str | None = None,
    prefer: str | None = None,
    url: str | None = None,
) -> dict:
    """Process a single file with local/service fallback logic.

    Local processor calls receive options resolved against the processor's
    declared schema (``attachments._options``); resolution warnings are
    attached to the resulting artifact's ``meta.warnings``. Service calls
    receive the RAW options — the service resolves them server-side.

    Two options are core's, not the processor's:

    - ``processor`` picks a named processor (``_choose_named``); without
      it, a named processor whose ``detect`` matches is used.
    - ``watermark`` (declared by the formats that make pictures) is taken
      out before the processor runs and applied to its result here, after
      local or service processing alike — never sent to the service.

    Options travel as a plain dict (never ``**kwargs``) so that option keys
    like ``filename`` or ``prefer`` can never collide with this function's
    own parameters — unknown keys must become ``meta.warnings``, not
    ``TypeError``.

    Args:
        filename: Name of the file (used for extension detection)
        data: File bytes
        options: Raw options (merged DSL + explicit kwargs)
        api_key: Optional API key for service mode
        prefer: Processing preference (local/service/local-only/service-only)
        url: Address the bytes were downloaded from, if any. When the
            matched processor declares a ``url`` option and the caller did
            not set one, it receives this address — so a web page resolves
            its relative links and loads in a browser from where it really
            lives. Sent to the service the same way.

    Returns:
        Artifact dict
    """
    options = dict(options or {})
    key = get_api_key(api_key)
    svc = service_configured(api_key)
    mode = get_prefer(prefer)

    proc, proc_key = _route_processor(filename, data)
    context = _option_context(filename, proc_key)
    ext = os.path.splitext(filename)[1].lower()
    table = (get_named(ext) if ext else {}) or get_named(proc_key)
    requested = options.pop(PROCESSOR_KEY, None)
    choice_warnings: list[str] = []
    named = None
    if table:
        named = _choose_named(
            table, data, filename, requested, context, choice_warnings
        )
    elif requested is not None and str(requested).strip().lower() != STANDARD:
        if proc is not None:
            message = (
                f"Unknown processor '{requested}' for {context} — "
                f"only the standard one ({STANDARD}) reads it"
            )
            choice_warnings.append(message)
            warn_option(message)
    log.debug(
        "routing %s  mode=%s  processor=%s  named=%s",
        filename,
        mode,
        proc,
        named.name if named else None,
    )

    # Resolve raw options against the declared schema: the standard
    # processor's, plus a named processor's own options (which win).
    standard_schema = get_options(proc_key) if proc is not None else ()
    schema = standard_schema
    if named is not None:
        own = {o.name for o in named.options}
        standard_schema = tuple(o for o in standard_schema if o.name not in own)
        schema = (*standard_schema, *named.options)
    # Files with no processor get no option warnings.
    resolved: dict[str, Any] = {}
    warnings: list[str] = []
    if proc is not None or named is not None:
        resolved, warnings = resolve_options(schema, options, context=context)
        if url and "url" not in resolved and any(o.name == "url" for o in schema):
            resolved["url"] = url
            options = {**options, "url": url}  # the service gets it too

    watermark = None
    if WATERMARK in schema:
        watermark = resolved.pop(WATERMARK.name, None)
        options = {k: v for k, v in options.items() if k != WATERMARK.name}

    if named is not None:
        result = _run_named(
            named,
            filename,
            data,
            resolved=resolved,
            warnings=warnings,
            standard_schema=standard_schema,
            raw=options,
            standard=lambda d, kwargs, warns, raw: _run_standard(
                filename, d, proc, kwargs, warns, raw, key, svc, mode
            ),
        )
    else:
        result = _run_standard(
            filename, data, proc, resolved, warnings, options, key, svc, mode
        )

    if choice_warnings:
        meta = result.setdefault("meta", {})
        meta["warnings"] = [*choice_warnings, *(meta.get("warnings") or [])]
    if watermark is not None:
        apply_watermark(
            result, watermark, source=url or filename, hint=_pictures_hint(schema)
        )
    return result


def _run_named(
    named: NamedProcessor,
    filename: str,
    data: bytes,
    *,
    resolved: dict[str, Any],
    warnings: list[str],
    standard_schema: tuple[Option, ...],
    raw: dict[str, Any],
    standard: Any,
) -> dict:
    """Run a named processor, giving it the standard processing as ``base``.

    ``base()`` runs the standard processor with the options of this call
    that belong to it (local first, service fallback as usual);
    ``base(data, **options)`` with other bytes and/or more options, in
    ``att()``'s vocabulary (``pages="1-2"``, ``images=True``). Its result
    is never sent through the service: the service does not know this
    processor.
    """
    standard_names = _option_names(standard_schema)
    standard_params = _option_params(standard_schema)
    standard_raw = {k: v for k, v in raw.items() if k in standard_names}
    standard_kwargs = {k: v for k, v in resolved.items() if k in standard_params}

    def base(other: bytes | None = None, /, **more: Any) -> dict:
        kwargs = dict(standard_kwargs)
        more_warnings: list[str] = []
        if more:
            more_kwargs, more_warnings = resolve_options(
                standard_schema, more, context=f"base of processor '{named.name}'"
            )
            if any(k in more_kwargs for k in _PAGE_PARAMS):
                for k in _PAGE_PARAMS:
                    kwargs.pop(k, None)
            kwargs.update(more_kwargs)
        return standard(
            data if other is None else other,
            kwargs,
            more_warnings,
            {**standard_raw, **more},
        )

    kwargs = dict(resolved)
    if named.wants_base:
        kwargs["base"] = base
    try:
        result = named.func(data, filename=filename, **kwargs)
    except Exception as e:
        log.error("processor %r failed on %s: %s", named.name, filename, e)
        result = _artifact_from_exception(filename, e, f"processor '{named.name}'")
    if not isinstance(result, dict):
        result = error_artifact(
            filename,
            ERROR_PROCESSING,
            f"processor '{named.name}' returned {type(result).__name__}, "
            "not an artifact (use attachments.make_artifact)",
        )
    _attach_warnings(result, warnings)
    meta = result.setdefault("meta", {})
    meta.setdefault("extra", {})["processor"] = named.name
    return result


def _run_standard(
    filename: str,
    data: bytes,
    proc: Processor | None,
    resolved: dict[str, Any],
    warnings: list[str],
    options: dict[str, Any],
    key: str | None,
    svc: bool,
    mode: str,
) -> dict:
    """The standard processor with local/service fallback (per *mode*).

    *resolved* and *warnings* are for the local processor; *options* (raw)
    for the service.
    """

    def _run_local() -> dict:
        result = proc(data, filename=filename, **resolved)
        return _attach_warnings(result, warnings)

    # Determine processing strategy based on mode
    if mode == "service-only":
        # Only use service
        if not svc:
            log.warning("service-only mode but no service configured for %s", filename)
            return error_artifact(
                filename,
                ERROR_SERVICE,
                "service-only mode but no service configured "
                "(configure(api_key=...) or configure(service_url=...))",
            )
        return _process_via_service(filename, data, key, options=options)

    elif mode == "local-only":
        # Only use local, fail if no processor or deps missing
        if proc is None:
            log.info("no local processor for %s", filename)
            return _empty_artifact(filename, "no local processor available")
        try:
            return _run_local()
        except Exception as e:
            log.error("local processing failed for %s: %s", filename, e)
            return _artifact_from_exception(filename, e, "local")

    elif mode == "service":
        # Try service first, fall back to local
        if svc:
            try:
                result = _process_via_service(filename, data, key, options=options)
                if not result.get("meta", {}).get("error"):
                    return result
            except Exception:
                log.debug("service failed for %s, falling back to local", filename)

        # Fall back to local
        if proc is None:
            return _empty_artifact(filename, "no processor available")
        try:
            return _run_local()
        except Exception as e:
            log.error("processing failed for %s: %s", filename, e)
            return _artifact_from_exception(filename, e, "local")

    else:  # mode == "local" (default)
        # Try local first, fall back to service if deps missing
        if proc is not None:
            try:
                result = _run_local()
                # Typed check: only a missing-dependency result (plus an API
                # key) may trigger service fallback. Other errors are final.
                if not svc or not is_missing_dependency(result):
                    return result
                log.info("local dep error for %s, falling back to service", filename)
            except Exception as e:
                if not key:
                    return _artifact_from_exception(filename, e, "local")
                log.info(
                    "local exception for %s, falling back to service: %s",
                    filename,
                    e,
                )

        # No local processor or local failed - try service if configured
        if svc:
            try:
                return _process_via_service(filename, data, key, options=options)
            except Exception as e:
                log.error("service processing failed for %s: %s", filename, e)
                return error_artifact(
                    filename, ERROR_SERVICE, f"service processing failed: {e}"
                )

        # No processor and no service
        if proc is None:
            return _empty_artifact(filename, "no processor available")

        # Should not reach here, but just in case
        return error_artifact(filename, ERROR_PROCESSING, "processing failed")


def _process_via_service(
    filename: str,
    data: bytes,
    api_key: str,
    *,
    options: dict[str, Any] | None = None,
) -> dict:
    """Process via the attachments service."""
    from .service import ServiceError, process_via_service

    log.debug("sending %s (%d bytes) to service", filename, len(data))
    try:
        result = process_via_service(
            data, filename=filename, api_key=api_key, options=options
        )
        result.setdefault("meta", {})
        result["meta"]["via"] = "service"
        return result
    except ServiceError as e:
        log.warning("service error for %s: %s", filename, e.message)
        return error_artifact(filename, ERROR_SERVICE, f"service error: {e.message}")


def _source_schema_for(input: str) -> tuple | None:
    """Return the declared source option schema matching *input*, if any.

    GitHub repo-root https URLs share the ``github://`` schema. Local
    paths (no scheme) and URLs of archives get the folder options
    (``file://``): an archive is read like a folder.

    Examples:
        >>> [o.name for o in _source_schema_for("docs/")][:2]
        ['files', 'tree']
        >>> _source_schema_for("https://example.com/page") is None
        True
        >>> "max_files" in [o.name for o in _source_schema_for("https://x.org/a.zip")]
        True
    """
    if input.startswith("https://github.com/") and input.count("/") <= 4:
        return source_option_schemas.get("github://")
    for prefix, schema in source_option_schemas.items():
        if input.startswith(prefix):
            return schema
    if any(input.startswith(prefix) for prefix in extra_unpack_handlers):
        return None
    if input.startswith(("http://", "https://")):
        path = input.split("?", 1)[0].split("#", 1)[0].lower()
        if path.endswith(RAW_ARCHIVE_SUFFIXES):
            return source_option_schemas.get("file://")
        return None
    return source_option_schemas.get("file://")


_TREE_NAMES = {o.name for o in TREE_OPTIONS}


def _take_tree_options(input: str, options: dict) -> dict[str, Any]:
    """Pop the folder options that apply to *input* from *options*.

    They go to ``resolve()`` as plain values instead of the per-file
    processors (which would warn "Unknown option"). Raw values: typed by
    ``resolve_options`` against ``TREE_OPTIONS`` afterwards.

    Examples:
        >>> opts = {"max_files": 3, "pages": "1-2"}
        >>> _take_tree_options("docs/", opts), opts
        ({'max_files': 3}, {'pages': '1-2'})
        >>> opts = {"max_files": 3}
        >>> _take_tree_options("https://example.com/page", opts), opts
        ({}, {'max_files': 3})
    """
    schema = _source_schema_for(input)
    if not schema:
        return {}
    taken: dict[str, Any] = {}
    for option in schema:
        if option.name not in _TREE_NAMES:
            continue
        for key in [k for k in options if k in {option.name, *option.aliases}]:
            taken[key] = options.pop(key)
    return taken


def _apply_source_options(input: str, options: dict) -> str:
    """Apply source-specific options to the input path.

    Consumes options declared in ``source_option_schemas`` (matching
    canonical names, aliases, and param names) and re-encodes every
    consumed option as a query parameter on the input string, where the
    matching source handler parses it — e.g. ``ref``/``branch``/``tag``
    become ``?ref=...``, which ``_sources.github`` reads. This is the
    generic delivery channel: handler signatures stay
    ``(url) -> [(name, bytes)]``, so a custom source's declared options
    (say ``region`` on ``s3://``) arrive as ``s3://...?region=...``.
    Falsy values are skipped. Unrecognized keys are left untouched WITHOUT
    warnings: they may be processor options resolved later, per file.

    Examples:
        >>> opts = {"ref": "main", "other": "value"}
        >>> _apply_source_options("github://org/repo", opts)
        'github://org/repo?ref=main'
        >>> opts  # ref is consumed
        {'other': 'value'}

        >>> opts = {"branch": "dev"}  # alias for ref
        >>> _apply_source_options("github://org/repo", opts)
        'github://org/repo?ref=dev'

        >>> _apply_source_options("local/file.txt", {"ref": "ignored"})
        'local/file.txt'
    """
    schema = _source_schema_for(input)
    if not schema:
        return input

    consumed: dict[str, Any] = {}
    for option in schema:
        names = {option.name, *option.aliases}
        if option.param:
            names.add(option.param)
        for key in [k for k in options if k in names]:
            consumed[option.param or option.name] = options.pop(key)

    # Generic delivery: append every consumed option as a query parameter
    # on the input string; the matching handler parses it from the URL
    # (github's _clone_github_to_temp reads ?ref=...). Falsy values are
    # skipped — same semantics as the original ``if ref:`` github path.
    for key, value in consumed.items():
        if not value:
            continue
        separator = "&" if "?" in input else "?"
        input = f"{input}{separator}{key}={value}"

    return input


def att(
    input: str | os.PathLike[str] | Iterable[str | os.PathLike[str]],
    *,
    api_key: str | None = None,
    prefer: str | None = None,
    **options: Any,
) -> Artifacts:
    """Turn any input into LLM-ready artifacts.

    This is the main entry point for the attachments library.

    Args:
        input: Source to process — a string, a ``pathlib.Path``, or a list
            (any iterable) of them, read in order (``**options`` apply to
            each). Strings support inline options via DSL:
            - Local file: "document.pdf" ("~/..." and "file:///..." too)
            - With options: "document.pdf[pages: 1-4]"
            - Directory: "docs/" (an overview first, then the files; secrets,
              dependencies, hidden and .gitignore'd files are skipped —
              see ``att.options("file://")``)
            - Pattern: "src/**/*.py", "reports/*/summary.md"
            - URL: "https://example.com/file.pdf[pages: 5-10]"
            - Web page: "https://example.com/post" (Markdown of the main
              content; ``[links: true]``, ``[screenshot: true]``, ...)
            - GitHub: "github://owner/repo[ref: main]"
            - Excel: "data.xlsx[sheet: Sales, rows: 100]"
        api_key: Optional API key for service mode. If provided, enables
            fallback to remote processing when local deps are missing.
        prefer: Processing preference:
            - "local" (default): Try local first, fall back to service
            - "service": Try service first, fall back to local
            - "local-only": Only use local processing
            - "service-only": Only use service
        **options: The kwargs twin of the DSL — every DSL option can be
            passed as a keyword argument instead, and explicit kwargs
            override DSL options on collision:
            ``att("d.pdf[pages: 1-1]", pages="2-3")`` processes pages 2-3.

    DSL Syntax:
        path[key: value, key2: value2, ...]

        Values: numbers (300), booleans (true/false), ranges (1-4),
        bare or quoted strings. Keys belong to processors: each processor
        declares its option schema, discoverable at runtime via
        ``att.options(".pdf")`` (or all of them via ``att.options()``).
        Aliases (``page`` -> ``pages``, ``pw`` -> ``password``,
        ``branch`` -> ``ref``, ...) come from those schemas too.

        Options are resolved per file against the matched processor's
        schema. Unknown keys never fail silently: they are dropped with a
        warning in that artifact's ``meta.warnings`` (e.g. "Unknown option
        'sheets' for .xlsx — did you mean 'sheet'?"). When a directory
        unpacks into mixed file types, an option like ``pages`` applies to
        the PDFs and produces per-file unknown-option warnings on the
        others — that is expected. Files with no processor at all get no
        option warnings.

    Returns:
        An :class:`attachments.Artifacts` — a ``list`` subclass whose
        elements remain plain artifact dicts, each with:
            - text: Extracted text content
            - images: List of image dicts
            - audio: List of audio dicts (future)
            - video: List of video dicts (future)
            - meta: Typed metadata (source, kind, error{code,message}, via, ...)

        The container adds interactive sugar around the frozen IR:
        ``repr()`` is a one-line summary, ``str()``/``.text`` is the
        assembled prompt (``render_text``), plus ``.images``, ``.errors``,
        ``.claude()``, ``.openai()``, and ``.chunk()`` shortcuts.

        Errors never raise out of att(); they come back as artifacts with
        ``meta["error"] = {"code": ..., "message": ...}`` (so the return
        value is ALWAYS Artifacts, including every error path).

    Example:
        >>> from attachments import att
        >>> # Simple usage
        >>> artifacts = att("document.pdf")
        >>> # With DSL options
        >>> artifacts = att("document.pdf[pages: 1-4]")
        >>> artifacts = att("report.pdf[pages: 1-10, images: true, dpi: 300]")
        >>> artifacts = att("data.xlsx[sheet: Revenue, rows: 50]")
        >>> # Explicit kwargs override DSL
        >>> artifacts = att("doc.pdf[pages: 1-4]", pages="1-2")  # pages 1-2
        >>> # Discover the options a processor declares
        >>> [o["name"] for o in att.options(".xlsx")][:3]
        ['sheet', 'rows', 'images']
    """
    out = Artifacts()
    for item in _input_items(input):
        if isinstance(item, dict):  # an input that is not a path: an error artifact
            out.append(item)
        else:
            out.extend(_att_one(item, api_key=api_key, prefer=prefer, options=options))
    return out


def _input_items(value: Any) -> list[Any]:
    """Flatten ``att()``'s input into strings (or error artifacts), in order.

    Paths become strings; lists, tuples and generators are read in order
    (nested ones too); sets are sorted so the result is deterministic.
    Anything else becomes an ``unpack-error`` artifact — ``att()`` never
    raises.

    Examples:
        >>> from pathlib import Path
        >>> _input_items(["a.txt", (Path("b.pdf"), "c.csv")])
        ['a.txt', 'b.pdf', 'c.csv']
        >>> _input_items({"z.txt", "a.txt"})
        ['a.txt', 'z.txt']
        >>> _input_items(42)[0]["meta"]["error"]["code"]
        'unpack-error'
    """
    if isinstance(value, str):
        return [value]
    if isinstance(value, os.PathLike):
        return [os.fsdecode(os.fspath(value))]
    if isinstance(value, bytes | bytearray | memoryview):
        return [
            error_artifact(
                "<bytes>",
                ERROR_UNPACK,
                "att() takes paths and URLs, not file contents. To read bytes, "
                "save them to a file, or call a processor directly: "
                "attachments.processors['.pdf'](data, filename='x.pdf').",
            )
        ]
    if isinstance(value, Mapping) or not isinstance(value, Iterable):
        return [
            error_artifact(
                repr(value)[:80],
                ERROR_UNPACK,
                "att() takes a path or URL (str or pathlib.Path), or a list of "
                f"them; got {type(value).__name__}.",
            )
        ]
    items = list(value)
    if isinstance(value, set | frozenset):
        items.sort(key=_sort_key)
    out: list[Any] = []
    for item in items:
        out.extend(_input_items(item))
    return out


def _sort_key(value: Any) -> str:
    if isinstance(value, str | os.PathLike):
        return os.fsdecode(os.fspath(value))
    return repr(value)


def _att_one(
    input: str,
    *,
    api_key: str | None,
    prefer: str | None,
    options: dict[str, Any],
) -> Artifacts:
    """``att()`` for one input string."""
    # Parse DSL options from input string
    input, dsl_options = parse_dsl(input)

    # Merge options: explicit kwargs override DSL options
    merged_options = {**dsl_options, **options}

    # Folder options (files, tree, ignore, max_files, ...) go to the source;
    # other source options (e.g. GitHub ref) travel in the input string.
    tree_raw = _take_tree_options(input, merged_options)
    tree_options, tree_warnings = resolve_options(
        TREE_OPTIONS, tree_raw, context="folders"
    )
    input = _apply_source_options(input, merged_options)

    log.info("att(%r)  prefer=%s  options=%s", input, prefer, merged_options or "{}")

    # Handle unpack with potential service fallback
    reports: list[Any] = []
    try:
        resolution = resolve(input, options=tree_options)
        pairs: list[tuple[str, bytes]] = resolution.files
        reports = resolution.reports
    except InvalidSourceOption as e:
        return Artifacts([error_artifact(input, ERROR_INVALID_OPTION, str(e))])
    except Exception as e:
        # Check if we can use service for unpacking
        key = get_api_key(api_key)
        mode = get_prefer(prefer)

        if service_configured(api_key) and mode not in ("local-only",):
            try:
                from .service import ServiceError, unpack_via_service

                pairs = unpack_via_service(input, api_key=key)
            except ServiceError as se:
                return Artifacts(
                    [
                        error_artifact(
                            input,
                            ERROR_UNPACK,
                            f"unpack failed: {e}; service: {se.message}",
                        )
                    ]
                )
            except ImportError:
                return Artifacts(
                    [error_artifact(input, ERROR_UNPACK, f"unpack failed: {e}")]
                )
            except Exception as se:
                return Artifacts(
                    [
                        error_artifact(
                            input, ERROR_UNPACK, f"unpack failed: {e}; service: {se}"
                        )
                    ]
                )
        else:
            return Artifacts(
                [error_artifact(input, ERROR_UNPACK, f"unpack failed: {e}")]
            )

    out = Artifacts()

    # One overview per folder/repository/pattern/archive, before its files.
    from ._overview import needs_overview, overview_artifact

    for report in reports:
        report.warnings[:0] = tree_warnings
        if needs_overview(report):
            out.append(overview_artifact(report))
    if tree_raw and not reports:
        names = ", ".join(sorted(tree_raw))
        tree_warnings = [
            *tree_warnings,
            f"Folder options ({names}) apply to folders, patterns, repositories "
            "and archives; ignored for a single file.",
        ]
    elif reports:
        tree_warnings = []

    # Process each file. Downloads are SourceFiles: (name, bytes) pairs
    # that also carry the final URL and any source warnings.
    for pair in pairs:
        fname, data = pair
        origin = getattr(pair, "url", None)
        artifact = _process_single(
            fname,
            data,
            options=merged_options,
            api_key=api_key,
            prefer=prefer,
            url=origin,
        )
        artifact = normalize_artifact(artifact, fname)
        if origin:
            # A downloaded file is known by its address, not by the last
            # path segment ("download", "index.html").
            artifact["meta"]["source"] = origin
        _attach_warnings(
            artifact, [*(getattr(pair, "warnings", ()) or ()), *tree_warnings]
        )
        out.append(artifact)

    return out
