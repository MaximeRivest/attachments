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
from typing import Callable, Dict, List, Tuple, Type, Any

# --------------------------------------------------------------------- #
class _Registry:
    """Internal singleton; do *not* instantiate twice."""
    def __init__(self) -> None:
        # {kind: List[Tuple[int, Type]]}
        self._plugins: Dict[str, List[Tuple[int, Type[Any]]]] = defaultdict(list)

    # ---------------- registration ---------------- #
    def register(self,
                 kind: str,
                 plugin_cls: Type[Any],
                 priority: int = 100) -> None:
        """Add a plugin class with a priority (higher = preferred)."""
        if not isinstance(priority, int):
            raise TypeError("priority must be int")
        self._plugins[kind].append((priority, plugin_cls))
        self._plugins[kind].sort(key=lambda t: -t[0])        # high → low

    # --------------- priority tweaks -------------- #
    def bump_priority(self,
                      plugin_cls: Type[Any],
                      delta: int) -> None:
        """Raise or lower an existing plugin’s priority."""
        for kind, lst in self._plugins.items():
            for i, (prio, cls) in enumerate(lst):
                if cls is plugin_cls:
                    lst[i] = (prio + delta, cls)
            lst.sort(key=lambda t: -t[0])

    # ----------------- retrieval ------------------ #
    def first(self,
              kind: str,
              predicate: Callable[[Type[Any]], bool]) -> Type[Any] | None:
        """Return the first plugin of `kind` whose class satisfies predicate."""
        for _, cls in self._plugins.get(kind, []):
            if predicate(cls):
                return cls
        return None

    def all(self,
            kind: str,
            predicate: Callable[[Type[Any]], bool] | None = None) -> List[Type[Any]]:
        """Return *all* plugins of a kind, optionally filtered by predicate."""
        pred = predicate or (lambda _: True)
        return [cls for _, cls in self._plugins.get(kind, []) if pred(cls)]

    # ------------------- misc --------------------- #
    def kinds(self) -> List[str]:
        return list(self._plugins.keys())

    def dump(self) -> None:
        """Pretty-print current registry (debug helper)."""
        from pprint import pprint
        view = {k: [(p, c.__name__) for p, c in v] for k, v in self._plugins.items()}
        pprint(view)


# a single global instance
REGISTRY: _Registry = _Registry()

__all__ = ["REGISTRY"]
