"""
Tests for the source registry - custom handler registration & dispatch.

=============================================================================
TEST GUIDELINES FOR THE SOURCE REGISTRY
=============================================================================

GOOD tests for the registry:
    - Test custom handler registration (function and decorator forms)
    - Test @source registering multiple prefixes
    - Always clean registered prefixes out of extra_unpack_handlers

BAD tests for the registry:
    - Leaving handlers registered (leaks into other tests)
    - Testing built-in sources here (use test_local/test_archives/...)

=============================================================================
"""

from __future__ import annotations

from attachments._sources import (
    extra_unpack_handlers,
    register_unpack_handler,
    source,
    unpack,
)


class TestRegisterUnpackHandler:
    """Tests for custom handler registration."""

    def test_register_function(self):
        def my_handler(url: str) -> list[tuple[str, bytes]]:
            return [("test.txt", b"from handler")]

        register_unpack_handler("myproto://", my_handler)

        try:
            assert "myproto://" in extra_unpack_handlers
            result = unpack("myproto://something")
            assert result == [("test.txt", b"from handler")]
        finally:
            # Cleanup
            del extra_unpack_handlers["myproto://"]

    def test_register_decorator(self):
        @register_unpack_handler("decorated://")
        def decorated_handler(url: str) -> list[tuple[str, bytes]]:
            return [("decorated.txt", b"decorated")]

        try:
            assert "decorated://" in extra_unpack_handlers
        finally:
            del extra_unpack_handlers["decorated://"]


class TestSourceDecorator:
    """Tests for @source decorator (multiple prefixes)."""

    def test_source_multiple_prefixes(self):
        @source("multi1://", "multi2://")
        def multi_handler(url: str) -> list[tuple[str, bytes]]:
            return [("multi.txt", b"multi")]

        try:
            assert "multi1://" in extra_unpack_handlers
            assert "multi2://" in extra_unpack_handlers
        finally:
            del extra_unpack_handlers["multi1://"]
            del extra_unpack_handlers["multi2://"]
