"""Decorators for registering loaders, modifiers, presenters, and adapters."""

import functools
import inspect
from typing import Any, Callable

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
                    
            raise TypeError(f"No {key} modifier for type {obj_type}")
        
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
    """Decorator for creating adapters."""
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
            # Find the right function
            obj_type = type(obj)
            for registered_type, registered_func in _adapter_registry[key].items():
                if registered_type is None or isinstance(obj, registered_type):
                    return registered_func(obj, *args, **kwargs)
                    
            raise TypeError(f"No {key} adapter for type {obj_type}")
        
        setattr(adapt, key, dispatcher)
    
    return func 