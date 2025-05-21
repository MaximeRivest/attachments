import importlib, attachments
import pytest
from attachments.registry import REGISTRY

# Names of abstract base classes to skip
def is_real_plugin(cls):
    abc_names = {"Loader", "Renderer", "Transform", "Deliverer"}
    mod = getattr(cls, "__module__", "")
    name = getattr(cls, "__name__", "")
    # skip if from core module and is an ABC
    return not (mod.endswith("core") and name in abc_names)

@pytest.mark.contract
@pytest.mark.parametrize("cls",
    [c for k in REGISTRY.kinds() for c in REGISTRY.all(k) if is_real_plugin(c)])
def test_plugin_contract(cls, tmp_path):
    inst = cls()
    if hasattr(inst, "selftest"):
        inst.selftest(tmp_path) 