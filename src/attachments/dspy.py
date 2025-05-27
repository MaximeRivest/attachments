"""
DSPy Integration Module
======================

Clean DSPy integration following the thread discussion:
- Separate import path: from attachments.dspy import Attachments
- Duck-typing approach without complex inheritance
- No .dspy() calls needed in user code
- Optional dependency handling

Usage:
    # For DSPy users - cleaner import
    from attachments.dspy import Attachments
    
    # Works directly in DSPy signatures
    doc = Attachments("report.pdf")
    result = rag(question="What are the key findings?", document=doc)
    
    # For regular users - unchanged
    from attachments import Attachments
    doc = Attachments("report.pdf").dspy()  # Still works
"""

from typing import Any, Union
from .highest_level_api import Attachments as BaseAttachments


# Check for DSPy availability at module import time
_DSPY_AVAILABLE = None
_DSPY_ERROR_MSG = None

def _check_dspy_availability():
    """Check if DSPy is available and cache the result."""
    global _DSPY_AVAILABLE, _DSPY_ERROR_MSG
    
    if _DSPY_AVAILABLE is not None:
        return _DSPY_AVAILABLE
    
    try:
        import dspy
        import pydantic
        _DSPY_AVAILABLE = True
        _DSPY_ERROR_MSG = None
    except ImportError as e:
        _DSPY_AVAILABLE = False
        missing_packages = []
        
        try:
            import dspy
        except ImportError:
            missing_packages.append("dspy-ai")
        
        try:
            import pydantic
        except ImportError:
            missing_packages.append("pydantic")
        
        if missing_packages:
            _DSPY_ERROR_MSG = (
                f"DSPy integration requires {' and '.join(missing_packages)} to be installed.\n\n"
                f"Install with:\n"
                f"  pip install {' '.join(missing_packages)}\n"
                f"  # or\n"
                f"  uv add {' '.join(missing_packages)}\n\n"
                f"If you don't need DSPy integration, use the regular import instead:\n"
                f"  from attachments import Attachments"
            )
        else:
            _DSPY_ERROR_MSG = f"DSPy integration failed: {e}"
    
    return _DSPY_AVAILABLE


class DSPyNotAvailableError(ImportError):
    """Raised when DSPy functionality is used but DSPy is not installed."""
    pass


class Attachments(BaseAttachments):
    """
    DSPy-optimized Attachments that works seamlessly in DSPy signatures.
    
    This class provides the same interface as regular Attachments but
    automatically works with DSPy without requiring .dspy() calls.
    
    Requires DSPy to be installed. If DSPy is not available, consider using
    the regular Attachments class instead:
        from attachments import Attachments
    """
    
    def __init__(self, *paths):
        """Initialize with same interface as base Attachments."""
        # Check DSPy availability early but allow object creation
        # This allows for better error messages when methods are actually called
        if not _check_dspy_availability():
            import warnings
            warnings.warn(
                f"DSPy is not available. {_DSPY_ERROR_MSG}\n"
                f"The Attachments object will work for basic operations but DSPy-specific "
                f"functionality will raise errors.",
                UserWarning,
                stacklevel=2
            )
        
        super().__init__(*paths)
        self._dspy_obj = None
    
    def _ensure_dspy_obj(self):
        """Lazily create the DSPy object when needed."""
        if not _check_dspy_availability():
            raise DSPyNotAvailableError(_DSPY_ERROR_MSG)
        
        if self._dspy_obj is None:
            # Use the exact same pattern as the working adapt.py
            from .adapt import dspy as dspy_adapter
            
            # Convert to single attachment using the base class method
            single_attachment = self._to_single_attachment()
            self._dspy_obj = dspy_adapter(single_attachment)
        return self._dspy_obj
    
    def __str__(self):
        """
        String representation that works for both contexts.
        
        In DSPy contexts, this returns the serialized model.
        In regular contexts, this returns the formatted text.
        """
        # Try DSPy serialization first if available
        if _check_dspy_availability():
            try:
                dspy_obj = self._ensure_dspy_obj()
                if hasattr(dspy_obj, 'serialize_model'):
                    return dspy_obj.serialize_model()
                elif hasattr(dspy_obj, '__str__'):
                    return str(dspy_obj)
            except Exception:
                # Fall back to regular string representation
                pass
        
        return super().__str__()
    
    def __getattr__(self, name: str):
        """
        Forward DSPy-specific attributes to the DSPy object.
        
        This enables duck-typing compatibility with DSPy BaseType.
        """
        # Try parent class first
        try:
            return super().__getattr__(name)
        except AttributeError:
            pass
        
        # Check if it's a DSPy/Pydantic attribute
        dspy_attrs = {
            'serialize_model', 'model_validate', 'model_dump', 'model_config',
            'model_fields', 'dict', 'json', 'schema', 'copy', 'parse_obj'
        }
        
        if name in dspy_attrs:
            if not _check_dspy_availability():
                raise DSPyNotAvailableError(
                    f"Cannot access '{name}' - {_DSPY_ERROR_MSG}"
                )
            
            dspy_obj = self._ensure_dspy_obj()
            if hasattr(dspy_obj, name):
                return getattr(dspy_obj, name)
        
        # If not found, raise the original error
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")
    
    def serialize_model(self):
        """DSPy serialization method."""
        if not _check_dspy_availability():
            raise DSPyNotAvailableError(
                f"Cannot serialize model - {_DSPY_ERROR_MSG}"
            )
        
        dspy_obj = self._ensure_dspy_obj()
        if hasattr(dspy_obj, 'serialize_model'):
            return dspy_obj.serialize_model()
        return str(self)
    
    def model_dump(self):
        """Pydantic v2 compatibility."""
        if not _check_dspy_availability():
            raise DSPyNotAvailableError(
                f"Cannot dump model - {_DSPY_ERROR_MSG}"
            )
        
        dspy_obj = self._ensure_dspy_obj()
        if hasattr(dspy_obj, 'model_dump'):
            return dspy_obj.model_dump()
        elif hasattr(dspy_obj, 'dict'):
            return dspy_obj.dict()
        return {'text': self.text, 'images': self.images, 'metadata': self.metadata}
    
    def dict(self):
        """Pydantic v1 compatibility."""
        return self.model_dump()


# Factory function for explicit DSPy object creation
def make_dspy(*paths) -> Any:
    """
    Create a DSPy-compatible object directly.
    
    This function returns the actual DSPy object (if available)
    rather than the wrapper class.
    
    Usage:
        doc = make_dspy("report.pdf")
        # Returns actual DSPy BaseType object
    
    Raises:
        DSPyNotAvailableError: If DSPy is not installed
    """
    if not _check_dspy_availability():
        raise DSPyNotAvailableError(_DSPY_ERROR_MSG)
    
    attachments = BaseAttachments(*paths)
    # Use the exact same pattern as the working adapt.py
    from .adapt import dspy as dspy_adapter
    
    single_attachment = attachments._to_single_attachment()
    return dspy_adapter(single_attachment)


# Convenience function for migration
def from_attachments(attachments: BaseAttachments) -> 'Attachments':
    """
    Convert a regular Attachments object to DSPy-compatible version.
    
    Usage:
        from attachments import Attachments as RegularAttachments
        from attachments.dspy import from_attachments
        
        regular = RegularAttachments("file.pdf")
        dspy_ready = from_attachments(regular)
    
    Raises:
        DSPyNotAvailableError: If DSPy is not installed and DSPy-specific methods are used
    """
    # Create new DSPy-compatible instance with same content
    dspy_attachments = Attachments()
    dspy_attachments.attachments = attachments.attachments
    return dspy_attachments


__all__ = ['Attachments', 'make_dspy', 'from_attachments', 'DSPyNotAvailableError'] 