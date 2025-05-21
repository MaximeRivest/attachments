import attachments
import pytest
import importlib
import os
from attachments.registry import REGISTRY
from attachments.core import Attachment, Attachments
import pandas as pd
from PIL import Image
from unittest.mock import patch
import sys

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

    # New test cases
    assert Attachment._split("file.txt[cmd]") == ("file.txt", "cmd")
    assert Attachment._split("file[name].txt[cmd]") == ("file[name].txt", "cmd")
    assert Attachment._split("url/to/file?p1=[v1]&p2=[v2][cmd]") == ("url/to/file?p1=[v1]&p2=[v2]", "cmd")
    assert Attachment._split("url/to/file?p1=[v1]&p2=[v2]") == ("url/to/file?p1=[v1]&p2=[v2]", "")
    assert Attachment._split("[cmd]") == ("[cmd]", "") # Not a path + cmd
    assert Attachment._split("file[]") == ("file[]", "")     # Empty cmd part means no cmd
    assert Attachment._split("file[ ]") == ("file[ ]", "")   # Empty cmd part means no cmd
    assert Attachment._split("file[c]") == ("file", "c")
    assert Attachment._split("file[[inner_cmd]]") == ("file[", "inner_cmd]")
    assert Attachment._split("path/to/some[file].txt") == ("path/to/some[file].txt", "") # No cmd
    assert Attachment._split("another_path_with_no_cmd[") == ("another_path_with_no_cmd[", "") # Incomplete
    assert Attachment._split("path_ends_with_bracket]") == ("path_ends_with_bracket]", "")

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

def test_rotate_transform(sample_img):
    """Test the Rotate transform with valid and invalid arguments."""
    from src.attachments.plugins.transforms.rotate_transform import Rotate
    from PIL import Image

    att = Attachment(sample_img)
    img_obj = att.obj # Original image object
    assert isinstance(img_obj, Image.Image)
    original_size = img_obj.size

    # Test with valid rotation
    transformer = Rotate()
    rotated_img = transformer.apply(img_obj, "90")
    assert isinstance(rotated_img, Image.Image)
    assert rotated_img.size[0] == original_size[1]
    assert rotated_img.size[1] == original_size[0]

    # Test with no argument (should be 0 degrees, no change)
    rotated_img_no_arg = transformer.apply(img_obj, None)
    assert rotated_img_no_arg.size == original_size

    # Test with empty string argument (should be 0 degrees)
    rotated_img_empty_arg = transformer.apply(img_obj, "")
    assert rotated_img_empty_arg.size == original_size

    # Test with non-Image object (should return object unchanged)
    not_an_image = "this is a string"
    assert transformer.apply(not_an_image, "90") == not_an_image

    # Test with invalid argument (e.g., non-integer string)
    # The current implementation of Rotate.apply implicitly handles this by int(args or 0)
    # If args is "abc", int("abc") raises ValueError. We should test this.
    with pytest.raises(ValueError, match="invalid literal for int()"):
        transformer.apply(img_obj, "not_a_number")

def test_rotate_transform_no_pillow(sample_img):
    """Test Rotate transform fallback when Pillow is missing."""
    import importlib, sys
    
    # First load the image normally to get a reference
    from attachments.core import Attachment
    original_att = Attachment(sample_img)
    original_obj = original_att.obj  # Keep reference to the original PIL Image object
    
    # Now patch out PIL
    with patch.dict(sys.modules, {'PIL': None, 'PIL.Image': None}):
        # Reload the rotate transform module to recognize the missing PIL
        import src.attachments.plugins.transforms.rotate_transform as rt
        importlib.reload(rt)
        
        # When PIL is missing, the Rotate class is replaced with a MissingDependencyProxy
        # that will raise ModuleNotFoundError when instantiated
        assert hasattr(rt.Rotate, '_attachments_disabled')
        assert rt.Rotate._attachments_disabled == True
        # It should also be marked with a disabled reason that mentions PIL
        assert hasattr(rt.Rotate, '_attachments_disabled_reason')
        assert "PIL" in rt.Rotate._attachments_disabled_reason
        
        # Instead of trying to instantiate it, which would raise ModuleNotFoundError,
        # let's verify the class is the proxy class by checking it has this attribute
        assert hasattr(rt.Rotate, '_attachments_original_plugin_name')
        assert rt.Rotate._attachments_original_plugin_name == "Rotate"
    
    # Reload to restore normal state for other tests
    importlib.reload(rt)
    import attachments
    importlib.reload(attachments)
    import src.attachments.plugins.transforms.rotate_transform
    from attachments.core import Attachment, Attachments
    from attachments.registry import REGISTRY

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

def test_missing_dep_guard():
    from attachments.plugin_api import register_plugin, requires
    
    @register_plugin("renderer_text", priority=10)
    @requires("nonexistent_pkg_xyz", pip_names={"nonexistent_pkg_xyz": "fancy-nonexistent-package"})
    class MissingDepRenderer:
        content_type = "text"
        _sample_obj = "test"
        _attachments_disabled = False

        def __init__(self):
            pass

        def match(self, obj): 
            return False
        def render(self, obj, meta): 
            return ""

    assert not any(issubclass(r, MissingDepRenderer) or r.__name__.startswith("MissingDepRenderer") for r in REGISTRY.all("renderer_text"))

    with pytest.raises(ModuleNotFoundError) as excinfo:
        MissingDepRenderer()
    
    assert "Module 'nonexistent_pkg_xyz' not found" in str(excinfo.value)
    assert "Try `pip install fancy-nonexistent-package`" in str(excinfo.value)
    assert "Plugin 'MissingDepRenderer' is disabled" in str(excinfo.value)

    all_renderers = REGISTRY.all("renderer_text")
    original_class_present = any(r.__name__ == "MissingDepRenderer" and not hasattr(r, "_attachments_disabled_reason") for r in all_renderers)
    assert not original_class_present

def test_external_plugin_path(monkeypatch, tmp_path):
    # Create a dummy plugin in a temp dir
    plugin_code = '''from attachments.plugin_api import register_plugin\nfrom attachments.core import Loader\n@register_plugin("loader", priority=99)\nclass DummyLoader(Loader):\n    @classmethod\n    def match(cls, path): return path.endswith(".dummy")\n    def load(self, path): return "dummy"\n'''
    plugin_dir = tmp_path / "myplugins"
    plugin_dir.mkdir()
    (plugin_dir / "dummy_plugin.py").write_text(plugin_code)
    monkeypatch.setenv("ATTACHMENTS_PLUGIN_PATH", str(plugin_dir))
    
    # Store original registry content types
    original_registry_state = {k: list(REGISTRY.all(k)) for k in REGISTRY.kinds()}

    import attachments # Initial import or ensure it's imported
    importlib.reload(attachments) # This will discover the dummy plugin
    
    found = any(c.__name__ == "DummyLoader" for c in attachments.REGISTRY.all("loader"))
    assert found

    # Clean up: unregister DummyLoader so other tests not affected
    for cls in attachments.REGISTRY.all("loader"):
        if cls.__name__ == "DummyLoader":
            attachments.REGISTRY.unregister("loader", cls)
            break
    importlib.reload(attachments)
    # Re-import all built-in plugins to repopulate the registry
    import src.attachments.plugins.loaders.csv_loader
    import src.attachments.plugins.loaders.image_loader
    import src.attachments.plugins.loaders.pdf_loader
    import src.attachments.plugins.loaders.plain_text_loader
    import src.attachments.plugins.renderers.csv_brief_text_renderer
    import src.attachments.plugins.renderers.csv_full_text_renderer
    import src.attachments.plugins.renderers.image_b64_renderer
    import src.attachments.plugins.renderers.image_ocr_text_renderer
    import src.attachments.plugins.renderers.string_text_renderer
    import src.attachments.plugins.transforms.csv_summary_transform
    import src.attachments.plugins.transforms.rotate_transform

def test_attachments_aggregation(sample_csv):
    a = Attachments(sample_csv, sample_csv)
    assert a.text.count("|") > 2

def test_every_builtin_plugin_imports():
    from attachments import REGISTRY
    kinds = {"loader", "renderer_text", "renderer_image", "transform", "deliverer"}
    for k in kinds:
        assert any("attachments.plugins." in c.__module__ for c in REGISTRY.all(k)), f"No builtin plugin found for kind: {k}" 