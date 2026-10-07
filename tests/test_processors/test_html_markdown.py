"""Tests for the HTML -> Markdown renderer (``_processors/_html_md``).

Each test pins one decision about what a model reads from a web page:
sentences stay whole across inline markup, data tables become pipe
tables while layout tables become paragraphs, code keeps its lines and
language, maths keeps its TeX, and main-content mode drops page chrome
without ever dropping content.
"""

from __future__ import annotations

import pytest

from attachments.deps import check_dep

pytestmark = pytest.mark.skipif(
    not check_dep("html").available, reason="beautifulsoup4 / lxml not installed"
)


def md(html: str, **kwargs) -> str:
    from bs4 import BeautifulSoup

    from attachments._processors._html_md import render

    kwargs.setdefault("main", False)
    return render(BeautifulSoup(html, "lxml"), **kwargs).text


def rendered(html: str, **kwargs):
    from bs4 import BeautifulSoup

    from attachments._processors._html_md import render

    return render(BeautifulSoup(html, "lxml"), **kwargs)


# ---------------------------------------------------------------------------
# Inline flow: the regression this renderer exists for
# ---------------------------------------------------------------------------


class TestInlineFlow:
    def test_links_and_emphasis_do_not_break_sentences(self):
        html = (
            "<p>The paper on <a href='/ml'>machine learning</a> was written at "
            "<a href='/g'>Google</a><sup>[1]</sup> by <i>eight</i> people.</p>"
        )
        assert md(html) == (
            "The paper on machine learning was written at Google[1] by *eight* people."
        )

    def test_highlighted_code_spans_stay_on_one_line(self):
        html = (
            "<pre><span class='gp'>&gt;&gt;&gt; </span><span class='n'>width</span>"
            "<span class='w'> </span><span class='o'>=</span>"
            "<span class='w'> </span><span class='mi'>20</span>\n</pre>"
        )
        assert md(html) == "```\n>>> width = 20\n```"

    def test_whitespace_collapses_like_a_browser(self):
        html = "<p>  one\n   two\t three&nbsp;&nbsp;four</p>"
        assert md(html) == "one two three four"

    def test_invisible_characters_are_dropped(self):
        assert md("<p>hy\u00adphen\u200bated\ufeff</p>") == "hyphenated"

    def test_br_is_a_line_break_and_repeats_collapse(self):
        assert md("<p>a<br>b<br><br><br>c</p>") == "a\nb\n\nc"

    def test_comments_and_doctype_are_not_text(self):
        html = "<!DOCTYPE html><html><body><!-- secret --><p>shown</p></body></html>"
        assert md(html) == "shown"

    def test_custom_elements_are_transparent(self):
        assert md("<p>a <x-chip>custom</x-chip> b</p>") == "a custom b"

    def test_declarative_shadow_dom_is_content_other_templates_are_not(self):
        html = (
            "<x-card><template shadowrootmode='open'><p>Shown</p></template></x-card>"
            "<template><p>Inert</p></template>"
        )
        assert md(html) == "Shown"

    def test_block_inside_inline_element_still_breaks(self):
        html = "<a href='/card'><h3>Card title</h3><p>Card body</p></a>"
        assert md(html, links=True) == "### Card title\n\nCard body"


class TestEmphasisAndCode:
    def test_markers_wrap_trimmed_text(self):
        assert md("<p>a<b> bold </b>b</p>") == "a **bold** b"

    def test_empty_icon_elements_leave_no_markers(self):
        assert md("<p><i class='icon'></i>Menu</p>") == "Menu"

    def test_nested_same_emphasis_is_not_doubled(self):
        assert md("<p><b>out <strong>in</strong></b></p>") == "**out in**"

    def test_no_emphasis_inside_headings(self):
        assert md("<h2>The <em>real</em> title</h2>") == "## The real title"

    def test_strikethrough(self):
        assert md("<p>was <del>$10</del> $5</p>") == "was ~~$10~~ $5"

    def test_inline_code_with_backticks_gets_a_longer_fence(self):
        assert md("<p><code>a`b</code></p>") == "``a`b``"

    def test_superscript_and_subscript_keep_their_meaning(self):
        assert md("<p>E = mc<sup>2</sup> and H<sub>2</sub>O</p>") == "E = mc^2 and H_2O"

    def test_citation_superscripts_stay_plain(self):
        assert md("<p>Claim<sup class='reference'>[12]</sup>.</p>") == "Claim[12]."


# ---------------------------------------------------------------------------
# Links
# ---------------------------------------------------------------------------


class TestLinks:
    def test_plain_text_by_default(self):
        assert md("<p>See <a href='https://x.org'>docs</a>.</p>") == "See docs."

    def test_links_resolve_against_base(self):
        out = md(
            "<p><a href='intro.html'>Intro</a> <a href='/top'>Top</a></p>",
            links=True,
            base_url="https://x.org/docs/",
        )
        assert out == "[Intro](https://x.org/docs/intro.html) [Top](https://x.org/top)"

    def test_fragment_and_script_links_are_text(self):
        out = md(
            "<p><a href='#cite-1'>[1]</a> <a href='javascript:void(0)'>Menu</a></p>",
            links=True,
        )
        assert out == "[1] Menu"

    def test_heading_permalinks_are_dropped(self):
        out = md(
            "<h2>Numbers<a class='headerlink' href='#numbers'>¶</a></h2>", links=True
        )
        assert out == "## Numbers"

    def test_images_only_with_links(self):
        html = "<p>Logo: <img src='/logo.png' alt='ACME logo'></p>"
        assert md(html) == "Logo:"
        assert md(html, links=True, base_url="https://acme.com/") == (
            "Logo: ![ACME logo](https://acme.com/logo.png)"
        )

    def test_linked_image_keeps_both(self):
        html = "<a href='/f'><img src='/t.png' alt='thumb'></a>"
        assert md(html, links=True, base_url="https://w.org/") == (
            "[![thumb](https://w.org/t.png)](https://w.org/f)"
        )

    def test_destination_with_spaces_is_bracketed(self):
        assert md("<a href='a b.pdf'>doc</a>", links=True) == "[doc](<a b.pdf>)"


# ---------------------------------------------------------------------------
# Blocks
# ---------------------------------------------------------------------------


class TestBlocks:
    def test_headings(self):
        assert md("<h1>A</h1><h3>B</h3>") == "# A\n\n### B"

    def test_nested_lists(self):
        html = "<ul><li>one<ul><li>one.a</li></ul></li><li>two</li></ul>"
        assert md(html) == "- one\n  - one.a\n- two"

    def test_ordered_list_start_and_value(self):
        html = "<ol start='3'><li>c</li><li>d</li><li value='10'>j</li></ol>"
        assert md(html) == "3. c\n4. d\n10. j"

    def test_task_list(self):
        html = (
            "<ul><li><input type='checkbox' checked> done</li>"
            "<li><input type='checkbox'> todo</li></ul>"
        )
        assert md(html) == "- [x] done\n- [ ] todo"

    def test_blockquote(self):
        assert md("<blockquote><p>a</p><p>b</p></blockquote>") == "> a\n>\n> b"

    def test_definition_list(self):
        html = "<dl><dt>License</dt><dd>MIT</dd><dt>Author</dt><dd>Ada</dd></dl>"
        assert md(html) == "License\n: MIT\n\nAuthor\n: Ada"

    def test_horizontal_rule(self):
        assert md("<p>a</p><hr><p>b</p>") == "a\n\n---\n\nb"

    def test_summary_is_bold(self):
        assert md("<details><summary>More</summary><p>Hidden</p></details>") == (
            "**More**\n\nHidden"
        )

    def test_form_controls_and_buttons_are_not_text(self):
        html = "<p>Search <input value='q'><button>Go</button></p>"
        assert md(html) == "Search"

    def test_disclosure_button_labels_its_content(self):
        html = "<button aria-expanded='false'>What is it?</button><div>An answer.</div>"
        assert md(html) == "What is it?\n\nAn answer."


class TestCode:
    def test_language_from_code_class(self):
        html = "<pre><code class='language-python'>x = 1</code></pre>"
        assert md(html) == "```python\nx = 1\n```"

    def test_language_from_sphinx_wrapper(self):
        html = (
            "<div class='highlight-pycon'><div class='highlight'>"
            "<pre>&gt;&gt;&gt; 1</pre></div></div>"
        )
        assert md(html) == "```pycon\n>>> 1\n```"

    def test_language_from_syntaxhighlighter_brush(self):
        html = "<pre class='brush: js notranslate'>let a;</pre>"
        assert md(html) == "```js\nlet a;\n```"

    def test_line_numbers_and_copy_buttons_are_not_code(self):
        html = (
            "<pre><span class='linenos'>1</span>a = 1\n"
            "<span class='linenos'>2</span>b = 2<button>Copy</button></pre>"
        )
        assert md(html) == "```\na = 1\nb = 2\n```"

    def test_backtick_fences_inside_code_get_a_longer_fence(self):
        html = "<pre>```\nnested\n```</pre>"
        assert md(html) == "````\n```\nnested\n```\n````"

    def test_indentation_is_preserved(self):
        html = "<pre>def f():\n    return 1\n</pre>"
        assert md(html) == "```\ndef f():\n    return 1\n```"


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------


class TestTables:
    def test_data_table_becomes_a_pipe_table(self):
        html = (
            "<table><tr><th>Name</th><th>Age</th></tr>"
            "<tr><td>Alice</td><td>30</td></tr></table>"
        )
        assert md(html) == "| Name | Age |\n| --- | --- |\n| Alice | 30 |"

    def test_rowspan_repeats_and_colspan_leaves_blank(self):
        html = (
            "<table><thead><tr><th>Company</th><th>HQ</th><th>Note</th></tr></thead>"
            "<tr><td>A</td><td rowspan='2'>US</td><td colspan='1'>x</td></tr>"
            "<tr><td>B</td><td>y</td></tr>"
            "<tr><td colspan='2'>Total</td><td>z</td></tr></table>"
        )
        assert md(html) == (
            "| Company | HQ | Note |\n| --- | --- | --- |\n"
            "| A | US | x |\n| B | US | y |\n| Total |  | z |"
        )

    def test_two_header_rows_merge(self):
        html = (
            "<table><thead><tr><th colspan='2'>2023</th></tr>"
            "<tr><th>Revenue</th><th>Profit</th></tr></thead>"
            "<tr><td>1</td><td>2</td></tr></table>"
        )
        assert md(html) == (
            "| 2023 / Revenue | 2023 / Profit |\n| --- | --- |\n| 1 | 2 |"
        )

    def test_table_without_header_gets_an_empty_header_row(self):
        rows = "".join(f"<tr><td>{i}.</td><td>Story {i}</td></tr>" for i in range(10))
        out = md(f"<table>{rows}</table>")
        assert out.startswith("|  |  |\n| --- | --- |\n| 0. | Story 0 |")

    def test_spacer_columns_and_empty_rows_drop(self):
        html = (
            "<table><tr><th>a</th><th></th><th>b</th></tr>"
            "<tr><td>1</td><td></td><td>2</td></tr><tr><td></td><td></td><td></td></tr>"
            "</table>"
        )
        assert md(html) == "| a | b |\n| --- | --- |\n| 1 | 2 |"

    def test_pipes_escaped_and_multiline_cells_use_br(self):
        html = (
            "<table><tr><th>k</th><th>v</th></tr>"
            "<tr><td>a|b</td><td><ul><li>x</li><li>y</li></ul></td></tr></table>"
        )
        assert md(html) == "| k | v |\n| --- | --- |\n| a\\|b | - x<br>- y |"

    def test_caption_comes_first(self):
        html = (
            "<table><caption>Sales</caption><tr><th>q</th><th>n</th></tr>"
            "<tr><td>Q1</td><td>5</td></tr></table>"
        )
        assert md(html).startswith("Sales\n\n| q | n |")

    def test_layout_table_reads_as_paragraphs(self):
        # Paul Graham / old-web layout: the essay sits in a nested table cell.
        html = (
            "<table><tr><td><img src='nav.gif'></td><td>"
            "<table><tr><td><p>First paragraph.</p><p>Second paragraph.</p>"
            "</td></tr></table>"
            "</td></tr></table>"
        )
        assert md(html) == "First paragraph.\n\nSecond paragraph."

    def test_presentation_role_is_layout(self):
        html = (
            "<table role='presentation'>"
            "<tr><th>Menu</th><td>Body text</td></tr></table>"
        )
        assert "|" not in md(html)

    def test_is_data_table_size_rules(self):
        from bs4 import BeautifulSoup

        from attachments._processors._html_md import is_data_table

        def table(rows: int, cols: int):
            cells = "".join("<td>x</td>" for _ in range(cols))
            body = "".join(f"<tr>{cells}</tr>" for _ in range(rows))
            return BeautifulSoup(f"<table>{body}</table>", "lxml").table

        assert not is_data_table(table(1, 8))  # one row: layout
        assert not is_data_table(table(8, 1))  # one column: layout
        assert is_data_table(table(10, 2))  # many rows: data
        assert is_data_table(table(2, 5))  # many columns: data
        assert not is_data_table(table(3, 3))  # small grid: layout


# ---------------------------------------------------------------------------
# Maths
# ---------------------------------------------------------------------------


class TestMath:
    def test_mathml_alttext_becomes_tex(self):
        html = (
            "<p>where <math alttext='{\\displaystyle d_{k}}'><mi>d</mi></math> is</p>"
        )
        assert md(html) == "where $d_{k}$ is"

    def test_tex_annotation_is_used_without_alttext(self):
        html = (
            "<math display='block'><semantics><mi>x</mi>"
            "<annotation encoding='application/x-tex'>x^2</annotation>"
            "</semantics></math>"
        )
        assert md(html) == "$$x^2$$"

    def test_mediawiki_hidden_mathml_with_image_fallback_renders_once(self):
        html = (
            "<p>Let <span class='mwe-math-element'>"
            "<span class='mwe-math-mathml-inline' style='display: none;'>"
            "<math alttext='{\\displaystyle Q}'><mi>Q</mi></math></span>"
            "<img class='mwe-math-fallback-image-inline'"
            " alt='{\\displaystyle Q}' src='q.svg'>"
            "</span> be the query.</p>"
        )
        for main in (False, True):
            assert rendered(html, main=main, links=True).text == "Let $Q$ be the query."


# ---------------------------------------------------------------------------
# Main content
# ---------------------------------------------------------------------------

ARTICLE = "<p>" + "The article body is the content a reader came for. " * 8 + "</p>"


class TestMainContent:
    def test_site_chrome_is_dropped(self):
        html = (
            "<body><header>Site logo</header><nav>Home | About</nav>"
            f"<div>{ARTICLE}</div>"
            "<aside>Popular posts</aside><footer>Copyright</footer></body>"
        )
        out = rendered(html, main=True).text
        assert "article body" in out
        for chrome in ("Site logo", "Home", "Popular posts", "Copyright"):
            assert chrome not in out

    def test_main_false_keeps_everything(self):
        html = f"<body><nav>Home</nav>{ARTICLE}<footer>Copyright</footer></body>"
        out = rendered(html, main=False).text
        assert "Home" in out and "Copyright" in out

    def test_article_header_and_aside_are_content(self):
        # HTML-AAM: inside an article they are not page landmarks.
        html = (
            "<body><article><header><h1>Title</h1><p>By Ada</p></header>"
            f"{ARTICLE}<aside>Editor's note</aside><footer>Filed under: news</footer>"
            "</article></body>"
        )
        out = rendered(html, main=True).text
        for content in ("# Title", "By Ada", "Editor's note", "Filed under"):
            assert content in out

    def test_single_main_is_the_scope(self):
        html = (
            "<body><div class='topbar'>Promo banner text</div>"
            f"<main><h1>Doc</h1>{ARTICLE}</main>"
            "<div>Unrelated footer links</div></body>"
        )
        r = rendered(html, main=True)
        assert r.scope == "main"
        assert r.text.startswith("# Doc")
        assert "Promo" not in r.text and "Unrelated" not in r.text

    def test_single_dominant_article_is_the_scope(self):
        html = f"<body><div>Header junk</div><article>{ARTICLE}</article></body>"
        r = rendered(html, main=True)
        assert r.scope == "article"
        assert "Header junk" not in r.text

    def test_chrome_roles_are_dropped(self):
        html = f"<body><div role='navigation'>Menu items</div>{ARTICLE}</body>"
        assert "Menu items" not in rendered(html, main=True).text

    def test_small_boilerplate_widgets_are_dropped(self):
        html = (
            f"<body>{ARTICLE}<div class='cookie-banner'>We use cookies.</div>"
            "<div class='share-buttons'>Share on X</div></body>"
        )
        out = rendered(html, main=True).text
        assert "cookies" not in out and "Share on" not in out

    def test_wrapper_named_like_a_widget_keeps_the_article(self):
        # A big wrapper whose class contains "sidebar" must not take the
        # article with it (widget words only apply to small elements).
        html = f"<body><div class='layout with-sidebar'>{ARTICLE}</div></body>"
        assert "article body" in rendered(html, main=True).text

    def test_dialogs_are_chrome_only_in_main_mode(self):
        html = f"<body>{ARTICLE}<dialog open>Subscribe now!</dialog></body>"
        assert "Subscribe" not in rendered(html, main=True).text
        assert "Subscribe" in rendered(html, main=False).text

    def test_hidden_elements_are_dropped(self):
        html = (
            f"<body>{ARTICLE}<div hidden>Hidden A</div>"
            "<div style='display:none'>Hidden B</div>"
            "<div aria-hidden='true'>Hidden C</div>"
            "</body>"
        )
        out = rendered(html, main=True).text
        assert "Hidden" not in out
        assert "Hidden A" in rendered(html, main=False).text

    def test_mediawiki_chrome_classes(self):
        html = (
            "<body><main><h2>History<span class='mw-editsection'>[edit]</span></h2>"
            f"{ARTICLE}<div class='navbox'>Huge link grid</div></main></body>"
        )
        out = rendered(html, main=True).text
        assert "[edit]" not in out and "link grid" not in out
        assert "## History" in out

    def test_falls_back_to_whole_page_when_main_would_be_empty(self):
        # Content wrongly marked as a sidebar: never return almost nothing.
        html = f"<body><aside>{ARTICLE}</aside></body>"
        r = rendered(html, main=True)
        assert "article body" in r.text
        assert r.main_fallback is True
        assert r.scope == "page"

    def test_link_lists_that_are_content_are_kept(self):
        # A front page of links (Hacker News) has no landmarks: nothing is
        # judged by link density, so it all stays.
        rows = "".join(
            f"<tr><td>{i}.</td><td><a href='/s{i}'>Story {i}</a></td></tr>"
            for i in range(30)
        )
        out = rendered(f"<body><table>{rows}</table></body>", main=True).text
        assert "Story 0" in out and "Story 29" in out


class TestSelection:
    def test_selection_renders_each_match_as_markdown(self):
        from bs4 import BeautifulSoup

        from attachments._processors._html_md import render_selection

        soup = BeautifulSoup(
            "<h2>A</h2><p>x</p><h2>B <a href='/b'>link</a></h2>", "lxml"
        )
        out = render_selection(soup.select("h2"), links=True, base_url="https://s.org/")
        assert out.text == "## A\n\n## B [link](https://s.org/b)"

    def test_title_can_be_selected(self):
        from bs4 import BeautifulSoup

        from attachments._processors._html_md import render_selection

        soup = BeautifulSoup("<head><title>The  Title</title></head><p>x</p>", "lxml")
        assert render_selection(soup.select("title")).text == "The Title"
