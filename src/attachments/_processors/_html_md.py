"""HTML -> Markdown for LLM prompts (the text half of the html processor).

Why a dedicated renderer instead of ``soup.get_text()`` or a generic
converter: web pages need decisions a generic tool does not make, and each
one changes what a model reads.

- **Inline vs block.** Text flows through links, emphasis and highlighted
  code without line breaks; only block elements (paragraphs, headings,
  list items, cells of layout tables, ...) start new lines. ``get_text("\\n")``
  breaks a sentence at every link, which is what this module replaces.
- **Tables.** *Data* tables become Markdown pipe tables (``rowspan``
  values repeat down, empty spacer columns drop). *Layout* tables — old
  sites built whole pages from them — are read as plain blocks, using
  Mozilla Readability's data-table test, so an essay laid out in a table
  is not squeezed into one table cell.
- **Code.** ``<pre>`` becomes a fenced block with its language when the
  markup names one; syntax-highlighting spans, copy buttons and line-number
  gutters do not leak into the code.
- **Maths.** MathML is written as its TeX source (``$...$``), the form
  Wikipedia and MathJax pages ship alongside the rendering.
- **Main content** (``main=True`` in :func:`render`): navigation, site
  headers/footers, sidebars, dialogs and a short list of boilerplate
  classes (cookie banners, share bars, ads, MediaWiki edit links) are
  skipped. The rules follow how browsers expose landmarks to assistive
  technology (HTML-AAM): ``<header>``, ``<footer>`` and ``<aside>`` are
  page chrome only when they are not inside an article/section/main —
  an article's own header (title, byline) is kept. When the page marks a
  single ``<main>`` that is used as the scope. If boilerplate removal
  leaves almost nothing, the whole page is used instead (``main_fallback``).
  Nothing here guesses by link density or text statistics, so content
  tables and link lists (a Hacker News front page, a references section)
  are never thrown away.

Markdown special characters in text are NOT escaped: the reader is a
language model, not a Markdown parser, and ``\\[edit\\]``-style escapes are
noise. Only ``|`` inside table cells is escaped, because it would break
the table.

Pure functions over a parsed BeautifulSoup tree; nothing is mutated.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from typing import Any
from urllib.parse import urljoin

# ---------------------------------------------------------------------------
# Element classes
# ---------------------------------------------------------------------------

#: Never rendered (no text a reader of the page would see as content).
_SKIP_TAGS = frozenset(
    {
        "head", "title", "meta", "link", "base", "script", "style", "noscript",
        "template", "svg", "canvas", "iframe", "frame", "frameset", "object",
        "embed", "param", "audio", "video", "source", "track", "map", "area",
        "input", "select", "option", "optgroup", "datalist", "textarea",
        "button", "rp", "slot",
    }
)  # fmt: skip

#: Elements that start and end a block of text (everything else is inline,
#: including unknown/custom elements, which are transparent).
_BLOCK_TAGS = frozenset(
    {
        "html", "body", "address", "article", "aside", "center", "details",
        "div", "fieldset", "figcaption", "figure", "footer", "form", "header",
        "hgroup", "legend", "main", "nav", "p", "search", "section", "caption",
        "tbody", "thead", "tfoot", "tr", "td", "th", "frameset", "noframes",
    }
)  # fmt: skip

_HEADINGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}

#: Inline wrappers -> Markdown marker.
_EMPHASIS = {
    "strong": "**",
    "b": "**",
    "em": "*",
    "i": "*",
    "del": "~~",
    "s": "~~",
    "strike": "~~",
}

_CODE_INLINE = frozenset({"code", "kbd", "samp", "tt"})

#: Content that introduces its own scope for header/footer/aside (HTML-AAM:
#: inside these, header/footer/aside are not page landmarks).
_SECTIONING = frozenset({"article", "aside", "main", "nav", "section"})

#: ARIA roles that mark page chrome, not content.
_CHROME_ROLES = frozenset(
    {
        "navigation", "banner", "contentinfo", "complementary", "search",
        "menu", "menubar", "dialog", "alertdialog", "toolbar",
    }
)  # fmt: skip

#: Whole class names that mark boilerplate. MediaWiki (Wikipedia and every
#: other MediaWiki site) gets explicit entries because it is the single most
#: common reference page on the web and its chrome is precisely marked.
_CHROME_CLASSES = frozenset(
    {
        "mw-editsection", "mw-jump-link", "navbox", "vertical-navbox",
        "catlinks", "printfooter", "noprint", "skip-link", "skiplink",
        "skip-to-content", "visually-hidden-focusable", "mw-portlet",
    }
)  # fmt: skip

#: Words (from class/id, split on non-alphanumerics) that mark small
#: boilerplate widgets. Applied only to elements holding less than
#: ``_WIDGET_MAX_SHARE`` of the page's text, so a wrapper like
#: ``class="content with-sidebar"`` can never take the article with it.
_CHROME_WORDS = frozenset(
    {
        "cookie", "cookies", "consent", "gdpr", "newsletter", "breadcrumb",
        "breadcrumbs", "sidebar", "share", "sharing", "social", "related",
        "advert", "adverts", "advertisement", "ad", "ads", "adsbygoogle",
        "sponsor", "sponsored", "popup", "modal", "dropdown",
    }
)  # fmt: skip
_WIDGET_MAX_SHARE = 0.25

#: Code-block decorations that are not code.
_CODE_NOISE_CLASSES = frozenset(
    {"linenos", "lineno", "line-numbers", "gutter", "copybtn", "copy-button"}
)

_WS = re.compile(r"[ \t\n\r\f\v\u00a0\u2028\u2029]+")
_SPACES = re.compile(r" {2,}")
#: Characters that render as nothing (soft hyphen, zero-width space, BOM,
#: word joiner). ZWJ/ZWNJ are kept: they change shaping in many scripts.
_INVISIBLE = dict.fromkeys(map(ord, "\u00ad\u200b\u2060\ufeff"))
_LANG_CLASS = re.compile(r"^(?:language|lang|highlight(?:-source)?)-(.+)$")
_NOT_A_LANGUAGE = frozenset(
    {"default", "none", "text", "plain", "plaintext", "nohighlight", "notranslate"}
)
_DISPLAYSTYLE = re.compile(r"^\{\\(?:display|text)style\s*(.*)\}$", re.DOTALL)
_HIDDEN_STYLE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden", re.I)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _bs4_types() -> tuple[type, type, tuple[type, ...]]:
    """(Tag, NavigableString, string types that are never text).

    TemplateString is not in the list: inert ``<template>`` elements are
    skipped as tags, while declarative shadow DOM templates are content.
    """
    from bs4 import element

    skip_strings = tuple(
        t
        for t in (
            getattr(element, name, None)
            for name in (
                "Comment",
                "CData",
                "ProcessingInstruction",
                "Declaration",
                "Doctype",
                "Script",
                "Stylesheet",
            )
        )
        if t is not None
    )
    return element.Tag, element.NavigableString, skip_strings


def _classes(el: Any) -> list[str]:
    value = el.get("class") or []
    if isinstance(value, str):
        value = value.split()
    return [c.lower() for c in value]


def _words(el: Any) -> set[str]:
    raw = " ".join(_classes(el)) + " " + str(el.get("id") or "").lower()
    return {w for w in re.split(r"[^a-z0-9]+", raw) if w}


def _is_hidden(el: Any) -> bool:
    if el.has_attr("hidden") or str(el.get("aria-hidden", "")).lower() == "true":
        return True
    return bool(_HIDDEN_STYLE.search(str(el.get("style") or "")))


def _int_attr(el: Any, name: str, *, cap: int = 1000) -> int:
    try:
        value = int(str(el.get(name, "1")).strip())
    except ValueError:
        return 1
    return min(max(value, 1), cap)


def _fence_for(text: str, *, minimum: int) -> str:
    longest = max((len(m) for m in re.findall(r"`+", text)), default=0)
    return "`" * max(minimum, longest + 1)


def _collapse_inline(text: str) -> str:
    """Collapse spaces inside one inline run, keeping ``<br>`` newlines."""
    lines = [_SPACES.sub(" ", line).strip() for line in text.split("\n")]
    out: list[str] = []
    for line in lines:
        if line == "" and (not out or out[-1] == ""):
            continue
        out.append(line)
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out)


def _indent(text: str, first: str, rest: str) -> str:
    lines = text.split("\n")
    return "\n".join(
        (first if i == 0 else (rest if line else "")) + line
        for i, line in enumerate(lines)
    )


def _is_line_number_column(el: Any) -> bool:
    """An aria-hidden element holding only digits: a code line-number gutter."""
    if str(el.get("aria-hidden", "")).lower() != "true":
        return False
    return not el.get_text().strip("0123456789 \n\t")


def _math_tex(math: Any) -> str:
    """TeX for a MathML element (alttext or a TeX annotation), else ''."""
    tex = str(math.get("alttext") or "").strip()
    if not tex:
        ann = math.find(
            "annotation", attrs={"encoding": re.compile(r"tex", re.IGNORECASE)}
        )
        if ann is not None:
            tex = ann.get_text().strip()
    match = _DISPLAYSTYLE.match(tex)
    if match:
        tex = match.group(1).strip()
    return _WS.sub(" ", tex)


def _code_language(pre: Any) -> str:
    """Language named by the markup around a ``<pre>`` (classes/data-lang)."""
    candidates: list[Any] = [pre]
    code = pre.find("code")
    if code is not None:
        candidates.insert(0, code)
    parent = pre.parent
    for _ in range(2):  # Sphinx/GitHub put it on a wrapper div or two up
        if parent is None or getattr(parent, "name", None) is None:
            break
        candidates.append(parent)
        parent = parent.parent
    for el in candidates:
        lang = el.get("data-lang") or el.get("data-language")
        if lang:
            return str(lang).strip().lower()
        classes = _classes(el)
        for i, cls in enumerate(classes):
            lang = ""
            if cls in ("brush:", "brush") and i + 1 < len(classes):
                lang = classes[i + 1].rstrip(";")  # SyntaxHighlighter: "brush: js"
            else:
                m = _LANG_CLASS.match(cls)
                if m:
                    lang = m.group(1).strip("-")
            if lang and lang not in _NOT_A_LANGUAGE:
                return lang
    return ""


# ---------------------------------------------------------------------------
# Data tables vs layout tables (Mozilla Readability's _isDataTable)
# ---------------------------------------------------------------------------


def _own_rows(table: Any) -> list[Any]:
    return [tr for tr in table.find_all("tr") if tr.find_parent("table") is table]


def _own_cells(tr: Any) -> list[Any]:
    return [c for c in tr.find_all(["td", "th"], recursive=False)]


#: Inside a cell, these mark page structure (layout), not a value.
_LAYOUT_TAGS = ("table", "form", "nav", "section", "article", "aside", "iframe")

#: A data cell holds at most this many characters: more is a block of
#: content that a one-line table cell would squeeze.
_PLAIN_CELL_CHARS = 200


def _plain_cell(cell: Any) -> bool:
    """A value (short text, maybe a short list or heading), not a layout box."""
    if cell.find(_LAYOUT_TAGS) is not None:
        return False
    return len(cell.get_text(" ", strip=True)) <= _PLAIN_CELL_CHARS


def is_data_table(table: Any) -> bool:
    """Readability's test: does this ``<table>`` hold data (vs. layout)?

    Descendant checks only look at this table's own cells, not those of a
    nested table (Readability counts nested ones too, which marks layout
    tables wrapping a data table as data).

    Examples:
        >>> from bs4 import BeautifulSoup
        >>> def t(html):
        ...     return is_data_table(BeautifulSoup(html, "html.parser").table)
        >>> t(
        ...     "<table><tr><th>a</th><th>b</th></tr>"
        ...     "<tr><td>1</td><td>2</td></tr></table>"
        ... )
        True
        >>> t("<table><tr><td>one cell of layout</td></tr></table>")
        False
        >>> t(
        ...     "<table><tr><td>Name</td><td>Age</td></tr>"
        ...     "<tr><td>Ann</td><td>9</td></tr></table>"
        ... )
        True
        >>> t(
        ...     "<table><tr><td><nav>Home</nav></td><td><form>Go</form></td></tr>"
        ...     "<tr><td>Body</td><td>x</td></tr></table>"
        ... )
        False
        >>> long = "long text " * 30
        >>> t(
        ...     f"<table><tr><td>{long}</td><td>x</td></tr>"
        ...     "<tr><td>a</td><td>b</td></tr></table>"
        ... )
        False
        >>> t('<table role="presentation"><tr><th>a</th></tr></table>')
        False
        >>> t(
        ...     "<table><tr><td><table><tr><td>x</td></tr></table></td>"
        ...     "<td>y</td></tr></table>"
        ... )
        False
    """
    role = str(table.get("role", "")).lower()
    if role in ("presentation", "none"):
        return False
    if role in ("table", "grid", "treegrid"):
        return True
    if str(table.get("datatable", "")) == "0":
        return False
    if table.get("summary"):
        return True
    caption = table.find("caption")
    if caption is not None and caption.find_parent("table") is table:
        if caption.get_text(strip=True):
            return True
    for tag in ("col", "colgroup", "tfoot", "thead", "th"):
        for el in table.find_all(tag):
            if el.find_parent("table") is table:
                return True
    if table.find("table") is not None:
        return False
    rows = _own_rows(table)
    columns = max(
        (sum(_int_attr(c, "colspan") for c in _own_cells(tr)) for tr in rows),
        default=0,
    )
    if len(rows) <= 1 or columns <= 1:
        return False
    if len(rows) >= 10 or columns > 4:
        return True
    # Readability calls every small table without headers layout; for a
    # model, losing the rows and columns of a small data table costs more.
    # Short cells are data; layout tables hold page structure or long text.
    if all(_plain_cell(c) for tr in rows for c in _own_cells(tr)):
        return True
    return len(rows) * columns > 10


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Ctx:
    sectioned: bool = False  # inside article/aside/main/nav/section
    heading: bool = False  # no emphasis markers inside headings
    link: bool = False  # inside a link already (no nested links)
    marks: frozenset[str] = frozenset()  # emphasis markers already open


class _Writer:
    """Accumulates inline text and finished blocks."""

    __slots__ = ("blocks", "inline")

    def __init__(self) -> None:
        self.blocks: list[str] = []
        self.inline: list[str] = []

    def text(self, s: str) -> None:
        if s:
            self.inline.append(s)

    def flush(self) -> None:
        if self.inline:
            text = _collapse_inline("".join(self.inline))
            self.inline = []
            if text:
                self.blocks.append(text)

    def block(self, s: str) -> None:
        self.flush()
        if s.strip():
            self.blocks.append(s)

    def done(self) -> list[str]:
        self.flush()
        return self.blocks


class _Renderer:
    def __init__(
        self,
        *,
        links: bool,
        base_url: str | None,
        skip: Callable[[Any, _Ctx], bool] | None,
    ) -> None:
        self.links = links
        self.base_url = base_url
        self.skip = skip
        self.images: list[Any] = []  # every <img> rendered, in order
        self.has_h1 = False
        self.Tag, self.NavigableString, self.skip_strings = _bs4_types()

    # -- entry points -------------------------------------------------------

    def blocks(self, root: Any, ctx: _Ctx | None = None) -> list[str]:
        w = _Writer()
        self.node(root, w, ctx or _Ctx())
        return w.done()

    def inline_text(self, el: Any, ctx: _Ctx) -> str:
        """Render *el* as one line (block structure flattened)."""
        w = _Writer()
        self.children(el, w, ctx)
        return " ".join(b.replace("\n", " ") for b in w.done()).strip()

    # -- dispatch -----------------------------------------------------------

    def children(self, el: Any, w: _Writer, ctx: _Ctx) -> None:
        for child in el.children:
            self.node(child, w, ctx)

    def node(self, n: Any, w: _Writer, ctx: _Ctx) -> None:
        if isinstance(n, self.NavigableString):
            if not isinstance(n, self.skip_strings):
                w.text(_WS.sub(" ", str(n).translate(_INVISIBLE)))
            return
        if not isinstance(n, self.Tag):
            return
        name = (n.name or "").lower()

        if name == "math":
            self.math(n, w)
            return
        if self.skip is not None and self.skip(n, ctx):
            # Maths hidden for visual users (MediaWiki ships MathML in a
            # display:none span next to an image) is still the formula.
            for math in n.find_all("math"):
                self.math(math, w)
            return
        if name == "template" and (
            n.has_attr("shadowrootmode") or n.has_attr("shadowroot")
        ):
            self.children(n, w, ctx)  # declarative shadow DOM is shown content
            return
        if name in _SKIP_TAGS:
            if name == "button" and (
                n.has_attr("aria-expanded") or n.has_attr("aria-controls")
            ):
                self.children(n, w, ctx)  # disclosure buttons label content
            return

        if name in _SECTIONING and not ctx.sectioned:
            ctx = replace(ctx, sectioned=True)

        if name in _HEADINGS:
            text = self.inline_text(n, replace(ctx, heading=True))
            if text:
                w.block("#" * _HEADINGS[name] + " " + text)
                self.has_h1 = self.has_h1 or name == "h1"
        elif name == "br":
            w.text("\n")
        elif name == "hr":
            w.block("---")
        elif name == "pre":
            self.pre(n, w)
        elif name == "blockquote":
            body = "\n\n".join(self.blocks_of_children(n, ctx))
            if body:
                w.block("\n".join("> " + ln if ln else ">" for ln in body.split("\n")))
        elif name in ("ul", "ol", "menu", "dir"):
            self.list_block(n, w, ctx)
        elif name == "li":  # an item outside any list
            self.list_item(n, w, ctx, "- ")
        elif name == "dl":
            self.definition_list(n, w, ctx)
        elif name == "table":
            self.table(n, w, ctx)
        elif name == "summary":
            text = self.inline_text(n, ctx)
            if text:
                w.block(f"**{text}**")
        elif name == "img":
            self.image(n, w)
        elif name == "a":
            self.anchor(n, w, ctx)
        elif name in _EMPHASIS:
            self.emphasis(n, w, ctx, _EMPHASIS[name])
        elif name in _CODE_INLINE:
            self.code_inline(n, w)
        elif name in ("sup", "sub"):
            self.script(n, w, ctx, "^" if name == "sup" else "_")
        elif name == "q":
            w.text('"')
            self.children(n, w, ctx)
            w.text('"')
        elif name in _BLOCK_TAGS:
            w.flush()
            self.children(n, w, ctx)
            w.flush()
        else:  # inline or unknown/custom element: transparent
            self.children(n, w, ctx)

    def blocks_of_children(self, el: Any, ctx: _Ctx) -> list[str]:
        w = _Writer()
        self.children(el, w, ctx)
        return w.done()

    # -- inline -------------------------------------------------------------

    def wrap_inline(
        self, n: Any, w: _Writer, ctx: _Ctx, render: Callable[[str], str]
    ) -> None:
        """Render children; wrap them with *render* if they stayed inline.

        Block content inside an inline element (a card link wrapping a
        heading and a paragraph) is passed through unwrapped: Markdown has
        no way to put blocks inside emphasis or a link.
        """
        sub = _Writer()
        self.children(n, sub, ctx)
        if sub.blocks:
            for block in sub.done():
                w.block(block)
            return
        text = "".join(sub.inline)
        core = text.strip()
        if not core:
            w.text(text)
            return
        lead = text[: len(text) - len(text.lstrip())]
        trail = text[len(text.rstrip()) :]
        w.text(lead + render(_SPACES.sub(" ", core)) + trail)

    def emphasis(self, n: Any, w: _Writer, ctx: _Ctx, mark: str) -> None:
        if ctx.heading or mark in ctx.marks:
            self.children(n, w, ctx)
            return
        inner = replace(ctx, marks=ctx.marks | {mark})
        self.wrap_inline(n, w, inner, lambda s: f"{mark}{s}{mark}")

    def code_inline(self, n: Any, w: _Writer) -> None:
        text = _WS.sub(" ", n.get_text().translate(_INVISIBLE))
        core = text.strip()
        if not core:
            w.text(text)
            return
        fence = _fence_for(core, minimum=1)
        pad = " " if core.startswith("`") or core.endswith("`") else ""
        w.text(f"{fence}{pad}{core}{pad}{fence}")

    def script(self, n: Any, w: _Writer, ctx: _Ctx, mark: str) -> None:
        """``x<sup>2</sup>`` -> ``x^2``; citation markers stay ``[1]``."""
        text = self.inline_text(n, ctx)
        if not text:
            return
        if text.startswith("[") or ctx.link or n.find("a") is not None:
            w.text(text)
        elif re.fullmatch(r"[\w.+\-−′*]+", text):
            w.text(mark + text)
        else:
            w.text(f"{mark}({text})")

    def anchor(self, n: Any, w: _Writer, ctx: _Ctx) -> None:
        href = str(n.get("href") or "").strip()
        if href.startswith("#") and not any(ch.isalnum() for ch in n.get_text()):
            return  # heading permalink ("¶", "#", "§", "🔗")
        if not self.links or ctx.link or not href or href.startswith("#"):
            self.children(n, w, ctx)
            return
        if href.lower().startswith(("javascript:", "data:", "vbscript:")):
            self.children(n, w, ctx)
            return
        url = self.resolve(href)
        dest = f"<{url}>" if (" " in url or url.count("(") != url.count(")")) else url

        # Link text is not escaped: it may hold an image's own Markdown.
        self.wrap_inline(n, w, replace(ctx, link=True), lambda t: f"[{t}]({dest})")

    def image(self, n: Any, w: _Writer) -> None:
        self.images.append(n)
        if not self.links:
            return
        if any(c.startswith("mwe-math-fallback") for c in _classes(n)):
            return  # the MathML twin is rendered instead
        src = str(n.get("src") or "").strip()
        if not src or src.startswith("data:"):
            return
        alt = _WS.sub(" ", str(n.get("alt") or "")).strip()
        alt = alt.replace("[", "\\[").replace("]", "\\]")
        w.text(f"![{alt}]({self.resolve(src)})")

    def math(self, n: Any, w: _Writer) -> None:
        tex = _math_tex(n) or _WS.sub(" ", n.get_text(" ")).strip()
        if not tex:
            return
        if str(n.get("display", "")).lower() == "block":
            w.block(f"$${tex}$$")
        else:
            w.text(f"${tex}$")

    def resolve(self, href: str) -> str:
        if self.base_url:
            try:
                return urljoin(self.base_url, href)
            except ValueError:
                return href
        return href

    # -- blocks -------------------------------------------------------------

    def pre(self, n: Any, w: _Writer) -> None:
        parts: list[str] = []

        def collect(el: Any) -> None:
            for child in el.children:
                if isinstance(child, self.NavigableString):
                    if not isinstance(child, self.skip_strings):
                        parts.append(str(child))
                elif isinstance(child, self.Tag):
                    name = (child.name or "").lower()
                    if name == "br":
                        parts.append("\n")
                    elif name in ("button", "script", "style", "template"):
                        continue
                    elif _CODE_NOISE_CLASSES.intersection(_classes(child)):
                        continue
                    elif _is_line_number_column(child):
                        continue
                    else:
                        collect(child)

        collect(n)
        code = "".join(parts).translate(_INVISIBLE).replace("\r\n", "\n")
        code = "\n".join(line.rstrip() for line in code.split("\n")).strip("\n")
        if not code.strip():
            return
        fence = _fence_for(code, minimum=3)
        w.block(f"{fence}{_code_language(n)}\n{code}\n{fence}")

    def list_block(self, n: Any, w: _Writer, ctx: _Ctx) -> None:
        ordered = n.name == "ol"
        number = _int_attr(n, "start", cap=10**9) if ordered and n.get("start") else 1
        if ordered and n.has_attr("reversed") and not n.get("start"):
            number = len(n.find_all("li", recursive=False))
        items: list[str] = []
        for child in n.children:
            if not isinstance(child, self.Tag):
                continue
            if (child.name or "").lower() != "li":
                # Stray content (or a nested list without an <li>) inside a list
                for block in self.blocks(child, ctx):
                    items.append(_indent(block, "  ", "  "))
                continue
            if self.skip is not None and self.skip(child, ctx):
                continue
            marker = f"{number}. " if ordered else "- "
            if ordered:
                if child.get("value", "").strip().lstrip("-").isdigit():
                    number = int(child["value"])
                    marker = f"{number}. "
                number = number - 1 if n.has_attr("reversed") else number + 1
            item = self.list_item_text(child, ctx, marker)
            if item:
                items.append(item)
        if items:
            w.block("\n".join(items))

    def list_item_text(self, li: Any, ctx: _Ctx, marker: str) -> str:
        box = li.find("input", attrs={"type": "checkbox"}, recursive=True)
        prefix = ""
        if box is not None and box.find_parent("li") is li:
            prefix = "[x] " if box.has_attr("checked") else "[ ] "
        blocks = self.blocks_of_children(li, ctx)
        body = "\n".join(blocks)
        if not body.strip():
            return ""
        return _indent(prefix + body, marker, " " * len(marker))

    def list_item(self, li: Any, w: _Writer, ctx: _Ctx, marker: str) -> None:
        item = self.list_item_text(li, ctx, marker)
        if item:
            w.block(item)

    def definition_list(self, n: Any, w: _Writer, ctx: _Ctx) -> None:
        lines: list[str] = []

        def visit(el: Any) -> None:
            for child in el.children:
                if not isinstance(child, self.Tag):
                    continue
                name = (child.name or "").lower()
                if self.skip is not None and self.skip(child, ctx):
                    continue
                if name == "dt":
                    term = self.inline_text(child, ctx)
                    if term:
                        if lines:
                            lines.append("")
                        lines.append(term)
                elif name == "dd":
                    body = "\n\n".join(self.blocks_of_children(child, ctx))
                    if body:
                        lines.append(_indent(body, ": ", "  "))
                elif name == "div":  # <div> grouping is valid inside <dl>
                    visit(child)
                else:
                    lines.extend(self.blocks(child, ctx))

        visit(n)
        text = "\n".join(lines).strip("\n")
        if text:
            w.block(text)

    def table(self, n: Any, w: _Writer, ctx: _Ctx) -> None:
        if not is_data_table(n):
            w.flush()
            self.children(n, w, ctx)
            w.flush()
            return

        caption_el = n.find("caption")
        caption = ""
        if caption_el is not None and caption_el.find_parent("table") is n:
            caption = self.inline_text(caption_el, ctx)

        rows = [tr for tr in _own_rows(n) if not (self.skip and self.skip(tr, ctx))]
        # The HTML table model: each cell occupies a rectangle of slots.
        # Slot value: (text, spanned_from_left). A rowspan repeats the value
        # down (every row stays self-contained); a colspan leaves the extra
        # columns blank (except when header rows are merged, below).
        slots: dict[tuple[int, int], tuple[str, bool]] = {}
        header_flags: list[bool] = []
        for r, tr in enumerate(rows):
            cells = _own_cells(tr)
            col = 0
            for cell in cells:
                while (r, col) in slots:
                    col += 1
                text = self.cell_text(cell, ctx)
                colspan = _int_attr(cell, "colspan")
                rowspan = min(_int_attr(cell, "rowspan"), len(rows) - r)
                for dr in range(rowspan):
                    for dc in range(colspan):
                        slots.setdefault((r + dr, col + dc), (text, dc > 0))
                col += colspan
            in_thead = (
                tr.find_parent("thead") is not None and tr.find_parent("table") is n
            )
            header_flags.append(
                in_thead or (bool(cells) and all(c.name == "th" for c in cells))
            )

        width = max((c + 1 for _, c in slots), default=0)
        if width == 0:
            return
        grid = [
            [slots.get((r, c), ("", False)) for c in range(width)]
            for r in range(len(rows))
        ]

        # Leading header rows (thead rows, or rows made only of <th>).
        n_head = 0
        while n_head < len(grid) and header_flags[n_head]:
            n_head += 1
        if n_head == len(grid):  # all-<th> table: first row is the header
            n_head = min(1, len(grid))

        if n_head > 1:
            header = []
            for c in range(width):
                seen: list[str] = []
                for r in grid[:n_head]:
                    value = r[c][0]
                    if value and value not in seen:
                        seen.append(value)
                header.append(" / ".join(seen))
        elif n_head == 1:
            header = [t if not spanned else "" for t, spanned in grid[0]]
        else:
            header = [""] * width
        body = [[t if not spanned else "" for t, spanned in r] for r in grid[n_head:]]

        # Drop spacer columns and empty rows.
        keep = [c for c in range(width) if header[c] or any(r[c] for r in body)]
        if not keep:
            return
        header = [header[c] for c in keep]
        body = [[r[c] for c in keep] for r in body]
        body = [r for r in body if any(r)]

        if len(keep) == 1:  # a one-column "table" reads better as lines
            lines = [v for v in [header[0], *(r[0] for r in body)] if v]
            text = "\n".join(lines)
            w.block("\n\n".join(x for x in (caption, text) if x))
            return

        def line(values: Iterable[str]) -> str:
            return "| " + " | ".join(values) + " |"

        out = [line(header), line("---" for _ in header), *(line(r) for r in body)]
        if caption:
            out.insert(0, caption + "\n")
        w.block("\n".join(out))

    def cell_text(self, cell: Any, ctx: _Ctx) -> str:
        blocks = self.blocks_of_children(cell, ctx)
        text = "<br>".join(b.replace("\n", "<br>") for b in blocks)
        return text.replace("|", "\\|").strip()


# ---------------------------------------------------------------------------
# Main-content scoping
# ---------------------------------------------------------------------------


def _text_len(el: Any) -> int:
    return len(_WS.sub("", el.get_text()))


def _chrome_predicate(total_chars: int) -> Callable[[Any, _Ctx], bool]:
    """Element filter for ``main=True`` (see the module docstring)."""
    widget_cap = max(int(total_chars * _WIDGET_MAX_SHARE), 1)

    def skip(el: Any, ctx: _Ctx) -> bool:
        name = (el.name or "").lower()
        if name in ("html", "body", "main"):
            return False
        if name == "nav" or name == "dialog":
            return True
        if name in ("header", "footer", "aside") and not ctx.sectioned:
            return True
        role = str(el.get("role") or "").lower()
        if role in _CHROME_ROLES:
            return True
        if str(el.get("aria-modal", "")).lower() == "true":
            return True
        if _is_hidden(el):
            return True
        classes = _classes(el)
        if _CHROME_CLASSES.intersection(classes):
            return True
        if _CHROME_WORDS.intersection(_words(el)):
            return _text_len(el) < widget_cap
        return False

    return skip


def _main_scope(body: Any) -> tuple[Any, str]:
    """The element holding the page's main content, and how it was found."""
    mains = body.find_all("main")
    mains += [m for m in body.find_all(attrs={"role": "main"}) if m not in mains]
    # Ignore a <main> nested in another (invalid, but seen): keep outermost.
    mains = [
        m for m in mains if not any(o is not m and m in o.descendants for o in mains)
    ]
    if len(mains) == 1:
        return mains[0], "main"
    if not mains:
        articles = [
            a for a in body.find_all("article") if a.find_parent("article") is None
        ]
        if len(articles) == 1:
            total = _text_len(body)
            if total and _text_len(articles[0]) >= total * 0.5:
                return articles[0], "article"
    return body, "body"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

#: When main-content extraction keeps fewer characters than this while the
#: full page has at least ``_FALLBACK_RATIO`` times more, the page has no
#: usable structure and the full render is used instead.
_FALLBACK_MIN_CHARS = 200
_FALLBACK_RATIO = 5


@dataclass
class Rendered:
    text: str
    images: list[Any]  # <img> elements in the rendered scope, in order
    scope: str  # "main" | "article" | "body" | "page" | "selection"
    main_fallback: bool = False
    has_h1: bool = False


def _join(blocks: list[str]) -> str:
    return "\n\n".join(b for b in blocks if b.strip()).strip()


def render(
    root: Any,
    *,
    main: bool = True,
    links: bool = False,
    base_url: str | None = None,
) -> Rendered:
    """Render a parsed document (or any element) to Markdown.

    Args:
        root: A BeautifulSoup document or element.
        main: Skip page chrome and scope to ``<main>`` when there is one.
        links: Write links as ``[text](url)`` and images as ``![alt](url)``;
            otherwise links are plain text and images are omitted.
        base_url: Resolves relative link/image URLs (with ``links=True``).

    Examples:
        >>> from bs4 import BeautifulSoup
        >>> html = '''<body><nav><a href="/">Home</a></nav>
        ...   <main><h1>Title</h1><p>Read <a href="/doc">the
        ...   docs</a> and <code>run()</code>.</p></main></body>'''
        >>> print(render(BeautifulSoup(html, "html.parser")).text)
        # Title
        <BLANKLINE>
        Read the docs and `run()`.
        >>> print(
        ...     render(
        ...         BeautifulSoup(html, "html.parser"),
        ...         main=False,
        ...         links=True,
        ...         base_url="https://x.org/a/",
        ...     ).text
        ... )
        [Home](https://x.org/)
        <BLANKLINE>
        # Title
        <BLANKLINE>
        Read [the docs](https://x.org/doc) and `run()`.
    """
    body = root.find("body") if hasattr(root, "find") else None
    if body is None:
        body = root

    if not main:
        r = _Renderer(links=links, base_url=base_url, skip=None)
        text = _join(r.blocks(body))
        return Rendered(text, r.images, "page", has_h1=r.has_h1)

    scope_el, scope = _main_scope(body)
    r = _Renderer(
        links=links, base_url=base_url, skip=_chrome_predicate(_text_len(scope_el))
    )
    text = _join(r.blocks(scope_el, _Ctx(sectioned=scope_el is not body)))
    if len(text) < _FALLBACK_MIN_CHARS:
        full = _Renderer(links=links, base_url=base_url, skip=None)
        full_text = _join(full.blocks(body))
        if len(full_text) >= max(len(text), 1) * _FALLBACK_RATIO:
            return Rendered(
                full_text, full.images, "page", main_fallback=True, has_h1=full.has_h1
            )
    return Rendered(text, r.images, scope, has_h1=r.has_h1)


def render_selection(
    matches: list[Any], *, links: bool = False, base_url: str | None = None
) -> Rendered:
    """Render CSS-selected elements, each as its own block, in order.

    Selections are explicit, so nothing in them is treated as chrome.
    """
    r = _Renderer(links=links, base_url=base_url, skip=None)
    blocks: list[str] = []
    for el in matches:
        if (el.name or "").lower() in ("title", "head"):
            blocks.append(_WS.sub(" ", el.get_text()).strip())
        else:
            blocks.append(_join(r.blocks(el)))
    return Rendered(_join(blocks), r.images, "selection")
