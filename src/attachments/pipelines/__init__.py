"""
Pipeline Processor System
========================

Allows contributors to create complete file-to-LLM processors with automatic registration.
Supports both primary processors (for simple API) and named specialized processors.

Usage:
    @processor(match=lambda att: att.path.endswith('.pdf'))
    def pdf_to_llm(att):  # Primary processor - auto-registered
        return process_pdf(att)
    
    @processor(match=lambda att: att.path.endswith('.pdf'), name="academic_pdf")
    def academic_pdf_to_llm(att):  # Named processor - explicit access
        return process_academic_pdf(att)
"""

from typing import Callable, List, Optional, Dict, Any
from dataclasses import dataclass
from ..core import Attachment

@dataclass
class ProcessorInfo:
    """Information about a registered processor."""
    match_fn: Callable[[Attachment], bool]
    process_fn: Callable[[Attachment], Attachment]
    name: Optional[str] = None
    is_primary: bool = False
    description: str = ""

class ProcessorRegistry:
    """Registry for pipeline processors."""
    
    def __init__(self):
        self._processors: List[ProcessorInfo] = []
        self._primary_processors: Dict[str, ProcessorInfo] = {}  # file_pattern -> processor
        self._named_processors: Dict[str, ProcessorInfo] = {}    # name -> processor
    
    def register(self, match_fn: Callable, process_fn: Callable, 
                name: Optional[str] = None, description: str = ""):
        """Register a pipeline processor."""
        
        # Determine if this is a primary processor (no name = primary)
        is_primary = name is None
        
        proc_info = ProcessorInfo(
            match_fn=match_fn,
            process_fn=process_fn,
            name=name or process_fn.__name__,
            is_primary=is_primary,
            description=description or process_fn.__doc__ or ""
        )
        
        self._processors.append(proc_info)
        
        if is_primary:
            # Store as primary processor for this file type
            # Use function name as key for now - could be smarter
            file_key = process_fn.__name__.replace('_to_llm', '')
            self._primary_processors[file_key] = proc_info
        else:
            # Store as named processor
            self._named_processors[name] = proc_info
    
    def find_primary_processor(self, att: Attachment) -> Optional[ProcessorInfo]:
        """Find the primary processor for an attachment."""
        # Try primary processors first
        for proc_info in self._primary_processors.values():
            if proc_info.match_fn(att):
                return proc_info
        return None
    
    def find_named_processor(self, name: str) -> Optional[ProcessorInfo]:
        """Find a named processor."""
        return self._named_processors.get(name)
    
    def list_processors_for_file(self, att: Attachment) -> List[ProcessorInfo]:
        """List all processors that can handle this file."""
        matching = []
        for proc_info in self._processors:
            if proc_info.match_fn(att):
                matching.append(proc_info)
        return matching
    
    def get_all_processors(self) -> Dict[str, List[ProcessorInfo]]:
        """Get all processors organized by type."""
        return {
            'primary': list(self._primary_processors.values()),
            'named': list(self._named_processors.values())
        }

# Global registry
_processor_registry = ProcessorRegistry()

def processor(match: Callable[[Attachment], bool], 
             name: Optional[str] = None,
             description: str = ""):
    """
    Decorator to register a processor function.
    
    Args:
        match: Function to test if this processor handles the attachment
        name: Optional name for specialized processors (None = primary)
        description: Description of what this processor does
        
    Usage:
        @processor(match=lambda att: att.path.endswith('.pdf'))
        def pdf_to_llm(att):  # Primary PDF processor
            return process_pdf(att)
            
        @processor(match=lambda att: att.path.endswith('.pdf'), name="academic_pdf")
        def academic_pdf_to_llm(att):  # Specialized processor
            return process_academic_pdf(att)
    """
    def decorator(func: Callable):
        _processor_registry.register(
            match_fn=match,
            process_fn=func,
            name=name,
            description=description
        )
        return func
    return decorator

def find_primary_processor(att: Attachment) -> Optional[Callable]:
    """Find the primary processor for an attachment."""
    proc_info = _processor_registry.find_primary_processor(att)
    return proc_info.process_fn if proc_info else None

def find_named_processor(name: str) -> Optional[Callable]:
    """Find a named processor by name."""
    proc_info = _processor_registry.find_named_processor(name)
    return proc_info.process_fn if proc_info else None

def list_available_processors() -> Dict[str, Any]:
    """List all available processors for introspection."""
    all_procs = _processor_registry.get_all_processors()
    
    result = {
        'primary_processors': {},
        'named_processors': {}
    }
    
    for proc in all_procs['primary']:
        result['primary_processors'][proc.name] = {
            'description': proc.description,
            'function': proc.process_fn.__name__
        }
    
    for proc in all_procs['named']:
        result['named_processors'][proc.name] = {
            'description': proc.description,
            'function': proc.process_fn.__name__
        }
    
    return result

# Create a namespace for easy access to processors
class ProcessorNamespace:
    """Namespace for accessing processors by name."""
    
    def __getattr__(self, name: str):
        """Get a processor by name."""
        # Try named processors first
        proc_fn = find_named_processor(name)
        if proc_fn:
            return proc_fn
        
        # Try primary processors by function name
        for proc_info in _processor_registry._primary_processors.values():
            if proc_info.process_fn.__name__ == name:
                return proc_info.process_fn
        
        raise AttributeError(f"No processor named '{name}' found")
    
    def __dir__(self):
        """List available processors for autocomplete."""
        names = []
        
        # Add named processors
        names.extend(_processor_registry._named_processors.keys())
        
        # Add primary processor function names
        for proc_info in _processor_registry._primary_processors.values():
            names.append(proc_info.process_fn.__name__)
        
        return sorted(names)

# Global processor namespace
processors = ProcessorNamespace()

# Import all processor modules to register them
from . import pdf_processor
from . import image_processor
from . import docx_processor
from . import pptx_processor
from . import excel_processor
from . import webpage_processor
from . import csv_processor
from . import vector_graphics_processor
from . import example_processors

__all__ = [
    'processor', 'processors', 'find_primary_processor', 'find_named_processor',
    'list_available_processors', 'ProcessorRegistry', 'ProcessorInfo'
] 