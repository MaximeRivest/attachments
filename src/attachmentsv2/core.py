"""
Core abstractions + the high-level Attachment class.

Attachment pipeline:
    path string
      └─► Loader                   (from registry.loader)
      └─► zero-or-many Transforms  (registry.transform,     via [token:arg] DSL)
      └─► Renderer(s)              (registry.renderer_*)
"""

from __future__ import annotations
import os
import re
from typing import Any, Dict, List, Tuple, Protocol

from .registry import REGISTRY


# ------------------------------------------------------------------ #
#                       Abstract plugin ABCs                         #
# ------------------------------------------------------------------ #
class Loader(Protocol):
    """Sub-class and register → turn path → Python object."""

    def match(self, path: str) -> bool: ...
    def load(self, path: str) -> Any: ...


class Renderer(Protocol):
    """Sub-class and register → turn object → text / images / audio."""

    # must be 'text' | 'image' | 'audio'
    content_type: str = "text"

    def match(self, obj: Any) -> bool: ...
    def render(self, obj: Any, meta: Dict[str, Any]) -> Any: ...


class Transform(Protocol):
    """Sub-class and register → modify object after load.

    Attribute `name` (str) is the DSL token that triggers the transform:
        Attachment("img.png[rotate:90]")  # token = 'rotate', arg = '90'
    """

    name: str

    def apply(self, obj: Any, arg: str | None) -> Any: ...


class Deliverer(Protocol):
    """
    Turn the results of .text / .images / .audio into the format
    expected by a downstream client (OpenAI, Anthropic, LangChain …).
    """
    name: str                        # e.g. 'openai', 'claude'
    def package(self,
                text: str | None,
                images: list[str] | None,
                audio: list[str] | None,
                prompt: str | None = None) -> Any: ...


# Register the ABC types themselves (optional; useful for reflection)
REGISTRY.register("abc", Loader, 0)
REGISTRY.register("abc", Renderer, 0)
REGISTRY.register("abc", Transform, 0)
REGISTRY.register("abc", Deliverer, 0)
# ------------------------------------------------------------------ #
#                         Attachment class                           #
# ------------------------------------------------------------------ #
class Attachment:
    """High-level façade.  Users *only* import this class."""

    # -------------------------------------------------------------- #
    def __init__(self, original: str) -> None:
        self.original = original
        self.path, self._cmd = self._split(original)

        # load
        self.obj = self._load()

        # transforms
        self.obj = self._apply_transforms(self.obj, self._cmd)

        # render
        self.text: str | None = self._render("text")
        self.images: List[str] | None = self._render("image")
        self.audio: List[str] | None = self._render("audio")

    # -------------------------------------------------------------- #
    #                           internals                            #
    # -------------------------------------------------------------- #
    _BRACKET_RX = re.compile(r"(.*)\[(.*)\]$")

    @classmethod
    def _split(cls, s: str) -> Tuple[str, str]:
        """Separate `file.ext[param1:value1,param2]` into ('file.ext', 'param1…')."""
        m = cls._BRACKET_RX.match(s)
        return (m.group(1), m.group(2)) if m else (s, "")

    # ------------------------- loading ---------------------------- #
    def _load(self) -> Any:
        loader_cls = REGISTRY.first("loader",
                                    lambda L: L().match(self.path))
        if loader_cls is None:
            raise ValueError(f"No loader registered for '{self.path}'")
        return loader_cls().load(self.path)

    # ----------------------- transforms --------------------------- #
    def _apply_transforms(self, obj: Any, cmd: str) -> Any:
        if not cmd:
            return obj
        for token in filter(None, (t.strip() for t in cmd.split(","))):
            name, *arg = token.split(":", 1)
            arg = arg[0] if arg else None
            t_cls = REGISTRY.first("transform", lambda T: T.name == name)
            if t_cls:
                obj = t_cls().apply(obj, arg)
        return obj

    # ------------------------ rendering --------------------------- #
    def _render(self, ctype: str):
        key = f"renderer_{ctype}"
        rend_cls = REGISTRY.first(key,
                                  lambda R: getattr(R, "content_type", None) == ctype
                                            and R().match(self.obj))
        if rend_cls is None:
            return None
        return rend_cls().render(self.obj, {})

    # -------------------------------------------------------------- #
    #                        dunder helpers                          #
    # -------------------------------------------------------------- #
    def __str__(self) -> str:
        return self.text or ""

    def __repr__(self) -> str:
        return f"Attachment({self.original!r})"


    # -------------------------------------------------------------- #
    #                          deliverers                           #
    # -------------------------------------------------------------- #
    def format_for(self, style: str = "openai", prompt: str | None = None):
        """
        Convert this attachment's .text / .images / .audio into the
        data structure expected by a given downstream API.
        """
        d_cls = REGISTRY.first(
            "deliverer", lambda D: D.name == style.lower()
        )
        if d_cls is None:
            raise ValueError(f"No deliverer named '{style}'")
        return d_cls().package(self.text, self.images, self.audio, prompt)

    # Convenience for OpenAI / Claude, etc.
    # Users can of course write their own wrappers.
    def to_openai_content(self, prompt: str = ""):
        return self.format_for("openai", prompt)

# ------------------------------------------------------------------ #
__all__ = ["Attachment", "Loader", "Renderer", "Transform"]
