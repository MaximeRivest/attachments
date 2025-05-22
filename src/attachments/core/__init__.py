"""Core components for the Attachments library."""

from .attachment import Attachment, MultiAttachment
from .namespaces import load, modify, present, adapt
from .decorators import loader, modifier, presenter, adapter

__all__ = [
    'Attachment', 
    'MultiAttachment',
    'load', 
    'modify', 
    'present', 
    'adapt',
    'loader',
    'modifier', 
    'presenter',
    'adapter'
] 