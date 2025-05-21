import importlib, warnings


def try_initialize_plugin_module(module_name: str, is_external: bool = False):
    """Import *module_name*, swallowing ImportError with a friendly warning.

    All dependency gating is now handled inside plugin modules via the
    @requires / @register_plugin decorators.  This helper merely acts as a
    thin wrapper so that core discovery code doesn't crash the whole app if
    one plugin hard-fails to import for some unexpected reason.
    """
    prefix = "external " if is_external else "built-in "
    try:
        importlib.import_module(module_name)
    except ImportError as err:
        warnings.warn(
            f"Failed to import {prefix}plugin module '{module_name}': {err}",
            RuntimeWarning,
        )
    except Exception as err:
        warnings.warn(
            f"Unexpected error while importing {prefix}plugin module '{module_name}': {err}",
            RuntimeWarning,
        ) 