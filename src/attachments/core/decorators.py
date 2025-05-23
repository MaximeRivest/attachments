"""Decorators for registering loaders, modifiers, presenters, and adapters."""

import functools
import inspect
from typing import Any, Callable, get_type_hints, Union
import sys

from .attachment import Attachment
from .namespaces import load, modify, present, adapt


# Registry for multiple dispatch
_presenter_registry = {}
_modifier_registry = {}
_adapter_registry = {}


def loader(matcher: Callable[[str], bool]):
    """Decorator for creating loaders."""
    def decorator(func):
        # Create a LoaderFunction class to enable | operator
        class LoaderFunction:
            def __init__(self, loader_func, matcher_func):
                self.loader_func = loader_func
                self.matcher_func = matcher_func
                self.__name__ = loader_func.__name__
                self.__doc__ = loader_func.__doc__
            
            def __call__(self, path_or_attachment):
                # If already an attachment, check if we should process
                if isinstance(path_or_attachment, Attachment):
                    if not path_or_attachment._pipeline_ready:
                        return path_or_attachment
                    path = path_or_attachment.source
                else:
                    path = path_or_attachment
                
                # Parse commands
                from ..utils.parsing import parse_path_expression
                actual_path, commands = parse_path_expression(path)
                
                # Check if this loader handles this path
                if not self.matcher_func(actual_path):
                    # Pass through for next loader in pipeline
                    if isinstance(path_or_attachment, Attachment):
                        return path_or_attachment
                    # Create empty attachment that signals "not handled"
                    return Attachment(None, path, commands)
                
                # Load the content
                content = self.loader_func(actual_path)
                
                # Return as Attachment
                return Attachment(content, actual_path, commands)
            
            def __or__(self, other):
                """Compose loaders with | operator."""
                def composed_loader(path_or_attachment):
                    # Try this loader first
                    try:
                        result = self(path_or_attachment)
                        # If it successfully loaded content, return it
                        if isinstance(result, Attachment) and result.content is not None:
                            return result
                    except Exception:
                        # This loader couldn't handle it, try next
                        pass
                    
                    # Try the other loader
                    return other(path_or_attachment)
                
                # Create a wrapper class that acts like LoaderFunction
                class ComposedLoader:
                    def __init__(self, name):
                        self.__name__ = name
                    
                    def __call__(self, path_or_attachment):
                        return composed_loader(path_or_attachment)
                    
                    def __or__(self, other):
                        # Allow further composition
                        return LoaderFunction.__or__(self, other)
                
                composed = ComposedLoader(f"{self.__name__}|{getattr(other, '__name__', 'unknown')}")
                return composed
        
        # Create loader instance
        loader_instance = LoaderFunction(func, matcher)
        
        # Add to namespace
        setattr(load, func.__name__, loader_instance)
        
        return loader_instance
    return decorator


def presenter(func):
    """Decorator for creating presenters with type-based dispatch."""
    # Get the type from the first parameter annotation
    sig = inspect.signature(func)
    params = list(sig.parameters.values())
    if params and params[0].annotation != inspect.Parameter.empty:
        obj_type = params[0].annotation
    else:
        raise ValueError(f"Presenter {func.__name__} must have type annotation")
    
    # Register the function
    key = func.__name__
    if key not in _presenter_registry:
        _presenter_registry[key] = {}
    _presenter_registry[key][obj_type] = func
    
    # Create or get the dispatcher
    if not hasattr(present, key):
        def dispatcher(att_or_obj):
            # Handle both raw objects and Attachments
            if isinstance(att_or_obj, Attachment):
                obj = att_or_obj.content
            else:
                obj = att_or_obj
                
            # Find the right function
            obj_type = type(obj)
            for registered_type, registered_func in _presenter_registry[key].items():
                if isinstance(obj, registered_type):
                    result = registered_func(obj)
                    # Return Attachment with presented content
                    if isinstance(att_or_obj, Attachment):
                        new_att = Attachment(result, att_or_obj.source, att_or_obj.commands)
                        return new_att
                    return result
                    
            raise TypeError(f"No {key} presenter for type {obj_type}")
        
        # Make it pipeable
        dispatcher.__or__ = lambda self, other: lambda x: dispatcher(x) | other
        dispatcher.__add__ = lambda self, other: lambda x: dispatcher(x) + other(x)
        
        setattr(present, key, dispatcher)
    
    return func


def modifier(func):
    """Decorator for creating modifiers with type-based dispatch."""
    # Similar to presenter but modifies in place
    sig = inspect.signature(func)
    params = list(sig.parameters.values())
    if params and params[0].annotation != inspect.Parameter.empty:
        obj_type = params[0].annotation
    else:
        obj_type = None  # Universal modifier
    
    key = func.__name__
    if key not in _modifier_registry:
        _modifier_registry[key] = {}
    _modifier_registry[key][obj_type] = func
    
    if not hasattr(modify, key):
        def dispatcher(att, *args, **kwargs):
            if not isinstance(att, Attachment):
                raise TypeError("Modifiers work on Attachment objects")
                
            # Find the right function
            obj_type = type(att.content)
            for registered_type, registered_func in _modifier_registry[key].items():
                # Handle typing.Any specially since isinstance() doesn't work with it
                if registered_type is None or registered_type is Any or (
                    registered_type is not Any and isinstance(att.content, registered_type)
                ):
                    # Check for command override
                    if key in att.commands and not args and not kwargs:
                        # Use command from path expression
                        result = registered_func(att.content, att.commands[key])
                    else:
                        result = registered_func(att.content, *args, **kwargs)
                    
                    return Attachment(result, att.source, att.commands)
            
            # Generate helpful error message with suggestions
            available_modifiers = _get_available_modifiers_for_type(obj_type)
            type_name = obj_type.__name__
            
            # File extension for context
            file_ext = ""
            if hasattr(att, 'source') and att.source:
                from pathlib import Path
                file_ext = Path(att.source).suffix.lower()
            
            error_msg = f"No '{key}' modifier available for {type_name}"
            if file_ext:
                error_msg += f" (from {file_ext} file)"
            
            if available_modifiers:
                error_msg += f"\n\nAvailable modifiers for {type_name}:\n"
                for mod_name, mod_info in available_modifiers.items():
                    error_msg += f"  • {mod_name}: {mod_info}\n"
            else:
                error_msg += f"\n\nNo modifiers are currently available for {type_name}."
                
            # Add general DSL usage help
            error_msg += f"\n\nDSL Usage Examples:"
            error_msg += f"\n  • PDF files: file.pdf[pages:1-3]"
            error_msg += f"\n  • Images: image.jpg[resize:50%] or image.jpg[resize:800x600]"
            error_msg += f"\n  • CSV files: data.csv[sample:100]"
            
            raise TypeError(error_msg)
        
        # Make it pipeable and callable
        class ModifierFunction:
            def __call__(self, *args, **kwargs):
                if args and isinstance(args[0], Attachment):
                    # Direct call: modify.pages(attachment)
                    return dispatcher(args[0], *args[1:], **kwargs)
                else:
                    # Pipeline call: modify.pages(1, 5)
                    return lambda att: dispatcher(att, *args, **kwargs)
            
            def __or__(self, other):
                return lambda x: self()(x) | other
                
        setattr(modify, key, ModifierFunction())
    
    return func


def adapter(func):
    """Decorator for creating adapters with robust type resolution."""
    key = func.__name__
    if key not in _adapter_registry:
        _adapter_registry[key] = {}
    
    # Get the type from the first parameter annotation
    sig = inspect.signature(func)
    params = list(sig.parameters.values())
    if params and params[0].annotation != inspect.Parameter.empty:
        obj_type = params[0].annotation
    else:
        obj_type = None  # Universal adapter
    
    _adapter_registry[key][obj_type] = func
    
    if not hasattr(adapt, key):
        def dispatcher(obj, *args, **kwargs):
            """Smart dispatcher that resolves forward references and uses duck typing."""
            obj_type = type(obj)
            
            # First pass: try to resolve type hints for this function to handle forward references
            resolved_types = {}
            try:
                # Get the function that registered this type
                for registered_type, registered_func in _adapter_registry[key].items():
                    if registered_type is not None:
                        # Try to resolve forward references using the function's module context
                        try:
                            # Create a namespace that includes Attachments for resolution
                            namespace = {}
                            
                            # Add the function's globals
                            if hasattr(registered_func, '__globals__'):
                                namespace.update(registered_func.__globals__)
                            
                            # Try to import Attachments if not already available
                            try:
                                if 'Attachments' not in namespace:
                                    from .. import Attachments
                                    namespace['Attachments'] = Attachments
                            except ImportError:
                                pass
                            
                            # Resolve type hints with our enhanced namespace
                            type_hints = get_type_hints(registered_func, globalns=namespace)
                            if 'source' in type_hints:
                                resolved_type = type_hints['source']
                                resolved_types[registered_type] = resolved_type
                            else:
                                resolved_types[registered_type] = registered_type
                        except (NameError, AttributeError, TypeError):
                            # Can't resolve this forward reference, keep original
                            resolved_types[registered_type] = registered_type
                    else:
                        resolved_types[registered_type] = registered_type
            except Exception:
                # If resolution fails completely, fall back to original types
                resolved_types = {k: k for k in _adapter_registry[key].keys()}
            
            # Second pass: dispatch using resolved types and smart duck typing
            for original_type, resolved_type in resolved_types.items():
                registered_func = _adapter_registry[key][original_type]
                
                # Case 1: Universal adapter (None type)
                if original_type is None:
                    return registered_func(obj, *args, **kwargs)
                
                # Case 2: Exact type match after resolution
                try:
                    if resolved_type != original_type and hasattr(resolved_type, '__origin__'):
                        # Handle Union types like Union[Attachment, "Attachments"]
                        if resolved_type.__origin__ is Union:
                            union_args = resolved_type.__args__
                            for union_type in union_args:
                                if _matches_type(obj, union_type):
                                    return registered_func(obj, *args, **kwargs)
                    elif resolved_type != original_type and isinstance(obj, resolved_type):
                        return registered_func(obj, *args, **kwargs)
                except (TypeError, AttributeError):
                    pass
                
                # Case 3: Duck typing and smart type matching
                if _matches_type(obj, original_type) or _matches_type(obj, resolved_type):
                    return registered_func(obj, *args, **kwargs)
                    
            raise TypeError(f"No {key} adapter for type {obj_type.__name__}. Available adapters: {list(_adapter_registry[key].keys())}")
        
        setattr(adapt, key, dispatcher)
        
        # Auto-add convenience method to Attachments class
        _add_adapter_method_to_attachments(key, dispatcher)
    
    return func


def _matches_type(obj, type_hint):
    """
    Smart type matching that handles forward references, duck typing, and Union types.
    
    Returns True if obj matches the type_hint using various strategies.
    """
    if type_hint is None:
        return True
    
    obj_type = type(obj)
    
    # Strategy 1: Direct isinstance check (works for resolved types)
    try:
        if isinstance(obj, type_hint):
            return True
    except TypeError:
        pass  # type_hint might be a string or Union, continue with other strategies
    
    # Strategy 2: String forward reference and ForwardRef matching
    if isinstance(type_hint, str):
        # Match by class name
        if obj_type.__name__ == type_hint:
            return True
        # Special case for "Attachments" - duck typing
        if type_hint == "Attachments" and hasattr(obj, 'attachments'):
            return True
    
    # Strategy 2b: Handle ForwardRef objects
    if hasattr(type_hint, '__forward_arg__'):
        forward_name = type_hint.__forward_arg__
        if obj_type.__name__ == forward_name:
            return True
        # Special case for "Attachments" - duck typing
        if forward_name == "Attachments" and hasattr(obj, 'attachments'):
            return True
    
    # Strategy 3: Handle Union types
    if hasattr(type_hint, '__origin__') and type_hint.__origin__ is Union:
        for union_arg in type_hint.__args__:
            if _matches_type(obj, union_arg):
                return True
    
    # Strategy 4: Handle generic types and type variables
    if hasattr(type_hint, '__origin__'):
        try:
            if isinstance(obj, type_hint.__origin__):
                return True
        except TypeError:
            pass
    
    # Strategy 5: Attachment duck typing
    if hasattr(type_hint, '__name__') and type_hint.__name__ == 'Attachment':
        if hasattr(obj, 'content') and hasattr(obj, 'source'):
            return True
    
    return False


def _add_adapter_method_to_attachments(adapter_name: str, dispatcher_func):
    """Add a to_* method to the Attachments class for this adapter."""
    # Convert adapter name to method name (e.g., 'openai_chat' -> 'to_openai_chat')
    method_name = f"to_{adapter_name}"
    
    # For common patterns, clean up the method name
    if adapter_name.endswith('_chat'):
        # 'openai_chat' -> 'to_openai' 
        method_name = f"to_{adapter_name[:-5]}"
    elif adapter_name.endswith('_responses'):
        # 'openai_responses' -> 'to_openai_responses'
        method_name = f"to_{adapter_name}"
    
    def adapter_method(self, *args, **kwargs):
        """Auto-generated adapter method."""
        return dispatcher_func(self, *args, **kwargs)
    
    # Add docstring
    adapter_method.__doc__ = f"""
    Format attachments using the {adapter_name} adapter.
    
    This method is automatically generated from the @adapter decorator.
    It calls adapt.{adapter_name}(self, *args, **kwargs) internally.
    """
    
    # We need to defer adding this to the Attachments class until it's imported
    # Store the method to be added later
    if not hasattr(_add_adapter_method_to_attachments, '_deferred_methods'):
        _add_adapter_method_to_attachments._deferred_methods = {}
    _add_adapter_method_to_attachments._deferred_methods[method_name] = adapter_method


def _register_adapter_methods_on_attachments():
    """Register all deferred adapter methods on the Attachments class."""
    if hasattr(_add_adapter_method_to_attachments, '_deferred_methods'):
        # Import here to avoid circular imports
        from .. import Attachments
        
        # Make Attachments available in the global scope for type resolution
        globals()['Attachments'] = Attachments
        
        for method_name, method_func in _add_adapter_method_to_attachments._deferred_methods.items():
            if not hasattr(Attachments, method_name):
                setattr(Attachments, method_name, method_func)


def _get_available_modifiers_for_type(obj_type):
    """
    Get all available modifiers for a specific object type.
    
    Returns a dict of {modifier_name: description} for the given type.
    """
    available = {}
    
    # Check all registered modifiers
    for modifier_name, type_registry in _modifier_registry.items():
        for registered_type, registered_func in type_registry.items():
            # Check if this modifier works with the object type
            if (registered_type is None or  # Universal modifier
                registered_type is Any or   # Any type modifier
                (registered_type is not Any and 
                 registered_type is not None and 
                 _type_matches(obj_type, registered_type))):
                
                # Generate a helpful description
                description = _get_modifier_description(modifier_name, registered_func, obj_type)
                available[modifier_name] = description
                break  # Found a match for this modifier
    
    return available


def _type_matches(obj_type, registered_type):
    """Check if obj_type matches the registered_type for modifier dispatch."""
    try:
        # Create a dummy instance check
        if hasattr(registered_type, '__name__'):
            return obj_type.__name__ == registered_type.__name__ or issubclass(obj_type, registered_type)
        return False
    except (TypeError, AttributeError):
        return False


def _get_modifier_description(modifier_name, registered_func, obj_type):
    """Generate a helpful description for a modifier based on the object type."""
    
    # Custom descriptions for known modifiers
    descriptions = {
        'pages': {
            'PdfReader': 'Extract specific pages (e.g., pages:1-3, pages:1,3,5)',
            'Presentation': 'Extract specific slides (e.g., pages:1-3)'
        },
        'sample': {
            'DataFrame': 'Sample random rows (e.g., sample:100)'
        },
        'resize': {
            'Image': 'Resize image (e.g., resize:50%, resize:800x600)'
        },
        'tile': {
            'Image': 'Create tiled layout (e.g., tile:2x2)'
        },
        'present_as': {
            'default': 'Change presentation format (e.g., present_as:markdown)'
        }
    }
    
    obj_type_name = obj_type.__name__
    
    if modifier_name in descriptions:
        type_desc = descriptions[modifier_name]
        if obj_type_name in type_desc:
            return type_desc[obj_type_name]
        elif 'default' in type_desc:
            return type_desc['default']
    
    # Fallback: try to extract from docstring
    if hasattr(registered_func, '__doc__') and registered_func.__doc__:
        return registered_func.__doc__.split('\n')[0].strip('"""').strip()
    
    return f"Apply {modifier_name} transformation" 