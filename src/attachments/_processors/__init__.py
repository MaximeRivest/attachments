# ruff: noqa: I001
from __future__ import annotations

import inspect
import re
from collections.abc import Callable
from dataclasses import dataclass

from .._options import (
    Option,
    register_options,
    reset_options,
    snapshot_option_defaults,
)
from ..types import Processor

# Global registry for processors (extension -> callable)
# Keys are lowercase extensions like ".pdf" or sentinel keys like "__text__".
# Values follow the IR processor contract (``types.Processor``):
# ``(data: bytes, *, filename=None, **options) -> Artifact``.
processors: dict[str, Processor] = {}

# Snapshot of default processors after initial registration (populated lazily)
_default_processors: dict[str, Processor] | None = None


#: Detection hook of a named processor: ``(data, filename) -> bool``.
Detector = Callable[[bytes, str], bool]


@dataclass(frozen=True)
class NamedProcessor:
    """A specialized processor: one of several for the same extension.

    The standard processor of an extension (``processors[".pdf"]``) reads
    every file; a named one reads the files it is chosen for — by name
    (``[processor: invoice]``) or, when it has a ``detect`` function, by
    looking at the file. See :func:`processor`.

    Attributes:
        name: What ``[processor: ...]`` and ``meta.extra.processor`` call it.
        func: The processor (IR contract). When it declares a ``base``
            parameter it receives the standard processing as ``base``.
        detect: ``(data, filename) -> bool``; ``None`` = only by name.
        options: Its own options, on top of the standard ones.
    """

    name: str
    func: Processor
    detect: Detector | None = None
    options: tuple[Option, ...] = ()

    @property
    def wants_base(self) -> bool:
        """Whether :attr:`func` takes the standard processing as ``base``."""
        return _takes_base(self.func)


def _takes_base(func: Callable) -> bool:
    try:
        parameter = inspect.signature(func).parameters.get("base")
    except (TypeError, ValueError):
        return False
    return parameter is not None and parameter.kind in (
        inspect.Parameter.KEYWORD_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
    )


#: Named processors: extension -> name -> entry, in registration order.
named_processors: dict[str, dict[str, NamedProcessor]] = {}

#: Name that always means the standard processor of an extension.
STANDARD = "default"

_NAME_RE = re.compile(r"[a-z][a-z0-9_-]*\Z")


def _normalize_key(key: str) -> str:
    """Normalize a processor key to lowercase with leading dot.

    Examples:
        >>> _normalize_key("PDF")
        '.pdf'
        >>> _normalize_key(".TXT")
        '.txt'
        >>> _normalize_key("xlsx")
        '.xlsx'
        >>> _normalize_key("__text__")  # Sentinel keys preserved
        '__text__'
    """
    k = key.strip()
    if k.startswith("__"):
        return k
    if not k.startswith("."):
        k = "." + k
    return k.lower()


def register_processor(
    key: str,
    func: Processor | None = None,
    registry: dict[str, Processor] | None = None,
) -> Callable:
    """Register a processor for a single file extension.

    Can be used as a function or decorator:

        # As a function
        register_processor(".docx", my_docx_processor)

        # As a decorator
        @register_processor(".docx")
        def docx_processor(data: bytes, **options) -> dict:
            ...

    To register one function for multiple extensions, use the
    :func:`processor` decorator instead:

        @processor(".doc", ".docx", ".rtf")
        def word_processor(data: bytes, **options) -> dict:
            ...

    Args:
        key: File extension (e.g., ".pdf") or sentinel key (e.g., "__text__")
        func: Processor following the IR contract
            ``(data: bytes, *, filename=None, **options) -> Artifact``
        registry: Optional custom registry dict. If None, uses the global registry.

    Returns:
        The registered function (for decorator use)

    Examples:
        >>> # Using a custom registry to avoid global state
        >>> from attachments.types import make_artifact
        >>> my_registry = {}
        >>> def my_proc(data: bytes, **opts) -> dict:
        ...     return make_artifact(text=data.decode())
        >>> register_processor(
        ...     ".custom", my_proc, registry=my_registry
        ... )  # doctest: +ELLIPSIS
        <function my_proc at ...>
        >>> ".custom" in my_registry
        True

        >>> # As decorator
        >>> @register_processor(".decorated", registry=my_registry)
        ... def decorated_proc(data: bytes, **opts) -> dict:
        ...     return make_artifact(text="decorated")
        >>> ".decorated" in my_registry
        True
    """
    target = registry if registry is not None else processors

    def decorator(fn: Processor) -> Processor:
        target[_normalize_key(key)] = fn
        return fn

    # Called as @register_processor(".ext") - returns decorator
    if func is None:
        return decorator

    # Called as register_processor(".ext", func) - register directly
    target[_normalize_key(key)] = func
    return func


def processor(
    *extensions: str,
    options: tuple[Option, ...] | None = None,
    name: str | None = None,
    detect: Detector | None = None,
) -> Callable:
    """Decorator to register a processor for multiple extensions.

    Without *name* it becomes THE processor of those extensions (replacing
    the built-in one). With *name* it is a specialized processor that
    lives next to the standard one:

    - ``att("x.pdf[processor: invoice]")`` uses it for that file;
    - with *detect*, it is also chosen for every file where
      ``detect(data, filename)`` is true (the most recently registered
      first; ``[processor: default]`` forces the standard one);
    - its *options* are added to the standard ones of the extension;
    - a ``base`` parameter, if it declares one, receives the standard
      processing: ``base()`` returns the artifact the file would have had
      without this processor (with service fallback, as usual), and
      ``base(pages="1-2")`` the same with other options;
    - ``meta.extra.processor`` of the result names it.

    Args:
        *extensions: One or more file extensions to register
        options: Optional declared option schema, registered for every
            extension (the ergonomic twin of ``register_options``). For a
            named processor: its own options only.
        name: Registers a specialized processor under this name
            (lowercase letters, digits, ``-`` and ``_``; not "default").
        detect: For a named processor: ``(data, filename) -> bool``,
            choosing it automatically. Keep it cheap (the first bytes,
            the file name): it runs for every file of these extensions.

    Returns:
        Decorator function

    Examples:
        >>> # Check that built-in processors exist
        >>> ".txt" in processors
        True
        >>> ".pdf" in processors
        True

        >>> # The decorator registers extensions and (optionally) a schema:
        >>> # @processor(".doc", ".docx", options=(Option("images", "bool"),))
        >>> # def word_processor(data, **opts): ...
    """

    if name is None:
        if detect is not None:
            raise ValueError("detect= needs a name= (it chooses a named processor)")

        def decorator(fn: Processor) -> Processor:
            for ext in extensions:
                processors[_normalize_key(ext)] = fn
                if options is not None:
                    register_options(ext, options)
            return fn

        return decorator

    if not isinstance(name, str) or not _NAME_RE.match(name) or name == STANDARD:
        raise ValueError(
            f"processor name must be lowercase letters, digits, '-' or '_' "
            f"(and not {STANDARD!r}), got {name!r}"
        )
    if not extensions:
        raise ValueError("a named processor needs at least one extension")

    def named(fn: Processor) -> Processor:
        entry = NamedProcessor(name, fn, detect, tuple(options or ()))
        for ext in extensions:
            table = named_processors.setdefault(_normalize_key(ext), {})
            table.pop(name, None)  # re-registering moves it to the end
            table[name] = entry
        return fn

    return named


def get_named(key: str) -> dict[str, NamedProcessor]:
    """The named processors of *key* (an extension), in registration order.

    Examples:
        >>> get_named(".pdf")
        {}
    """
    return named_processors.get(_normalize_key(key), {})


def _snapshot_defaults() -> None:
    """Capture current processors as defaults (called once after initial imports)."""
    global _default_processors
    if _default_processors is None:
        _default_processors = dict(processors)


def reset_processors() -> None:
    """Reset the global processor registry to its default state.

    Useful for testing to ensure test isolation. Restores only the
    built-in processors (text, pdf, xlsx) and removes any custom processors,
    named ones included.
    Also resets the declared option schemas (``attachments._options``).
    """
    global processors
    if _default_processors is not None:
        processors.clear()
        processors.update(_default_processors)
    named_processors.clear()  # no built-in processor is a named one
    reset_options()


def get_processors_copy() -> dict[str, Processor]:
    """Return a shallow copy of the current processor registry.

    Useful for creating isolated registries for testing or custom pipelines.

    Examples:
        >>> copy = get_processors_copy()
        >>> isinstance(copy, dict)
        True
        >>> ".txt" in copy
        True
        >>> copy is processors  # It's a copy, not the same object
        False
    """
    return dict(processors)


# Import modules to trigger self-registration
from . import text as _text  # noqa: E402,F401
from . import xlsx as _xlsx  # noqa: E402,F401
from . import pdf as _pdf  # noqa: E402,F401
from . import docx as _docx  # noqa: E402,F401
from . import html as _html  # noqa: E402,F401
from . import pptx as _pptx  # noqa: E402,F401
from . import image as _image  # noqa: E402,F401
from . import csv as _csv  # noqa: E402,F401
from . import svg as _svg  # noqa: E402,F401
from . import ipynb as _ipynb  # noqa: E402,F401
from . import audio as _audio  # noqa: E402,F401

# After docx/pptx/xlsx: reuses their processors and option schemas.
from . import legacy_office as _legacy_office  # noqa: E402,F401

# Capture defaults after built-in processors (and their schemas) registered
_snapshot_defaults()
snapshot_option_defaults()


__all__ = [
    "NamedProcessor",
    "Processor",
    "get_named",
    "named_processors",
    "processors",
    "register_processor",
    "processor",
    "reset_processors",
    "get_processors_copy",
    "Option",
    "register_options",
]
