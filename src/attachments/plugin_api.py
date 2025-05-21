"""Public helpers for plugin authors.

Usage::

    from attachments.plugin_api import register_plugin, requires

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
import logging
from importlib.util import find_spec
from typing import Type, Callable, Any
import inspect
import sys

from .registry import REGISTRY

logger = logging.getLogger("attachments")

__all__ = ["requires", "register_plugin"]

# ----------------------------------------------------------- #
#                        requires()                           #
# ----------------------------------------------------------- #

def requires(*modules: str, pip_names: dict[str, str] | None = None):
    """Decorator that flags the wrapped class as disabled if *any* module
    in *modules* cannot be found (based on importlib.util.find_spec).

    Args:
        *modules: Python module names to check for (e.g., 'PIL', 'pytesseract').
        pip_names: Optional mapping from module name to pip package name
                   (e.g., {"PIL": "Pillow", "fitz": "PyMuPDF"}).
                   Used to generate helpful error messages.
    """
    if pip_names is None:
        pip_names = {} # Default to empty dict

    missing_modules = []
    for m in modules:
        try:
            # find_spec is good, but let's try a direct import to be sure and to catch other issues
            __import__(m)
        except ImportError:
            missing_modules.append(m)
        except Exception: # Other errors during import check
            missing_modules.append(m) # Treat as missing for safety

    def decorator(cls: Type[Any]) -> Type[Any]:
        if missing_modules:
            error_messages = []
            for mod_name in missing_modules:
                pip_name = pip_names.get(mod_name, mod_name) # Fallback to module name if not in pip_names
                error_messages.append(f"Module '{mod_name}' not found. Try `pip install {pip_name}`.")
            
            # Combine messages into a single error
            full_error_message = f"Plugin '{cls.__name__}' is disabled due to missing dependencies:\n" + "\n".join(f"  - {msg}" for msg in error_messages)
            
            # Instead of just warning and setting a flag, we make the class itself unusable
            # by replacing it with a proxy that raises an informative error upon instantiation.
            # This makes the problem more immediately obvious to the developer using the plugin.

            class MissingDependencyProxy:
                _attachments_original_plugin_name = cls.__name__
                _attachments_disabled_reason = full_error_message
                _attachments_disabled = True
                _attachments_disabled_msg = full_error_message

                def __init__(self, *args, **kwargs):
                    raise RuntimeError(self._attachments_disabled_reason)

                # expose reason for diagnostics
                _attachments_disabled = True
                _attachments_disabled_msg = full_error_message

                @classmethod # Keep match as classmethod if original had it
                def match(cls_proxy, *args, **kwargs):
                     # For selftest in PluginContract, we need match to exist but indicate failure.
                     # It shouldn't be called if the plugin is truly disabled by register_plugin.
                     # However, if someone tries to call it directly on the proxied class:
                    if hasattr(cls, "match") and inspect.ismethod(getattr(cls, "match")):
                        # If the original had a classmethod match, we can't easily call it. 
                        # The best we can do is indicate it's part of a disabled plugin.
                        # Alternatively, always return False or raise the RuntimeError here too.
                        # For simplicity with PluginContract, we need it to exist.
                        # We could also make PluginContract check for _attachments_disabled_reason.
                        print(f"Warning: '{cls_proxy._attachments_original_plugin_name}.match()' called on a plugin disabled due to: {cls_proxy._attachments_disabled_reason}", file=sys.stderr)
                        return False # Or raise RuntimeError(cls_proxy._attachments_disabled_reason)
                    raise RuntimeError(cls_proxy._attachments_disabled_reason)

            # For selftest in PluginContract, we still need _attachments_disabled for the skip logic
            # and _sample_path/_sample_obj if they existed, so register_plugin doesn't fail before skipping.
            if hasattr(cls, "_sample_path"):
                MissingDependencyProxy._sample_path = getattr(cls, "_sample_path") # type: ignore
            if hasattr(cls, "_sample_obj"):
                MissingDependencyProxy._sample_obj = getattr(cls, "_sample_obj") # type: ignore
            if hasattr(cls, "content_type"):
                MissingDependencyProxy.content_type = getattr(cls, "content_type") # type: ignore
            if hasattr(cls, "name"):
                 MissingDependencyProxy.name = getattr(cls, "name") # type: ignore

            # Preserve the original class name for easier debugging
            MissingDependencyProxy.__name__ = f"{cls.__name__} (DisabledDueToMissingDeps)"
            MissingDependencyProxy.__qualname__ = f"{cls.__qualname__} (DisabledDueToMissingDeps)"
            
            # The register_plugin decorator will check for _attachments_disabled and skip registration.
            # The selftest method in PluginContract will also skip if _attachments_disabled is True.
            return MissingDependencyProxy # type: ignore
        return cls

    return decorator

# ----------------------------------------------------------- #
#                     register_plugin()                       #
# ----------------------------------------------------------- #

def register_plugin(kind: str, priority: int = 100):
    def decorator(cls):
        if getattr(cls, "_attachments_disabled", False):
            # remember **why** so we can show it later
            reason = getattr(cls, "_attachments_disabled_msg", "disabled")
            REGISTRY._disabled.append((kind, cls, reason))    # NEW
            return cls                                         # don’t register
        REGISTRY.register(kind, cls, priority)
        return cls
    return decorator