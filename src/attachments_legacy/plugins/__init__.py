import importlib, pkgutil

for m in pkgutil.walk_packages(__path__, prefix=__name__ + "."):
    importlib.import_module(m.name)