"""
A tiny, priority-aware plugin registry used by the Attachments package.

Plugin *kinds* (keys):

    loader            - subclasses that load raw input → Python object
    renderer_text     - render object → text
    renderer_image    - render object → list[str]   (base64 images)
    renderer_audio    - render object → list[str]   (base64 audio)
    transform         - in-place / functional transforms applied after load

Each list is kept sorted **descending** by priority, so higher numbers
are attempted first.  Users (or other libraries) can register new
plugins at runtime or change priority without touching core code.
"""

from __future__ import annotations
from collections import defaultdict
from typing import Callable, Dict, List, Tuple, Type, Any, NamedTuple
from contextlib import contextmanager
import warnings

# --------------------------------------------------------------------- #
class RegistryItem(NamedTuple):
    cls: Type
    priority: int

class Registry:
    def __init__(self) -> None:
        self._registry = defaultdict(list) # kind -> list[RegistryItem]

    # ---------------- registration ---------------- #
    def register(self,
                 kind: str,
                 cls: Type,
                 priority: int = 100) -> None:
        """Add a plugin class with a priority (higher = preferred)."""
        if not isinstance(priority, int):
            raise TypeError("priority must be int")
        # Basic check if class is already registered to avoid duplicates if reloaded
        if any(item.cls is cls for item in self._registry[kind]):
            warnings.warn(f"Plugin {cls.__name__} already registered for kind '{kind}'. Skipping.", RuntimeWarning)
            return
        self._registry[kind].append(RegistryItem(cls, priority))

    # --------------- priority tweaks -------------- #
    def bump_priority(self,
                      cls: Type,
                      delta: int) -> None:
        """Raise or lower an existing plugin's priority."""
        for kind, items in self._registry.items():
            for i, item in enumerate(items):
                if item.cls is cls:
                    items[i] = RegistryItem(item.cls, item.priority + delta)
            items.sort(key=lambda x: -x.priority)

    # ----------------- retrieval ------------------ #
    def first(self,
              kind: str,
              predicate: Callable[[Type], bool]) -> Type | None:
        """Return the first plugin of `kind` whose class satisfies predicate."""
        for item in sorted(self._registry.get(kind, []), key=lambda x: x.priority, reverse=True):
            if predicate(item.cls):
                return item.cls
        return None

    def all(self,
            kind: str) -> list[Type]:
        """Return *all* plugins of a kind."""
        return [item.cls for item in sorted(self._registry.get(kind, []), key=lambda x: x.priority, reverse=True)]

    # ------------------- misc --------------------- #
    def kinds(self) -> List[str]:
        return list(self._registry.keys())

    def dump(self) -> None:
        """Pretty-print current registry (debug helper)."""
        for kind, items in self._registry.items():
            print(f"  Kind: {kind}")
            for item in sorted(items, key=lambda x: x.priority, reverse=True):
                print(f"    - {item.cls.__name__} (priority: {item.priority})")

    def unregister(self, kind: str, cls: Type) -> None:
        """Remove a plugin class from the registry for a given kind."""
        self._registry[kind] = [item for item in self._registry.get(kind, []) if item.cls is not cls]

    def clear(self) -> None:
        """Clear all registered plugins. Useful for testing."""
        self._registry = defaultdict(list)

    @contextmanager
    def temp_registration(self, kind: str, cls: Type, priority: int = 100):
        """Temporarily register a plugin for the duration of a test."""
        self.register(kind, cls, priority)
        try:
            yield
        finally:
            self.unregister(kind, cls)

# a single global instance
REGISTRY = Registry()

__all__ = ["REGISTRY"]
