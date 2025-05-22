import importlib, warnings
import sys # Added for print to stderr


def try_initialize_plugin_module(module_name: str, is_external: bool = False, source: str | None = None):
    """Import *module_name*, swallowing ImportError with a friendly warning.

    All dependency gating is now handled inside plugin modules via the
    @requires / @register_plugin decorators.  This helper merely acts as a
    thin wrapper so that core discovery code doesn't crash the whole app if
    one plugin hard-fails to import for some unexpected reason.
    """
    prefix = "external " if is_external else "built-in "
    display_source = f" (from {source})" if source else ""
    try:
        importlib.import_module(module_name)
    except ImportError as err:
        # Use print to stderr for more immediate visibility than warnings for critical load failures.
        print(
            f"[attachments] Info: Failed to import {prefix}plugin module '{module_name}'{display_source}: {err}",
            file=sys.stderr,
        )
    except Exception as err:
        print(
            f"[attachments] Warning: Unexpected error while importing {prefix}plugin module '{module_name}'{display_source}: {err}",
            file=sys.stderr,
        ) 

def is_url(path: str) -> bool:
    return path.startswith(("http://", "https://"))