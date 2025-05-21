"""Public helpers for plugin authors.

Usage::

    from attachmentsv2.plugin_api import register_plugin, requires

    @register_plugin(kind="renderer_text", priority=50)
    @requires("pytesseract", "PIL")
    class ImageOCRText(Renderer):
        ...

The @requires decorator guards against missing optional dependencies.
If *any* of the modules listed cannot be imported, the class is marked as
`_attachments_disabled = True` and `@register_plugin` silently skips
registration, while emitting a friendly warning.
"""
from __future__ import annotations

import warnings
from importlib.util import find_spec
from typing import Type, Callable, Any

from .registry import REGISTRY

__all__ = ["requires", "register_plugin"]

# ----------------------------------------------------------- #
#                        requires()                           #
# ----------------------------------------------------------- #

def requires(*modules: str):
    """Decorator that flags the wrapped class as disabled if *any* module
    in *modules* cannot be found (based on importlib.util.find_spec).
    """

    missing = [m for m in modules if find_spec(m) is None]

    def decorator(cls: Type[Any]) -> Type[Any]:
        if missing:
            warnings.warn(
                f"Skipping plugin {cls.__name__} – missing deps: {missing}",
                RuntimeWarning,
            )
            cls._attachments_disabled = True  # type: ignore[attr-defined]
        return cls

    return decorator

# ----------------------------------------------------------- #
#                     register_plugin()                       #
# ----------------------------------------------------------- #

def register_plugin(kind: str, priority: int = 100):
    """Decorator that registers the class with REGISTRY when appropriate.

    Registration is skipped if the class was previously marked as disabled
    by the @requires decorator (or any other mechanism that sets
    ``_attachments_disabled = True``).
    """

    def decorator(cls: Type[Any]) -> Type[Any]:
        if getattr(cls, "_attachments_disabled", False):
            # silently ignore – requires() already warned
            return cls
        REGISTRY.register(kind, cls, priority)
        return cls

    return decorator 