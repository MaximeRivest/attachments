"""Attachments - the Python funnel for LLM context

Turn any file into model-ready text + images, in one line."""

from .core import (
    Attachment, AttachmentCollection, attach, A, Pipeline, SmartVerbNamespace, 
    _loaders, _modifiers, _presenters, _adapters, _refiners, 
    loader, modifier, presenter, adapter, refiner
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
split = SmartVerbNamespace(_modifiers)  # Split functions are also modifiers

__version__ = "0.5.0"

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
    
    # Module imports
    'loaders',
    'presenters',
    'pipelines'
]
