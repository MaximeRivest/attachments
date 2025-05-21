import attachments
import pytest
import importlib
import os
from attachments.registry import REGISTRY
from attachments.core import Attachment, Attachments
import pandas as pd

# Dummy high-priority renderer for prioritisation test
def test_registry_prioritisation(monkeypatch):
    class HighPrioRenderer:
        content_type = 'text'
        def match(self, obj): return True
        def render(self, obj, meta): return "hi"
    with REGISTRY.temp_registration("renderer_text", HighPrioRenderer, 999):
        assert REGISTRY.first("renderer_text", lambda R: True) is HighPrioRenderer

def test_dsl_split():
    assert Attachment._split("foo.pdf[rotate:90]") == ("foo.pdf", "rotate:90")
    assert Attachment._split("bar.csv") == ("bar.csv", "")

def test_loader_discovery(sample_csv):
    att = Attachment(sample_csv)
    assert isinstance(att.obj, pd.DataFrame)

def test_transform_chain(sample_csv):
    class AddX:
        name = "addx"
        def apply(self, obj, arg): return obj + "X"
    with REGISTRY.temp_registration("transform", AddX, 100):
        att = Attachment(sample_csv)
        att.obj = "foo"  # bypass loader
        out = att._apply_transforms(att.obj, "addx,addx")
        assert out == "fooXX"

def test_renderer_fallback(tmp_path):
    # Create a dummy unsupported file
    dummy_path = tmp_path / "sample.xyz_unsupported"
    dummy_content = "dummy content for xyz_unsupported file"
    dummy_path.write_text(dummy_content)

    # With PlainTextLoader as a fallback, this should now succeed
    att = Attachment(str(dummy_path))

    # The PlainTextLoader should have loaded the content.
    # If no specific renderer matches a plain string, att.text should be the string itself.
    assert att.text == dummy_content

    # To test renderer fallback specifically (i.e., loader worked, but no renderer):
    # We would need a scenario where an object is loaded that has no matching renderer.
    # For example, if PlainTextLoader returned a custom object instead of a string,
    # and no renderer was registered for that custom object.
    # class CustomObject:
    #     def __str__(self): return "custom object string"
    # class LoaderReturningCustomObject:
    #     def match(self, path): return path.endswith(".custom")
    #     def load(self, path): return CustomObject()
    # with REGISTRY.temp_registration("loader", LoaderReturningCustomObject, 10):
    #     custom_file = tmp_path / "test.custom"
    #     custom_file.write_text("custom data")
    #     att_custom = Attachment(str(custom_file))
    #     assert att_custom.text is None # Assuming no renderer for CustomObject for text

def test_deliverer_packaging(sample_img):
    class DummyDeliverer:
        name = "dummy"
        def package(self, text, images, audio, prompt=None):
            return [{"type": "input_image"}]
    with REGISTRY.temp_registration("deliverer", DummyDeliverer, 100):
        att = Attachment(sample_img)
        pkg = att.format_for("dummy")
        assert {"type": "input_image"} in pkg

def test_missing_dep_guard(caplog):
    from attachments.plugin_api import register_plugin, requires
    @register_plugin("renderer_text", priority=10)
    @requires("nonexistent_pkg_xyz")
    class MissingDepRenderer:
        content_type = "text"
        def match(self, obj): return False
        def render(self, obj, meta): return ""
    # Should not be in registry
    assert MissingDepRenderer not in REGISTRY.all("renderer_text")
    assert any("nonexistent_pkg_xyz" in r.message for r in caplog.records)
    REGISTRY.unregister("renderer_text", MissingDepRenderer)

def test_external_plugin_path(monkeypatch, tmp_path):
    # Create a dummy plugin in a temp dir
    plugin_code = '''from attachments.plugin_api import register_plugin\nfrom attachments.core import Loader\n@register_plugin("loader", priority=99)\nclass DummyLoader(Loader):\n    def match(self, path): return path.endswith(".dummy")\n    def load(self, path): return "dummy"\n'''
    plugin_dir = tmp_path / "myplugins"
    plugin_dir.mkdir()
    (plugin_dir / "dummy_plugin.py").write_text(plugin_code)
    monkeypatch.setenv("ATTACHMENTS_PLUGIN_PATH", str(plugin_dir))
    import attachments
    importlib.reload(attachments)
    found = any(c.__name__ == "DummyLoader" for c in attachments.REGISTRY.all("loader"))
    assert found

def test_attachments_aggregation(sample_csv):
    a = Attachments(sample_csv, sample_csv)
    assert a.text.count("|") > 2

def test_every_builtin_plugin_imports():
    from attachments import REGISTRY
    kinds = {"loader", "renderer_text", "renderer_image", "transform", "deliverer"}
    for k in kinds:
        assert any("attachments.plugins." in c.__module__ for c in REGISTRY.all(k)), f"No builtin plugin found for kind: {k}" 