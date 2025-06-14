"""
DSPy Integration Module
======================

Clean DSPy integration following the DSPy BaseType pattern:
- Separate import path: from attachments.dspy import Attachments
- Proper Pydantic BaseModel implementation
- serialize_model() method for DSPy integration
- Normal string behavior preserved
- Automatic type registration for DSPy signatures
- Compatible with both DSPy 2.6.25+ (new BaseType) and legacy versions

Usage:
    # For DSPy users - cleaner import with automatic type registration
    from attachments.dspy import Attachments
    import dspy
    
    # Both approaches now work seamlessly:
    
    # 1. Class-based signatures (recommended)
    class MySignature(dspy.Signature):
        document: Attachments = dspy.InputField()
        summary: str = dspy.OutputField()
    
    # 2. String-based signatures (now works automatically!)
    signature = dspy.Signature("document: Attachments -> summary: str")
    
    # Use in DSPy programs
    doc = Attachments("report.pdf")
    result = dspy.ChainOfThought(MySignature)(document=doc)

Automatic Type Registration:
    When you import from attachments.dspy, the Attachments type is automatically
    registered with DSPy's signature parser. This means you can use string-based
    signatures like "document: Attachments -> summary: str" without any additional
    setup or manual type registration.

Version Compatibility:
    This module automatically detects your DSPy version and uses the appropriate
    integration method:
    - DSPy 2.6.25+: Uses new BaseType class with format() method
    - Legacy DSPy: Uses traditional Pydantic BaseModel with serialize_model()
"""

from typing import Any, Union, Dict, List
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


def _create_dspy_class():
    """Create the DSPy-compatible class when DSPy is available."""
    if not _check_dspy_availability():
        return None
    
    import pydantic
    
    # Try to import the new BaseType from DSPy 2.6.25+
    try:
        from dspy.adapters.types import BaseType
        use_new_basetype = True
    except ImportError:
        # Fallback for older DSPy versions
        use_new_basetype = False
    
    if use_new_basetype:
        # DSPy 2.6.25+ with new BaseType
        class DSPyAttachment(BaseType):
            """DSPy-compatible wrapper for Attachment objects following new BaseType pattern."""
            
            text: str = ""
            images: List[str] = []
            audio: List[str] = []
            path: str = ""
            metadata: Dict[str, Any] = {}
            
            # Pydantic v2 configuration
            model_config = pydantic.ConfigDict(
                frozen=True,
                str_strip_whitespace=True,
                validate_assignment=True,
                extra='forbid',
            )
            
            def format(self) -> List[Dict[str, Any]]:
                """Format for DSPy 2.6.25+ - returns list of content dictionaries."""
                content_parts = []
                
                if self.text:
                    content_parts.append({"type": "text", "text": self.text})
                
                if self.images:
                    # Process images - ensure they're properly formatted
                    for img in self.images:
                        if img and isinstance(img, str) and len(img) > 10:
                            # Check if it's already a data URL
                            if img.startswith('data:image/'):
                                content_parts.append({
                                    "type": "image_url",
                                    "image_url": {"url": img}
                                })
                            elif not img.endswith('_placeholder'):
                                # It's raw base64, add the data URL prefix
                                content_parts.append({
                                    "type": "image_url", 
                                    "image_url": {"url": f"data:image/png;base64,{img}"}
                                })
                
                return content_parts if content_parts else [{"type": "text", "text": f"Attachment: {self.path}"}]
            
            def __str__(self):
                # For normal usage, just return the text content
                return self.text if self.text else f"Attachment: {self.path}"
            
            def __repr__(self):
                if self.text:
                    text_preview = self.text[:50] + "..." if len(self.text) > 50 else self.text
                    return f"DSPyAttachment(text='{text_preview}', images={len(self.images)})"
                elif self.images:
                    return f"DSPyAttachment(images={len(self.images)}, path='{self.path}')"
                else:
                    return f"DSPyAttachment(path='{self.path}')"
    
    else:
        # Legacy DSPy versions - keep old implementation
        class DSPyAttachment(pydantic.BaseModel):
            """DSPy-compatible wrapper for Attachment objects following DSPy patterns."""
            
            text: str = ""
            images: List[str] = []
            audio: List[str] = []
            path: str = ""
            metadata: Dict[str, Any] = {}
            
            # Pydantic v2 configuration
            model_config = pydantic.ConfigDict(
                frozen=True,
                str_strip_whitespace=True,
                validate_assignment=True,
                extra='forbid',
            )
            
            @pydantic.model_serializer
            def serialize_model(self):
                """Serialize for DSPy compatibility - called by DSPy framework."""
                content_parts = []
                
                if self.text:
                    content_parts.append(f"<DSPY_TEXT_START>{self.text}<DSPY_TEXT_END>")
                
                if self.images:
                    # Process images - ensure they're properly formatted
                    valid_images = []
                    for img in self.images:
                        if img and isinstance(img, str) and len(img) > 10:
                            # Check if it's already a data URL
                            if img.startswith('data:image/'):
                                valid_images.append(img)
                            elif not img.endswith('_placeholder'):
                                # It's raw base64, add the data URL prefix
                                valid_images.append(f"data:image/png;base64,{img}")
                    
                    if valid_images:
                        for img in valid_images:
                            content_parts.append(f"<DSPY_IMAGE_START>{img}<DSPY_IMAGE_END>")
                
                if content_parts:
                    return "".join(content_parts)
                else:
                    return f"<DSPY_ATTACHMENT_START>Attachment: {self.path}<DSPY_ATTACHMENT_END>"
            
            def __str__(self):
                # For normal usage, just return the text content
                return self.text if self.text else f"Attachment: {self.path}"
            
            def __repr__(self):
                if self.text:
                    text_preview = self.text[:50] + "..." if len(self.text) > 50 else self.text
                    return f"DSPyAttachment(text='{text_preview}', images={len(self.images)})"
                elif self.images:
                    return f"DSPyAttachment(images={len(self.images)}, path='{self.path}')"
                else:
                    return f"DSPyAttachment(path='{self.path}')"
    
    return DSPyAttachment

# TODO: Make it so .text and .images are editable and assignable
class Attachments(BaseAttachments):
    """
    DSPy-optimized Attachments that works seamlessly in DSPy signatures.
    
    This class provides the same interface as regular Attachments but
    creates a DSPy-compatible object when passed to DSPy signatures.
    
    Normal usage (text, images properties) works exactly like regular Attachments.
    DSPy usage (in signatures) automatically converts to proper DSPy format.
    """
    
    def __init__(self, *paths):
        """Initialize with same interface as base Attachments."""
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
        self._dspy_class = _create_dspy_class()
        self._dspy_obj = None
    
    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        """Implement Pydantic core schema for DSPy compatibility."""
        if not _check_dspy_availability():
            # Fallback to string schema if DSPy not available
            import pydantic_core
            return pydantic_core.core_schema.str_schema()
        
        import pydantic_core
        
        # Create a schema that validates Attachments objects and serializes them properly
        def validate_attachments(value):
            if isinstance(value, cls):
                return value
            elif isinstance(value, BaseAttachments):
                # Convert regular Attachments to DSPy-compatible version
                dspy_attachments = cls()
                dspy_attachments.attachments = value.attachments
                return dspy_attachments
            elif isinstance(value, str):
                # Allow string input, create Attachments from it
                return cls(value)
            else:
                raise ValueError(f"Expected Attachments object or string, got {type(value)}")
        
        def serialize_attachments(value):
            if hasattr(value, 'serialize_model'):
                return value.serialize_model()
            return str(value)
        
        return pydantic_core.core_schema.with_info_plain_validator_function(
            validate_attachments,
            serialization=pydantic_core.core_schema.plain_serializer_function_ser_schema(
                serialize_attachments,
                return_schema=pydantic_core.core_schema.str_schema(),
            )
        )
    
    def _get_dspy_obj(self):
        """Get or create the DSPy object representation."""
        if not _check_dspy_availability():
            raise DSPyNotAvailableError(_DSPY_ERROR_MSG)
        
        if self._dspy_obj is None and self._dspy_class is not None:
            # Convert to single attachment
            single_attachment = self._to_single_attachment()
            
            # Clean up images
            clean_images = []
            for img in single_attachment.images:
                if img and isinstance(img, str) and len(img) > 10:
                    if img.startswith('data:image/') or not img.endswith('_placeholder'):
                        clean_images.append(img)
            
            self._dspy_obj = self._dspy_class(
                text=single_attachment.text,
                images=clean_images,
                audio=single_attachment.audio,
                path=single_attachment.path,
                metadata=single_attachment.metadata
            )
        
        return self._dspy_obj
    
    # Implement the DSPy protocol methods that are called by the framework
    def serialize_model(self):
        """DSPy serialization method - called by DSPy framework."""
        if not _check_dspy_availability():
            raise DSPyNotAvailableError(f"Cannot serialize model - {_DSPY_ERROR_MSG}")
        
        dspy_obj = self._get_dspy_obj()
        if dspy_obj:
            # Check if this is the new BaseType with format() method
            if hasattr(dspy_obj, 'format') and callable(getattr(dspy_obj, 'format')):
                # DSPy 2.6.25+ - use the new format method
                try:
                    formatted_content = dspy_obj.format()
                    # The BaseType's serialize_model will handle the proper wrapping
                    return dspy_obj.serialize_model()
                except Exception:
                    # Fallback to old method if format() fails
                    pass
            
            # Legacy DSPy or fallback - use old serialize_model method
            if hasattr(dspy_obj, 'serialize_model'):
                return dspy_obj.serialize_model()
        
        return str(self)  # Final fallback to normal string representation
    
    def model_dump(self):
        """Pydantic v2 compatibility - used by DSPy framework."""
        if not _check_dspy_availability():
            raise DSPyNotAvailableError(f"Cannot dump model - {_DSPY_ERROR_MSG}")
        
        dspy_obj = self._get_dspy_obj()
        if dspy_obj and hasattr(dspy_obj, 'model_dump'):
            return dspy_obj.model_dump()
        return {'text': self.text, 'images': self.images, 'metadata': self.metadata}
    
    def dict(self):
        """Pydantic v1 compatibility."""
        return self.model_dump()
    
    def __getattr__(self, name: str):
        """Forward DSPy-specific attributes to the DSPy object."""
        # Try parent class first
        try:
            return super().__getattr__(name)
        except AttributeError:
            pass
        
        # Check if it's a DSPy/Pydantic attribute
        dspy_attrs = {
            'model_validate', 'model_config', 'model_fields', 
            'json', 'schema', 'copy', 'parse_obj'
        }
        
        if name in dspy_attrs:
            if not _check_dspy_availability():
                raise DSPyNotAvailableError(f"Cannot access '{name}' - {_DSPY_ERROR_MSG}")
            
            dspy_obj = self._get_dspy_obj()
            if dspy_obj and hasattr(dspy_obj, name):
                return getattr(dspy_obj, name)
        
        # If not found, raise the original error
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")


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


# Automatic type registration for DSPy signature compatibility
# This makes Attachments available to DSPy's string-based signature parser
def _register_types_for_dspy():
    """
    Automatically register Attachments type for DSPy signature parsing.
    
    This function is called when the module is imported, making it so users
    can use string-based DSPy signatures like:
    
        dspy.Signature("document: Attachments -> summary: str")
    
    without any additional setup.
    """
    try:
        import typing
        import sys
        
        # Make Attachments available in the typing module namespace
        # This is where DSPy's signature parser looks for types
        typing.Attachments = Attachments
        
        # Also add to the current module's globals for importlib resolution
        # DSPy tries importlib.import_module() as a fallback
        current_module = sys.modules[__name__]
        if not hasattr(current_module, 'Attachments'):
            setattr(current_module, 'Attachments', Attachments)
            
        # For extra compatibility, also add to builtins if safe to do so
        # This ensures maximum compatibility across different DSPy versions
        try:
            import builtins
            if not hasattr(builtins, 'Attachments'):
                builtins.Attachments = Attachments
        except (ImportError, AttributeError):
            # If we can't modify builtins, that's okay
            pass
            
    except Exception:
        # If type registration fails, don't break the import
        # Users can still use class-based signatures or manual registration
        pass


# Automatically register types when module is imported
_register_types_for_dspy() 