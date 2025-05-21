"""
Scan ATTACHMENTS_PLUGIN_PATH for *.py files & packages, import them,
and rely on their top-level `REGISTRY.register(...)` calls.
"""

import os, sys, pathlib
from .utils import try_initialize_plugin_module

ENV_VAR = "ATTACHMENTS_PLUGIN_PATH"

def load_external_plugins() -> None:
    paths_str = os.getenv(ENV_VAR, "")
    if not paths_str:
        return

    original_sys_path = list(sys.path)

    for raw_path in paths_str.split(":"):
        p = pathlib.Path(raw_path).expanduser().resolve()
        if not p.exists():
            continue

        # 1️⃣  Single .py files  -------------------------------------
        if p.is_file() and p.suffix == ".py":
            # For single files, Python needs the *directory* in sys.path
            # and then we import by module name (filename without .py)
            dir_path_str = str(p.parent)
            module_name = p.stem
            if dir_path_str not in sys.path:
                sys.path.insert(0, dir_path_str)
            
            try_initialize_plugin_module(module_name, is_external=True)
            
            # Clean up sys.path immediately if we added it
            if dir_path_str in sys.path and dir_path_str not in original_sys_path:
                sys.path.remove(dir_path_str)
            continue

        # 2️⃣  Package dirs or plain dirs with many .py  -------------
        if p.is_dir():
            # For directories (potentially packages or collections of .py files),
            # add the directory itself to sys.path to allow direct import of modules within.
            # If it's a package, its __init__.py will be found.
            # If it's a dir of modules, each .py will be found.
            dir_path_str = str(p)
            if dir_path_str not in sys.path:
                 sys.path.insert(0, dir_path_str)

            for py_file in p.rglob("*.py"):
                # Skip __init__.py itself (if p is a package, it's handled implicitly by importing the package name)
                # or other dunder files. We are looking for plugin modules.
                if py_file.name.startswith("__"):
                    continue
                
                # Construct module name relative to the directory `p` we added to sys.path
                # e.g. if p = /abs/path/to/plugins and py_file = /abs/path/to/plugins/subdir/mod.py
                # then module_name_to_import should be subdir.mod
                relative_path = py_file.relative_to(p)
                module_name_to_import = '.'.join(relative_path.with_suffix("").parts)
                
                try_initialize_plugin_module(module_name_to_import, is_external=True)

            # Clean up sys.path if we added this directory
            if dir_path_str in sys.path and dir_path_str not in original_sys_path:
                sys.path.remove(dir_path_str)

    # Restore original sys.path just in case, though targeted removals should handle it.
    sys.path = original_sys_path
