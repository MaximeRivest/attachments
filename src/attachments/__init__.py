from .core import Attachment, Attachments
from .core import _mk_api_method
from .discovery import load_external_plugins
from .registry import REGISTRY
from .utils import try_initialize_plugin_module
import os
import pkgutil
import logging

# Configure logging
logging.basicConfig(level=os.getenv("ATTACHMENTS_LOG", "WARNING"))
logger = logging.getLogger(__name__)

# 1. Load *user* plugins first so they can override priorities if they wish.
load_external_plugins()

# 2. Now load built-ins by explicitly walking known plugin subdirectories
#    This avoids trying to import __init__.py or other non-plugin modules directly under 'plugins'
plugin_subdirectories = ["loaders", "renderers", "transforms", "deliverers"]
plugin_base_path = os.path.join(os.path.dirname(__file__), "plugins")

for subdir_name in plugin_subdirectories:
    subdir_path = os.path.join(plugin_base_path, subdir_name)
    if os.path.isdir(subdir_path):
        # Construct the module prefix for this subdirectory
        module_prefix = f"{__name__}.plugins.{subdir_name}."
        for m in pkgutil.walk_packages([subdir_path], prefix=module_prefix):
            try_initialize_plugin_module(m.name)


# ---- after built-in & external plugin discovery -----------------

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

def diagnostics():
    """
    Return a dict with two keys:
      • "registry": plugins grouped by kind + disabled list
      • "env":      ATTACHMENTS_* environment variables
    """
    import os, pprint
    reg = {k: [c.__name__ for c in REGISTRY.all(k)] for k in REGISTRY.kinds()}
    disabled = [(k, c.__name__, r) for k, c, r in REGISTRY.disabled()]
    return {"registry": reg, "disabled": disabled,
            "env": {k: v for k, v in os.environ.items() if k.startswith("ATTACHMENTS")}}

__all__ = ["Attachment", "Attachments", "diagnostics"]
