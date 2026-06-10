"""
Tests for declared option schemas and resolution (attachments.options).

=============================================================================
TEST GUIDELINES FOR OPTIONS
=============================================================================

GOOD tests:
    - Resolver behavior: alias matching, param hidden-alias, exact
      warning text ("did you mean"), coercion per type, drop-on-failure
    - Registry semantics: register/get/reset, decorator options=
    - Schema export shape (dsl_schema / options)

BAD tests:
    - Testing the DSL parser (test_dsl.py / test_dsl_vectors.py)
    - End-to-end att() behavior (test_core.py)

=============================================================================
"""

from __future__ import annotations

import pytest

from attachments._options import (
    Option,
    dsl_schema,
    get_options,
    option_schemas,
    options,
    register_options,
    reset_options,
    resolve_options,
    source_option_schemas,
)
from attachments._processors import processor, processors, reset_processors

XLSX_SCHEMA = (
    Option("sheet", "str_or_int"),
    Option("rows", "int", aliases=("max_rows",), param="max_rows"),
)
PDF_SCHEMA = (
    Option("pages", "pages", aliases=("page",), example="pages: 1-4"),
    Option("password", "str", aliases=("pw",)),
    Option("images", "bool_or_auto", aliases=("render",), param="render_images"),
    Option("dpi", "int", param="images_dpi"),
)


class TestOptionDataclass:
    def test_frozen(self):
        opt = Option("dpi", "int")
        with pytest.raises(AttributeError):
            opt.name = "other"  # type: ignore[misc]

    def test_invalid_type_rejected(self):
        with pytest.raises(ValueError, match="invalid type 'color'"):
            Option("dpi", "color")


class TestRegistry:
    def test_builtin_schemas_present(self):
        assert any(o.name == "pages" for o in get_options(".pdf"))
        assert any(o.name == "sheet" for o in get_options(".xlsx"))
        assert any(o.name == "ref" for o in get_options("github://"))
        assert get_options("__text__") == ()

    def test_key_normalization(self):
        assert get_options("PDF") == get_options(".pdf")

    def test_unknown_key_returns_empty(self):
        assert get_options(".unknown-ext") == ()

    def test_register_and_reset(self):
        register_options(".custom", (Option("depth", "int"),))
        assert get_options(".custom")[0].name == "depth"

        register_options("custom://", (Option("token", "str"),))
        assert "custom://" in source_option_schemas

        reset_options()
        assert get_options(".custom") == ()
        assert "custom://" not in source_option_schemas
        # Built-ins survive the reset
        assert any(o.name == "pages" for o in get_options(".pdf"))
        assert any(o.name == "ref" for o in get_options("github://"))

    def test_reset_processors_also_resets_schemas(self):
        register_options(".custom", (Option("depth", "int"),))
        reset_processors()
        assert ".custom" not in option_schemas

    def test_processor_decorator_with_options(self):
        @processor(".deco", options=(Option("level", "int"),))
        def _deco(data: bytes, **_opts) -> dict:
            return {"text": ""}

        assert ".deco" in processors
        assert get_options(".deco")[0].name == "level"
        reset_processors()


class TestResolveUnknownKeys:
    def test_did_you_mean_exact_text(self):
        kwargs, warnings = resolve_options(XLSX_SCHEMA, {"sheets": 0}, context=".xlsx")
        assert kwargs == {}
        assert warnings == ["Unknown option 'sheets' for .xlsx — did you mean 'sheet'?"]

    def test_no_close_match_omits_suggestion(self):
        kwargs, warnings = resolve_options(XLSX_SCHEMA, {"zzz_qqq": 1}, context=".xlsx")
        assert kwargs == {}
        assert warnings == ["Unknown option 'zzz_qqq' for .xlsx"]

    def test_unknown_key_is_dropped_but_known_keys_resolve(self):
        kwargs, warnings = resolve_options(
            XLSX_SCHEMA, {"sheet": "Sales", "bogus_thing": 1}, context=".xlsx"
        )
        assert kwargs == {"sheet": "Sales"}
        assert len(warnings) == 1

    def test_empty_schema_warns_for_every_key(self):
        kwargs, warnings = resolve_options((), {"pages": (1, 4)}, context=".txt")
        assert kwargs == {}
        assert warnings == ["Unknown option 'pages' for .txt"]


class TestResolveMatching:
    def test_alias_match(self):
        kwargs, warnings = resolve_options(PDF_SCHEMA, {"pw": "secret"}, context=".pdf")
        assert kwargs == {"password": "secret"}
        assert warnings == []

    def test_param_acts_as_hidden_alias(self):
        kwargs, warnings = resolve_options(
            XLSX_SCHEMA, {"max_rows": 10}, context=".xlsx"
        )
        assert kwargs == {"max_rows": 10}
        assert warnings == []

        kwargs, _ = resolve_options(PDF_SCHEMA, {"render_images": True}, context=".pdf")
        assert kwargs == {"render_images": True}

    def test_param_renames_kwarg(self):
        kwargs, _ = resolve_options(PDF_SCHEMA, {"dpi": 300}, context=".pdf")
        assert kwargs == {"images_dpi": 300}

    def test_later_raw_key_wins_on_collision(self):
        """Merging kwargs after DSL options makes kwargs override the DSL."""
        raw = {"page": 1, "pages": "2-3"}  # insertion order matters
        kwargs, _ = resolve_options(PDF_SCHEMA, raw, context=".pdf")
        assert kwargs == {"page_start": 1, "page_end": 3}


class TestPagesCoercion:
    def test_range_tuple(self):
        kwargs, _ = resolve_options(PDF_SCHEMA, {"pages": (1, 4)}, context=".pdf")
        assert kwargs == {"page_start": 0, "page_end": 4}

    def test_range_list(self):
        """JSON wire transport turns tuples into lists; both resolve."""
        kwargs, _ = resolve_options(PDF_SCHEMA, {"pages": [2, 5]}, context=".pdf")
        assert kwargs == {"page_start": 1, "page_end": 5}

    def test_range_string(self):
        kwargs, _ = resolve_options(PDF_SCHEMA, {"pages": "1-4"}, context=".pdf")
        assert kwargs == {"page_start": 0, "page_end": 4}

    def test_single_int(self):
        kwargs, _ = resolve_options(PDF_SCHEMA, {"pages": 3}, context=".pdf")
        assert kwargs == {"page_start": 2, "page_end": 3}

    def test_single_int_string(self):
        kwargs, _ = resolve_options(PDF_SCHEMA, {"page": "3"}, context=".pdf")
        assert kwargs == {"page_start": 2, "page_end": 3}

    def test_page_list_string_not_supported_yet(self):
        kwargs, warnings = resolve_options(
            PDF_SCHEMA, {"pages": "1,3-5"}, context=".pdf"
        )
        assert kwargs == {}
        assert len(warnings) == 1
        assert "not supported yet" in warnings[0]

    def test_zero_page_rejected(self):
        kwargs, warnings = resolve_options(PDF_SCHEMA, {"pages": 0}, context=".pdf")
        assert kwargs == {}
        assert len(warnings) == 1
        assert "1-based" in warnings[0]


class TestTypeCoercions:
    def test_bool_or_auto(self):
        for raw, expected in [
            (True, True),
            (False, False),
            ("auto", "auto"),
            ("Always", "always"),
            ("yes", True),
            ("off", False),
        ]:
            kwargs, warnings = resolve_options(
                PDF_SCHEMA, {"images": raw}, context=".pdf"
            )
            assert kwargs == {"render_images": expected}, raw
            assert warnings == []

    def test_bool_or_auto_failure(self):
        kwargs, warnings = resolve_options(
            PDF_SCHEMA, {"images": "sometimes"}, context=".pdf"
        )
        assert kwargs == {}
        assert warnings == [
            "Invalid value for option 'images' on .pdf: expected a boolean, "
            "'auto', or 'always', got 'sometimes'"
        ]

    def test_int_from_string(self):
        kwargs, _ = resolve_options(PDF_SCHEMA, {"dpi": "300"}, context=".pdf")
        assert kwargs == {"images_dpi": 300}

    def test_int_failure_drops_with_warning(self):
        kwargs, warnings = resolve_options(PDF_SCHEMA, {"dpi": "abc"}, context=".pdf")
        assert kwargs == {}
        assert warnings == [
            "Invalid value for option 'dpi' on .pdf: expected an integer, got 'abc'"
        ]

    def test_str_or_int_keeps_both(self):
        kwargs, _ = resolve_options(XLSX_SCHEMA, {"sheet": 0}, context=".xlsx")
        assert kwargs == {"sheet": 0}
        kwargs, _ = resolve_options(XLSX_SCHEMA, {"sheet": "Sales"}, context=".xlsx")
        assert kwargs == {"sheet": "Sales"}

    def test_str_coerces_numbers(self):
        kwargs, _ = resolve_options(PDF_SCHEMA, {"password": 1234}, context=".pdf")
        assert kwargs == {"password": "1234"}

    def test_coercion_failure_message_includes_example(self):
        _, warnings = resolve_options(PDF_SCHEMA, {"pages": True}, context=".pdf")
        assert warnings[0].endswith("(e.g. [pages: 1-4])")


class TestSchemaExport:
    def test_dsl_schema_shape(self):
        schema = dsl_schema()
        assert schema["version"] == 1
        assert set(schema) == {"version", "processors", "sources"}
        pdf = schema["processors"][".pdf"]
        assert [o["name"] for o in pdf] == [
            "pages",
            "password",
            "images",
            "dpi",
            "ocr",
            "max_pages",
        ]
        entry = next(o for o in pdf if o["name"] == "pages")
        assert set(entry) == {
            "name",
            "type",
            "aliases",
            "param",
            "default",
            "help",
            "example",
        }
        assert entry["aliases"] == ["page"]
        assert [o["name"] for o in schema["sources"]["github://"]] == ["ref"]

    def test_dsl_schema_is_json_serializable(self):
        import json

        json.dumps(dsl_schema())

    def test_options_single_key(self):
        names = [o["name"] for o in options(".xlsx")]
        assert names == ["sheet", "rows"]
        assert options(".unknown-ext") == []

    def test_options_all(self):
        everything = options()
        assert everything == dsl_schema()

    def test_att_options_attribute(self):
        from attachments import att

        assert att.options is options


class TestOptionsRepr:
    """options() returns repr-friendly subclasses carrying the SAME data."""

    def test_single_key_is_list_with_table_repr(self):
        result = options(".xlsx")
        assert isinstance(result, list)
        rendered = repr(result)
        lines = rendered.splitlines()
        assert lines[0].startswith("Option")
        for column in ("Type", "Aliases", "Default", "Example", "Description"):
            assert column in lines[0]
        assert any(line.startswith("sheet") for line in lines)
        assert any(line.startswith("rows") and "max_rows" in line for line in lines)
        # Wrapped sensibly: nothing runs past ~88 columns.
        assert all(len(line) <= 88 for line in lines)

    def test_unknown_key_repr(self):
        assert repr(options(".unknown-ext")) == "(no options declared)"

    def test_catalog_is_dict_with_table_repr(self):
        catalog = options()
        assert isinstance(catalog, dict)
        rendered = repr(catalog)
        assert rendered.startswith("DSL options (schema version 1)")
        assert "Processors" in rendered
        assert "Sources" in rendered
        assert ".pdf" in rendered
        assert "github://" in rendered
        assert "No options:" in rendered  # extension groups with no options

    def test_repr_subclasses_stay_json_serializable(self):
        import json

        assert json.loads(json.dumps(options(".pdf"))) == [
            dict(o) for o in options(".pdf")
        ]
        assert json.loads(json.dumps(options())) == dsl_schema()

    def test_dsl_schema_stays_plain(self):
        """dsl_schema() feeds asset generation — it must stay a plain dict."""
        schema = dsl_schema()
        assert type(schema) is dict
        assert all(type(v) is list for v in schema["processors"].values())
