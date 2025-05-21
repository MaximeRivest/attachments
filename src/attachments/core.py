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
import warnings

from .registry import REGISTRY


# ------------------------------------------------------------------ #
#                       Abstract plugin ABCs                         #
# ------------------------------------------------------------------ #
class Loader(Protocol):
    """Sub-class and register → turn path → Python object."""

    @classmethod
    def match(cls, path: str) -> bool: ...
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
        if not isinstance(original, str):
            original = str(original)
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
    # _BRACKET_RX = re.compile(r"(.*)\\[(.*)\\]$") # Remove or comment out old regex

    @classmethod
    def _split(cls, s: str) -> Tuple[str, str]:
        """Separate `file.ext[param1:value1,param2]` into ('file.ext', 'param1…').
        
        Handles nested brackets by finding the last top-level square bracket pair
        at the end of the string, which is assumed to be the command block.
        Example: "https://example.com/file.pdf?p=[abc][cmd1,cmd2]"
        should be split into ("https://example.com/file.pdf?p=[abc]", "cmd1,cmd2").
        """
        # Find the last '['
        last_bracket_open_idx = s.rfind('[')

        # If no '[' is found, or if the string doesn't end with ']',
        # or if the last '[' is after the last char (should not happen with rfind unless string is "[")
        # or if the last '[' is the last character itself.
        if last_bracket_open_idx == -1 or not s.endswith(']') or last_bracket_open_idx >= len(s) - 1:
            return s, ""

        # Potential path part and command part
        path_part = s[:last_bracket_open_idx]
        cmd_part = s[last_bracket_open_idx + 1 : -1] # Content between last '[' and final ']'

        # If the path_part is empty AND the original string started with '[',
        # it means the original string was like "[cmd]". This is not a path with a command.
        if not path_part and s.startswith('['):
            return s, "" # Treat as a path without commands

        # Heuristic for URL query parameters: if path_part ends with '=',
        # it's likely that the stuff in brackets was a value, not a command.
        if path_part.endswith('='):
            return s, "" # Treat the whole thing as a path

        # If the extracted command part is empty after stripping, it's not a valid command.
        if not cmd_part.strip():
             # This could be a path like "file_with_empty_brackets[]" or "file_with_spaces[ ]"
             return s, ""

        return path_part, cmd_part.strip()

    # ------------------------- loading ---------------------------- #
    def _load(self) -> Any:
        loader_cls = REGISTRY.first("loader",
                                    lambda L: L.match(self.path))
        if loader_cls is None:
            # With PlainTextLoader, this should ideally not be hit for existent files
            # unless PlainTextLoader itself is somehow disabled or not registered.
            # However, if a file is truly unreadable or of an unhandled binary type
            # that even PlainTextLoader can't process meaningfully, this path might still be relevant.
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
        warnings.warn(
            "Method to_openai_content() is deprecated, use to_openai() instead.",
            DeprecationWarning,
            stacklevel=2
        )
        return self.to_openai(prompt)


class Attachments:
    """
    A thin wrapper around **many** `Attachment` objects.

    >>> a = Attachments("file.pdf", "photo.jpg[rotate:90]")
    >>> len(a), a.images, str(a)[:80]
    (2, ['data:image/png;base64,....'], '…first 80 chars of combined text…')
    """

    # ---------------------------------------------------------- #
    #                       constructor                          #
    # ---------------------------------------------------------- #
    def __init__(self, *sources: Any):
        """
        *sources* may be a mix of:

        * str / pathlib.Path → turned into an `Attachment`
        * Attachment        → kept as-is
        * Attachments       → flattened into this container
        """
        self._atts: List[Attachment] = []
        for src in sources:
            if isinstance(src, Attachment):
                self._atts.append(src)
            elif isinstance(src, Attachments):
                self._atts.extend(src._atts)
            else:  # assume path / URL string
                self._atts.append(Attachment(src))

    # ---------------------------------------------------------- #
    #                 📜 combined "view" fields                   #
    # ---------------------------------------------------------- #
    @property
    def text(self) -> str | None:
        parts = [att.text for att in self._atts if att.text]
        return "\n\n".join(parts) if parts else None

    @property
    def images(self) -> List[str] | None:
        imgs = [img for att in self._atts for img in (att.images or [])]
        return imgs or None

    @property
    def audio(self) -> List[str] | None:
        aud = [a for att in self._atts for a in (att.audio or [])]
        return aud or None

    # ---------------------------------------------------------- #
    #                     formatting helpers                     #
    # ---------------------------------------------------------- #
    def format_for(self, style: str = "openai", prompt: str | None = None):
        """
        Aggregate all attachments and package them for a downstream API
        using the same deliverer mechanism as a single `Attachment`.
        """
        d_cls = REGISTRY.first("deliverer", lambda D: D.name == style.lower())
        if d_cls is None:
            raise ValueError(f"No deliverer named '{style}'")
        return d_cls().package(self.text, self.images, self.audio, prompt)

    # convenience wrappers (filled in dynamically below)
    # e.g. to_openai_content, to_claude_content, …

    # ---------------------------------------------------------- #
    #                    collection protocol                     #
    # ---------------------------------------------------------- #
    def __len__(self) -> int:                # len(a)
        return len(self._atts)

    def __iter__(self):                      # for att in a
        return iter(self._atts)

    def __getitem__(self, idx):              # a[0] or a[1:3]
        if isinstance(idx, slice):
            return Attachments(*self._atts[idx])
        return self._atts[idx]

    # ---------------------------------------------------------- #
    #                     nice string views                      #
    # ---------------------------------------------------------- #
    def __str__(self) -> str:
        return self.text or ""

    def __repr__(self) -> str:
        return f"Attachments({len(self)} items)"

# -------------------------------------------------------------- #
#            Inject helper methods like .as_openai()             #
# -------------------------------------------------------------- #
def _mk_api_method(name: str):
    def _api(self, prompt: str = ""):
        return self.format_for(name, prompt)
    _api.__name__ = f"to_{name}"
    return _api


# ------------------------------------------------------------------ #
__all__ = ["Attachment", "Attachments", "Loader", "Renderer", "Transform"]
