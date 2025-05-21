from .core import Attachment, Attachments
from .discovery import load_external_plugins
from .registry import REGISTRY
from .utils import try_initialize_plugin_module

# 1. Load *user* plugins first so they can override priorities if they wish.
load_external_plugins()

# 2. Now load built-ins
import pkgutil
for m in pkgutil.walk_packages(__path__, prefix=__name__ + '.plugins.'):
    try_initialize_plugin_module(m.name)


# ---- after built-in & external plugin discovery -----------------
def _mk_api_method(name: str):
    def _api(self, prompt: str = ""):
        return self.format_for(name, prompt)
    _api.__name__ = f"as_{name}"
    _api.__doc__  = f"Shortcut for Attachment.format_for('{name}', ...)."
    return _api

for d_cls in REGISTRY.all("deliverer"):
    name = d_cls.name.lower()
    setattr(Attachment, f"as_{name}", _mk_api_method(name))
    # Patch Attachments with to_{name} methods as well
    def _mk_api_method_attachments(name):
        def _api(self, prompt: str = ""):
            return self.format_for(name, prompt)
        _api.__name__ = f"to_{name}"
        _api.__doc__ = f"Shortcut for Attachments.format_for('{name}', ...)."
        return _api
    setattr(Attachments, f"to_{name}", _mk_api_method_attachments(name))

__all__ = ["Attachment", "Attachments"]
