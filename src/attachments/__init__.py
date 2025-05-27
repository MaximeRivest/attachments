"""Attachments - the Python funnel for LLM context

Turn any file into model-ready text + images, in one line."""

from .core import (
    Attachment, AttachmentCollection, attach, A, Pipeline, SmartVerbNamespace, 
    _loaders, _modifiers, _presenters, _adapters, _refiners, _splitters,
    loader, modifier, presenter, adapter, refiner, splitter
)
from .highest_level_api import process as simple, Attachments

# Import all loaders and presenters to register them
from . import loaders
from . import presenters

# Import pipelines to register processors
from . import pipelines
from .pipelines import processors

# Import other modules to register their functions
from . import refine as _refine_module
from . import modify as _modify_module
from . import adapt as _adapt_module
from . import split as _split_module

# Create the namespace instances after functions are registered
load = SmartVerbNamespace(_loaders)
modify = SmartVerbNamespace(_modifiers)
present = SmartVerbNamespace(_presenters)
adapt = SmartVerbNamespace(_adapters)
refine = SmartVerbNamespace(_refiners)
split = SmartVerbNamespace(_splitters)  # Split functions now have their own registry

# Dynamic version reading from pyproject.toml
def _get_version():
    """Read version from pyproject.toml"""
    import os
    from pathlib import Path
    
    # Try to find pyproject.toml starting from this file's directory
    current_dir = Path(__file__).parent
    for _ in range(3):  # Look up to 3 levels up
        pyproject_path = current_dir / "pyproject.toml"
        if pyproject_path.exists():
            try:
                content = pyproject_path.read_text(encoding='utf-8')
                for line in content.split('\n'):
                    if line.strip().startswith('version = '):
                        # Extract version from line like: version = "0.6.0"
                        version = line.split('=', 1)[1].strip().strip('"').strip("'")
                        return version
            except Exception:
                pass
        current_dir = current_dir.parent
    
    # Fallback: try importlib.metadata if package is installed
    try:
        from importlib.metadata import version
        return version("attachments")
    except ImportError:
        try:
            from importlib_metadata import version
            return version("attachments")
        except ImportError:
            pass
    
    return "unknown"

__version__ = _get_version()

__all__ = [
    # Core classes and functions
    'Attachment',
    'AttachmentCollection', 
    'attach',
    'A',
    'Pipeline',
    
    # High-level API
    'Attachments',
    'simple',
    
    # Namespace objects
    'load',
    'modify', 
    'present',
    'adapt',
    'refine',
    'split',
    
    # Processors
    'processors',
    
    # Decorator functions
    'loader',
    'modifier',
    'presenter', 
    'adapter',
    'refiner',
    'splitter',
    
    # Module imports
    'loaders',
    'presenters',
    'pipelines'
]
