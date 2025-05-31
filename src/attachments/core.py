from typing import Any, Dict, List, Optional, Union, Callable, get_type_hints
from functools import wraps, partial
import re
import base64
import io
from pathlib import Path

class Pipeline:
    """A callable pipeline that can be applied to attachments."""
    
    def __init__(self, steps: List[Callable] = None, fallback_pipelines: List['Pipeline'] = None):
        self.steps = steps or []
        self.fallback_pipelines = fallback_pipelines or []
    
    def __or__(self, other: Union[Callable, 'Pipeline']) -> 'Pipeline':
        """Chain this pipeline with another step or pipeline."""
        if isinstance(other, Pipeline):
            # If both are pipelines, create a new pipeline with fallback logic
            if self.steps and other.steps:
                # This is chaining two complete pipelines - treat as fallback
                return Pipeline(self.steps, [other] + other.fallback_pipelines)
            elif not self.steps:
                # If self is empty, just return other
                return other
            else:
                # Concatenate steps
                return Pipeline(self.steps + other.steps, other.fallback_pipelines)
        else:
            # Adding a single step to the pipeline
            return Pipeline(self.steps + [other], self.fallback_pipelines)
    
    def __call__(self, input_: Union[str, 'Attachment']) -> Any:
        """Apply the pipeline to an input."""
        if isinstance(input_, str):
            result = Attachment(input_)
        else:
            result = input_
        
        # Try the main pipeline first
        try:
            return self._execute_steps(result, self.steps)
        except Exception as e:
            # If the main pipeline fails, try fallback pipelines
            for fallback in self.fallback_pipelines:
                try:
                    return fallback(input_)
                except:
                    continue
            # If all pipelines fail, raise the original exception
            raise e
    
    def _execute_steps(self, result: 'Attachment', steps: List[Callable]) -> Any:
        """Execute a list of steps on an attachment."""
        for step in steps:
            result = step(result)
            if result is None:
                # If step returns None, keep the previous result
                continue
            if not isinstance(result, (Attachment, AttachmentCollection)):
                # If step returns something else (like an adapter result), return it directly
                # This allows adapters to "exit" the pipeline and return their result
                return result
        
        return result
    
    def __getattr__(self, name: str):
        """Allow calling adapters as methods on pipelines."""
        if name in _adapters:
            def adapter_method(input_: Union[str, 'Attachment'], *args, **kwargs):
                # Apply pipeline first, then adapter
                result = self(input_)
                adapter_fn = _adapters[name]
                return adapter_fn(result, *args, **kwargs)
            return adapter_method
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")
    
    def __repr__(self) -> str:
        step_names = [getattr(step, '__name__', str(step)) for step in self.steps]
        main_pipeline = f"Pipeline({' | '.join(step_names)})"
        if self.fallback_pipelines:
            fallback_names = [repr(fp) for fp in self.fallback_pipelines]
            return f"{main_pipeline} with fallbacks: [{', '.join(fallback_names)}]"
        return main_pipeline

class AdditivePipeline:
    """A pipeline that applies presenters additively, preserving existing content."""
    
    def __init__(self, steps: List[Callable] = None):
        self.steps = steps or []
    
    def __call__(self, input_: Union[str, 'Attachment']) -> 'Attachment':
        """Apply additive pipeline - each step adds to existing content."""
        if isinstance(input_, str):
            result = Attachment(input_)
        else:
            result = input_
        
        for step in self.steps:
            # Apply each step to the original attachment
            # Each presenter should preserve existing content and add new content
            result = step(result)
            if result is None:
                continue
        
        return result
    
    def __add__(self, other: Union[Callable, 'AdditivePipeline']) -> 'AdditivePipeline':
        """Chain additive pipelines."""
        if isinstance(other, AdditivePipeline):
            return AdditivePipeline(self.steps + other.steps)
        else:
            return AdditivePipeline(self.steps + [other])
    
    def __or__(self, other: Union[Callable, Pipeline]) -> Pipeline:
        """Convert to regular pipeline when using | operator."""
        return Pipeline([self]) | other
    
    def __repr__(self) -> str:
        step_names = [getattr(step, '__name__', str(step)) for step in self.steps]
        return f"AdditivePipeline({' + '.join(step_names)})"

class AttachmentCollection:
    """A collection of attachments that supports vectorized operations."""
    
    def __init__(self, attachments: List['Attachment']):
        self.attachments = attachments or []
    
    def __or__(self, operation: Union[Callable, Pipeline]) -> Union['AttachmentCollection', 'Attachment']:
        """Apply operation - vectorize or reduce based on operation type."""
        
        # Check if this is a reducing operation (operates on collections)
        if self._is_reducer(operation):
            # Apply to the collection as a whole (reduction)
            return operation(self)
        else:
            # Apply to each attachment (vectorization)
            results = []
            for att in self.attachments:
                result = operation(att)
                if result is not None:
                    results.append(result)
            return AttachmentCollection(results)
    
    def __add__(self, other: Union[Callable, Pipeline]) -> 'AttachmentCollection':
        """Apply additive operation to each attachment."""
        results = []
        for att in self.attachments:
            result = att + other
            if result is not None:
                results.append(result)
        return AttachmentCollection(results)
    
    def _is_reducer(self, operation) -> bool:
        """Check if an operation is a reducer (combines multiple attachments)."""
        # Check if it's a refiner that works on collections
        if hasattr(operation, 'name'):
            reducing_operations = {
                'tile_images', 'combine_images', 'merge_text', 
                'claude', 'openai_chat', 'openai_response'  # Adapters are always reducers
            }
            return operation.name in reducing_operations
        return False
    
    def to_attachment(self) -> 'Attachment':
        """Convert collection to single attachment by combining content."""
        if not self.attachments:
            return Attachment("")
        
        # Create a new attachment that combines all content
        combined = Attachment("")
        combined.text = "\n\n".join(att.text for att in self.attachments if att.text)
        combined.images = [img for att in self.attachments for img in att.images]
        combined.audio = [audio for att in self.attachments for audio in att.audio]
        
        # Combine metadata
        combined.metadata = {
            'collection_size': len(self.attachments),
            'combined_from': [att.path for att in self.attachments]
        }
        
        return combined
    
    def __len__(self) -> int:
        return len(self.attachments)
    
    def __getitem__(self, index: int) -> 'Attachment':
        return self.attachments[index]
    
    def __repr__(self) -> str:
        return f"AttachmentCollection({len(self.attachments)} attachments)"

class Attachment:
    """Simple container for file processing."""
    
    def __init__(self, attachy: str = ""):
        self.attachy = attachy
        self.path, self.commands = self._parse_attachy()
        
        self._obj: Optional[Any] = None
        self.text: str = ""
        self.images: List[str] = []
        self.audio: List[str] = []
        self.metadata: Dict[str, Any] = {}
        
        self.pipeline: List[str] = []
        
        # Cache for content analysis (avoid repeated reads)
        self._content_cache: Dict[str, Any] = {}
    
    @property
    def content_type(self) -> str:
        """Get the Content-Type header from URL responses, or empty string."""
        return self.metadata.get('content_type', '').lower()
    
    @property
    def has_content(self) -> bool:
        """Check if attachment has downloadable content (from URLs)."""
        return (hasattr(self, '_file_content') and self._file_content is not None) or \
               (hasattr(self, '_response') and self._response is not None)
    
    def get_magic_bytes(self, num_bytes: int = 20) -> bytes:
        """
        Get the first N bytes of content for magic number detection.
        
        Returns empty bytes if no content is available or on error.
        Uses caching to avoid repeated reads.
        """
        cache_key = f"magic_bytes_{num_bytes}"
        if cache_key in self._content_cache:
            return self._content_cache[cache_key]
        
        magic_bytes = b''
        
        try:
            if hasattr(self, '_file_content') and self._file_content:
                original_pos = self._file_content.tell()
                self._file_content.seek(0)
                magic_bytes = self._file_content.read(num_bytes)
                self._file_content.seek(original_pos)
            elif hasattr(self, '_response') and self._response:
                magic_bytes = self._response.content[:num_bytes]
        except Exception:
            # If reading fails, return empty bytes
            magic_bytes = b''
        
        # Cache the result
        self._content_cache[cache_key] = magic_bytes
        return magic_bytes
    
    def get_content_sample(self, num_bytes: int = 1000) -> bytes:
        """
        Get a larger sample of content for analysis.
        
        Returns empty bytes if no content is available or on error.
        Uses caching to avoid repeated reads.
        """
        cache_key = f"content_sample_{num_bytes}"
        if cache_key in self._content_cache:
            return self._content_cache[cache_key]
        
        content_sample = b''
        
        try:
            if hasattr(self, '_file_content') and self._file_content:
                original_pos = self._file_content.tell()
                self._file_content.seek(0)
                content_sample = self._file_content.read(num_bytes)
                self._file_content.seek(original_pos)
            elif hasattr(self, '_response') and self._response:
                content_sample = self._response.content[:num_bytes]
        except Exception:
            content_sample = b''
        
        # Cache the result
        self._content_cache[cache_key] = content_sample
        return content_sample
    
    def get_text_sample(self, num_chars: int = 500, encoding: str = 'utf-8') -> str:
        """
        Get a text sample of content for text-based analysis.
        
        Returns empty string if content cannot be decoded as text.
        """
        cache_key = f"text_sample_{num_chars}_{encoding}"
        if cache_key in self._content_cache:
            return self._content_cache[cache_key]
        
        text_sample = ''
        
        try:
            # Get more bytes than characters since some chars are multi-byte
            content_sample = self.get_content_sample(num_chars * 2)
            if content_sample:
                text_sample = content_sample.decode(encoding, errors='ignore')[:num_chars]
        except Exception:
            text_sample = ''
        
        # Cache the result
        self._content_cache[cache_key] = text_sample
        return text_sample
    
    def has_magic_signature(self, signatures: Union[bytes, List[bytes]]) -> bool:
        """
        Check if content starts with any of the given magic number signatures.
        
        Args:
            signatures: Single signature (bytes) or list of signatures to check
            
        Returns:
            True if content starts with any of the signatures
        """
        if isinstance(signatures, bytes):
            signatures = [signatures]
        
        magic_bytes = self.get_magic_bytes(max(len(sig) for sig in signatures) if signatures else 20)
        
        for signature in signatures:
            if magic_bytes.startswith(signature):
                return True
        
        return False
    
    def contains_in_content(self, patterns: Union[bytes, str, List[Union[bytes, str]]], 
                           max_search_bytes: int = 2000) -> bool:
        """
        Check if content contains any of the given patterns.
        
        Useful for checking ZIP-based Office formats (e.g., word/, ppt/, xl/).
        
        Args:
            patterns: Pattern(s) to search for (bytes or strings)
            max_search_bytes: How many bytes to search in
            
        Returns:
            True if any pattern is found in the content
        """
        if not isinstance(patterns, list):
            patterns = [patterns]
        
        content_sample = self.get_content_sample(max_search_bytes)
        if not content_sample:
            return False
        
        # Convert content to string for mixed pattern searching
        try:
            content_str = content_sample.decode('latin-1', errors='ignore')
        except:
            content_str = ''
        
        for pattern in patterns:
            if isinstance(pattern, bytes):
                if pattern in content_sample:
                    return True
            elif isinstance(pattern, str):
                if pattern in content_str:
                    return True
        
        return False
    
    def is_likely_text(self, sample_size: int = 1000) -> bool:
        """
        Heuristic to determine if content is likely text-based.
        
        Returns True if content can be decoded as UTF-8 and doesn't look like binary.
        """
        cache_key = f"is_text_{sample_size}"
        if cache_key in self._content_cache:
            return self._content_cache[cache_key]
        
        try:
            content_sample = self.get_content_sample(sample_size)
            if not content_sample:
                return False
            
            # Try to decode as UTF-8
            content_sample.decode('utf-8')
            
            # Check if it doesn't start with known binary signatures
            is_text = not self.has_magic_signature([
                b'%PDF',           # PDF
                b'PK',             # ZIP-based formats
                b'\xff\xd8\xff',   # JPEG
                b'\x89PNG',        # PNG
                b'GIF8',           # GIF
                b'BM',             # BMP
                b'RIFF'            # RIFF (WebP, etc.)
            ])
            
            self._content_cache[cache_key] = is_text
            return is_text
            
        except UnicodeDecodeError:
            self._content_cache[cache_key] = False
            return False
        except Exception:
            return False
    
    def clear_content_cache(self):
        """Clear the content analysis cache (useful when content changes)."""
        self._content_cache.clear()
    
    @property
    def input_source(self):
        """
        Get the appropriate input source for loaders.
        
        Returns _file_content (BytesIO) if available from URL downloads,
        otherwise returns the file path. This eliminates the need for
        repetitive getattr patterns in loaders.
        """
        return getattr(self, '_file_content', None) or self.path
    
    @property
    def text_content(self):
        """
        Get text content for text-based loaders.
        
        Returns _prepared_text if available from URL downloads,
        otherwise reads from file path. This eliminates the need for
        repetitive patterns in text loaders.
        """
        if hasattr(self, '_prepared_text'):
            return self._prepared_text
        else:
            # Read from file path with proper encoding handling
            try:
                with open(self.path, 'r', encoding='utf-8') as f:
                    return f.read()
            except UnicodeDecodeError:
                with open(self.path, 'r', encoding='latin-1', errors='ignore') as f:
                    return f.read()
    
    def _parse_attachy(self) -> tuple[str, Dict[str, str]]:
        if not self.attachy:
            return "", {}
        
        path_str = self.attachy
        commands_list = [] # Store as list to preserve order, then convert to dict
        
        # Regex to find a command [key:value] at the very END of the string.
        # Value part [^\[\]]* ensures it doesn't jump over other commands or include brackets.
        command_pattern_at_end = re.compile(r"\[([a-zA-Z0-9_-]+):([^\[\]]*)\]$")
        
        # Regex to find shorthand page selection [1,3-5,-1] at the very END of the string.
        # This matches patterns like [3-5], [1,3-5], [1,3-5,-1], etc.
        page_shorthand_pattern = re.compile(r"\[([0-9,-]+)\]$")
        
        temp_path_str = path_str
        while True:
            # First try to match regular [key:value] commands
            match = command_pattern_at_end.search(temp_path_str)
            if match:
                key = match.group(1).strip()
                value = match.group(2).strip()
                commands_list.append((key, value))
                # Update path_str to be the part before the matched command
                temp_path_str = temp_path_str[:match.start()].strip()
                continue
            
            # If no regular command found, try shorthand page selection
            page_match = page_shorthand_pattern.search(temp_path_str)
            if page_match:
                page_value = page_match.group(1).strip()
                # Convert shorthand [3-5] to [pages:3-5]
                commands_list.append(('pages', page_value))
                # Update path_str to be the part before the matched command
                temp_path_str = temp_path_str[:page_match.start()].strip()
                continue
            
            # No more patterns found
            break
        
        # Commands were parsed from right to left, so reverse for correct order in dictionary
        # For multiple commands with the same key, the rightmost one (last parsed) will win due to dict conversion.
        final_commands = dict(reversed(commands_list))
        final_path = temp_path_str.strip()
        
        # If the final_path is empty AND the original attachy string looked like it was ONLY commands
        # (e.g., "\\"[cmd1:val1][cmd2:val2]\\""), this is typically invalid for a path.
        # In such a case, the original string should be treated as the path, with no commands.
        if not final_path and self.attachy.startswith('"["') and self.attachy.endswith('"]') and final_commands:
            return self.attachy, {}
        
        # If the path part itself ends with ']' and doesn't look like a command that was missed,
        # it might be a legitimate filename. Example: "file_with_bracket].txt"
        # If it looks like a malformed command, e.g. "/path/to/file.txt][broken_cmd"
        # current logic takes `final_path` as is. Further validation could be added if needed.
        
        return final_path, final_commands
    
    def __or__(self, verb: Union[Callable, Pipeline]) -> Union['Attachment', 'AttachmentCollection', Pipeline]:
        """Support both immediate application and pipeline creation."""
        if isinstance(verb, Pipeline):
            # Apply pipeline to this attachment
            return verb(self)
        else:
            # Apply single verb
            result = verb(self)
            if result is None:
                result = self
            if isinstance(result, Attachment):
                result.pipeline.append(getattr(verb, '__name__', str(verb)))
            elif isinstance(result, AttachmentCollection):
                # For collections, add the pipeline step to each attachment
                for att in result.attachments:
                    att.pipeline.append(getattr(verb, '__name__', str(verb)))
            return result
    
    def __getattr__(self, name: str):
        """Allow calling adapters as methods on attachments."""
        if name in _adapters:
            def adapter_method(*args, **kwargs):
                adapter_fn = _adapters[name]
                return adapter_fn(self, *args, **kwargs)
            return adapter_method
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")
    
    def __add__(self, other: Union[Callable, 'Pipeline']) -> 'Attachment':
        """Support additive composition for presenters: present.text + present.images"""
        if isinstance(other, (VerbFunction, Pipeline)):
            # Apply the presenter additively (should preserve existing content)
            result = other(self)
            return result if result is not None else self
        else:
            raise TypeError(f"Cannot add {type(other)} to Attachment")
    
    def __repr__(self) -> str:
        # Show shortened base64 for images
        img_info = ""
        if self.images:
            img_count = len([img for img in self.images if img and not img.endswith('_placeholder')])
            if img_count > 0:
                first_img = next((img for img in self.images if img and not img.endswith('_placeholder')), "")
                if first_img:
                    if first_img.startswith('data:image/'):
                        img_preview = f"{first_img[:30]}...{first_img[-10:]}"
                    else:
                        img_preview = f"{first_img[:20]}...{first_img[-10:]}"
                    img_info = f", images=[{img_count} imgs: {img_preview}]"
                else:
                    img_info = f", images={img_count}"
        
        pipeline_str = str(self.pipeline) if self.pipeline else "[]"
        # Truncate long pipeline strings in repr
        if len(pipeline_str) > 100:
            pipeline_str = pipeline_str[:100] + "...]"

        return f"Attachment(path='{self.path}', text={len(self.text)} chars{img_info}, pipeline={pipeline_str})"
    
    def __str__(self) -> str:
        """Return the text content. If empty, provide a placeholder."""
        if self.text:
            return self.text
        elif self._obj is not None:
            # Avoids auto-rendering complex _obj if presenters haven't populated .text
            return f"[Attachment object loaded for '{self.path}', text not yet presented]"
        else:
            return f"[Attachment for '{self.path}', no content loaded or presented]"
    
    def cleanup(self):
        """Clean up any temporary resources associated with this attachment."""
        # Clean up temporary PDF files
        if 'temp_pdf_path' in self.metadata:
            try:
                import os
                temp_path = self.metadata['temp_pdf_path']
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                del self.metadata['temp_pdf_path']
            except Exception:
                # If cleanup fails, just continue
                pass
        
        # Clean up temporary files downloaded from URLs
        if 'temp_file_path' in self.metadata:
            try:
                import os
                temp_path = self.metadata['temp_file_path']
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                del self.metadata['temp_file_path']
            except Exception:
                # If cleanup fails, just continue
                pass
        
        # Close any open file objects
        if hasattr(self._obj, 'close'):
            try:
                self._obj.close()
            except Exception:
                pass
    
    def __del__(self):
        """Destructor to ensure cleanup when attachment is garbage collected."""
        try:
            self.cleanup()
        except Exception:
            # Ignore errors during cleanup in destructor
            pass


# --- REGISTRATION SYSTEM ---

_loaders = {}
_modifiers = {}
_presenters = {}
_adapters = {}
_refiners = {}
_splitters = {}  # Split functions that expand attachments into collections


def loader(match: Callable[[Attachment], bool]):
    """Register a loader function with a match predicate."""
    def decorator(func):
        @wraps(func)
        def wrapper(att: Attachment) -> Attachment:
            """Wrapper that provides centralized error handling and input source handling for all loaders."""
            try:
                # Enhanced: Automatically handle input source detection and preparation
                prepared_att = _prepare_loader_input(att, func.__name__)
                return func(prepared_att)
            except ImportError as e:
                return _create_helpful_error_attachment(att, e, func.__name__)
            except Exception as e:
                # For other errors, check if it's a common issue we can help with
                if 'github.com' in att.path and '/blob/' in att.path:
                    return _create_github_url_error_attachment(att)
                else:
                    # Re-raise other exceptions as they might be legitimate errors
                    raise e
        
        _loaders[func.__name__] = (match, wrapper)
        return wrapper
    return decorator


def _prepare_loader_input(att: Attachment, loader_name: str) -> Attachment:
    """
    Prepare input for loaders by detecting source and setting up appropriate input.
    
    This eliminates repetitive input source detection code from every loader.
    """
    from io import BytesIO
    import tempfile
    import os
    
    # If we have in-memory content from URL morphing, prepare it
    if hasattr(att, '_file_content') and att._file_content:
        att._file_content.seek(0)  # Reset position
        att.metadata[f'{_get_loader_type(loader_name)}_loaded_from'] = 'in_memory_url_content'
        
        # For text loaders, check if content is actually text before trying to decode
        if _is_text_loader(loader_name):
            # Only try to decode if it's likely text content (not binary like images)
            if att.metadata.get('is_binary', False):
                # Don't try to decode binary content as text - this prevents replacement character warnings
                # Let the text loader handle it appropriately (it will likely skip or error)
                att._prepared_text = ''
            else:
                # Convert to text and store in a temporary attribute
                try:
                    content_text = att._file_content.read().decode('utf-8')
                    att._file_content.seek(0)  # Reset for the actual loader
                    att._prepared_text = content_text
                except UnicodeDecodeError:
                    # Only fallback to latin-1 if it's not known binary content
                    att._file_content.seek(0)
                    content_text = att._file_content.read().decode('latin-1', errors='ignore')
                    att._file_content.seek(0)
                    att._prepared_text = content_text
        
        return att
    
    # If we have a response object, prepare it
    elif hasattr(att, '_response') and att._response:
        att.metadata[f'{_get_loader_type(loader_name)}_loaded_from'] = 'response_object'
        
        # Create _file_content from response for binary loaders
        if not _is_text_loader(loader_name):
            att._file_content = BytesIO(att._response.content)
        else:
            # For text loaders, use response.text for proper encoding (this handles encoding correctly)
            att._prepared_text = att._response.text
        
        return att
    
    # Traditional file path - no preparation needed
    else:
        att.metadata[f'{_get_loader_type(loader_name)}_loaded_from'] = 'file_path'
        return att


def _get_loader_type(loader_name: str) -> str:
    """Extract the loader type from the function name for metadata."""
    # Extract the type from loader function names like 'pdf_to_pdfplumber' -> 'pdf'
    type_mappings = {
        'pdf_to_pdfplumber': 'pdf',
        'pptx_to_python_pptx': 'pptx', 
        'docx_to_python_docx': 'docx',
        'excel_to_openpyxl': 'excel',
        'csv_to_pandas': 'csv',
        'text_to_string': 'text',
        'html_to_bs4': 'html',
        'image_to_pil': 'image',
        'zip_to_images': 'zip'
    }
    return type_mappings.get(loader_name, loader_name.split('_')[0])


def _is_text_loader(loader_name: str) -> bool:
    """Check if this is a text-based loader that needs string input."""
    text_loaders = {'text_to_string', 'html_to_bs4', 'csv_to_pandas', 'svg_to_svgdocument', 'eps_to_epsdocument'}
    return loader_name in text_loaders


def modifier(func):
    """Register a modifier function with type dispatch."""
    import inspect
    sig = inspect.signature(func)
    params = list(sig.parameters.values())
    
    if len(params) >= 2:
        type_hint = params[1].annotation
        if type_hint != inspect.Parameter.empty:
            key = func.__name__
            if key not in _modifiers:
                _modifiers[key] = []
            _modifiers[key].append((type_hint, func))
            return func
    
    key = func.__name__
    if key not in _modifiers:
        _modifiers[key] = []
    _modifiers[key].append((None, func))
    return func


def presenter(func=None, *, category=None):
    """Register a presenter function with type dispatch and smart DSL filtering.
    
    Args:
        func: The presenter function to register
        category: Optional explicit category ('text', 'image', or None for auto-detection)
        
    Examples:
        @presenter
        def auto_detected(att, data): ...  # Auto-detects based on what it modifies
        
        @presenter(category='text')
        def explicit_text(att, data): ...  # Explicitly categorized as text
        
        @presenter(category='image') 
        def explicit_image(att, data): ...  # Explicitly categorized as image
    """
    def decorator(func):
        import inspect
        sig = inspect.signature(func)
        params = list(sig.parameters.values())
        
        # Create a smart wrapper that handles DSL command filtering
        @wraps(func)
        def smart_presenter_wrapper(att: Attachment, *args, **kwargs):
            """Smart presenter wrapper that filters based on DSL commands."""
            
            # Get presenter name and category
            presenter_name = func.__name__
            presenter_category = category
            
            # Auto-detect category if not explicitly provided
            if presenter_category is None:
                presenter_category = _detect_presenter_category(func, presenter_name)
            
            # Get DSL commands with cleaner approach
            include_images = att.commands.get('images', 'true').lower() != 'false'  # Images on by default
            
            # Apply image filtering (images can be turned off)
            if not include_images and presenter_category == 'image':
                # Skip image presenters if images are disabled
                return att
            
            # Apply text format filtering ONLY if format is explicitly specified
            # This allows manual pipelines to work as expected while still supporting DSL format commands
            if presenter_category == 'text' and 'format' in att.commands:
                text_format = att.commands['format']  # Only filter if explicitly set
                
                # Normalize format aliases and map to presenter names
                if text_format in ('plain', 'text', 'txt'):
                    preferred_presenter = 'text'
                elif text_format in ('markdown', 'md'):
                    preferred_presenter = 'markdown'
                elif text_format in ('code', 'structured', 'html', 'xml', 'json'):
                    # For code formats, prefer structured presenters, fallback to markdown
                    if presenter_name in ('html', 'xml', 'csv'):
                        # Let structured presenters run for code format
                        preferred_presenter = presenter_name
                    else:
                        preferred_presenter = 'markdown'  # Fallback for code format
                else:
                    preferred_presenter = 'markdown'  # Default
                
                # Check if the preferred presenter exists for this object type
                # If not, allow any text presenter to run (fallback behavior)
                if presenter_name in ('text', 'markdown'):
                    if att._obj is not None:
                        # Check if preferred presenter exists for this object type
                        obj_type = type(att._obj)
                        preferred_exists = False
                        
                        if preferred_presenter in _presenters:
                            for expected_type, handler_fn in _presenters[preferred_presenter]:
                                # Skip fallback handlers (None type) - they don't count as type-specific
                                if expected_type is None:
                                    continue
                                try:
                                    if isinstance(expected_type, str):
                                        expected_class_name = expected_type.split('.')[-1]
                                        if expected_class_name in obj_type.__name__ or obj_type.__name__ == expected_class_name:
                                            preferred_exists = True
                                            break
                                    elif isinstance(att._obj, expected_type):
                                        preferred_exists = True
                                        break
                                except (TypeError, AttributeError):
                                    continue
                        
                        # Only skip if preferred presenter exists AND this isn't the preferred one
                        if preferred_exists and presenter_name != preferred_presenter:
                            return att
                    else:
                        # No object loaded yet, use original filtering logic
                        if presenter_name != preferred_presenter:
                            return att
            
            # If we get here, the presenter should run
            return func(att, *args, **kwargs)
        
        # Register the smart wrapper instead of the original function
        if len(params) >= 2:
            type_hint = params[1].annotation
            if type_hint != inspect.Parameter.empty:
                key = func.__name__
                if key not in _presenters:
                    _presenters[key] = []
                _presenters[key].append((type_hint, smart_presenter_wrapper))
                return smart_presenter_wrapper
        
        key = func.__name__
        if key not in _presenters:
            _presenters[key] = []
        _presenters[key].append((None, smart_presenter_wrapper))
        return smart_presenter_wrapper
    
    # Handle both @presenter and @presenter(category='text') syntax
    if func is None:
        # Called with parameters: @presenter(category='text')
        return decorator
    else:
        # Called without parameters: @presenter
        return decorator(func)


def _detect_presenter_category(func: Callable, presenter_name: str) -> str:
    """Automatically detect presenter category based on function behavior and name.
    
    Returns:
        'text': Presenter that primarily works with text content
        'image': Presenter that primarily works with images  
    """
    
    # Auto-detect based on function name patterns
    text_patterns = ['text', 'markdown', 'csv', 'xml', 'html', 'json', 'yaml', 'summary', 'head', 'metadata']
    image_patterns = ['image', 'thumbnail', 'chart', 'graph', 'plot', 'visual', 'photo', 'picture']
    
    name_lower = presenter_name.lower()
    
    # Check for image patterns first (more specific)
    if any(pattern in name_lower for pattern in image_patterns):
        return 'image'
    
    # Check for text patterns
    if any(pattern in name_lower for pattern in text_patterns):
        return 'text'
    
    # Try to analyze the function source code for hints (best effort)
    try:
        import inspect
        source = inspect.getsource(func)
        
        # Count references to text vs image operations
        text_indicators = source.count('att.text') + source.count('.text ') + source.count('text =')
        image_indicators = source.count('att.images') + source.count('.images') + source.count('images.append')
        
        if image_indicators > text_indicators:
            return 'image'
        elif text_indicators > 0:
            return 'text'
    except:
        # If source analysis fails, fall back to safe default
        pass
    
    # Default to 'text' for unknown presenters (safe default - always runs)
    return 'text'


def adapter(func):
    """Register an adapter function."""
    _adapters[func.__name__] = func
    return func


def refiner(func):
    """Register a refiner function that operates on presented content."""
    _refiners[func.__name__] = func
    return func


def splitter(func):
    """Register a splitter function that expands attachments into collections."""
    import inspect
    sig = inspect.signature(func)
    params = list(sig.parameters.values())
    
    if len(params) >= 2:
        type_hint = params[1].annotation
        if type_hint != inspect.Parameter.empty:
            key = func.__name__
            if key not in _splitters:
                _splitters[key] = []
            _splitters[key].append((type_hint, func))
            return func
    
    key = func.__name__
    if key not in _splitters:
        _splitters[key] = []
    _splitters[key].append((None, func))
    return func


# --- VERB NAMESPACES ---

class VerbFunction:
    """A wrapper for verb functions that supports both direct calls and pipeline creation."""
    
    def __init__(self, func: Callable, name: str, args=None, kwargs=None, is_loader=False):
        self.func = func
        self.name = name
        self.__name__ = name
        self.args = args or ()
        self.kwargs = kwargs or {}
        self.is_loader = is_loader
    
    def __call__(self, *args, **kwargs) -> Union[Attachment, 'VerbFunction']:
        """Support both att | verb() and verb(args) | other_verb patterns."""
        if len(args) == 1 and isinstance(args[0], Attachment) and not kwargs and not self.args and not self.kwargs:
            # Direct application: verb(attachment)
            return self.func(args[0])
        elif len(args) == 1 and isinstance(args[0], Attachment) and (kwargs or self.args or self.kwargs):
            # Apply with stored or provided arguments
            return self._apply_with_args(args[0], *(self.args + args[1:]), **{**self.kwargs, **kwargs})
        elif len(args) == 1 and isinstance(args[0], str) and self.is_loader and not kwargs and not self.args and not self.kwargs:
            # Special case: loader called with string path - create attachment and apply
            att = Attachment(args[0])
            return self.func(att)
        elif args or kwargs:
            # Partial application: verb(arg1, arg2) returns a new VerbFunction with stored args
            return VerbFunction(self.func, self.name, self.args + args, {**self.kwargs, **kwargs}, self.is_loader)
        else:
            # No args, return self for pipeline creation
            return self
    
    def _apply_with_args(self, att: Attachment, *args, **kwargs):
        """Apply the function with additional arguments."""
        
        # Check if the function can accept additional arguments
        import inspect
        sig = inspect.signature(self.func)
        params = list(sig.parameters.values())
        
        # Check if this is an adapter (has *args, **kwargs) vs modifier/presenter (fixed params)
        has_var_args = any(p.kind == p.VAR_POSITIONAL for p in params)
        has_var_kwargs = any(p.kind == p.VAR_KEYWORD for p in params)
        
        if has_var_args and has_var_kwargs:
            # This is an adapter - pass arguments directly
            return self.func(att, *args, **kwargs)
        else:
            # This is a modifier/presenter - set commands and call with minimal args
            if args and hasattr(att, 'commands'):
                # Assume first argument is the command value for this verb
                att.commands[self.name] = str(args[0])
            
            # If function only takes 1 parameter (just att) or 2 parameters (att + obj type),
            # don't pass additional args - the commands are already set
            if len(params) <= 2:
                return self.func(att)
            else:
                # Function can take additional arguments
                return self.func(att, *args, **kwargs)
    
    def __or__(self, other: Union[Callable, Pipeline]) -> Pipeline:
        """Create a pipeline when using | operator."""
        return Pipeline([self]) | other
    
    def __add__(self, other: Union[Callable, 'VerbFunction', Pipeline]) -> 'AdditivePipeline':
        """Create an additive pipeline when using + operator."""
        return AdditivePipeline([self, other])
    
    def __repr__(self) -> str:
        args_str = ""
        if self.args or self.kwargs:
            args_str = f"({', '.join(map(str, self.args))}{', ' if self.args and self.kwargs else ''}{', '.join(f'{k}={v}' for k, v in self.kwargs.items())})"
        return f"VerbFunction({self.name}{args_str})"

class VerbNamespace:
    def __init__(self, registry):
        self._registry = registry
    
    def __getattr__(self, name: str) -> VerbFunction:
        if name in self._registry:
            if isinstance(self._registry[name], tuple):
                wrapper = self._make_loader_wrapper(name)
                return VerbFunction(wrapper, name, is_loader=True)
            elif isinstance(self._registry[name], list):
                wrapper = self._make_dispatch_wrapper(name)
                return VerbFunction(wrapper, name)
            else:
                wrapper = self._make_adapter_wrapper(name)
                return VerbFunction(wrapper, name)
        
        raise AttributeError(f"No verb '{name}' registered")
    
    def _make_loader_wrapper(self, name: str):
        """Create a wrapper that converts strings to Attachments."""
        match_fn, loader_fn = self._registry[name]
        
        @wraps(loader_fn)
        def wrapper(input_: Union[str, Attachment]) -> Attachment:
            if isinstance(input_, str):
                att = Attachment(input_)
            else:
                att = input_
            
            # Skip loading if already loaded (default behavior for all loaders)
            if att._obj is not None:
                return att
            
            if match_fn(att):
                return loader_fn(att)
            else:
                # Skip gracefully if this loader doesn't match - enables chaining
                return att
        
        return wrapper
    
    def _make_dispatch_wrapper(self, name: str):
        """Create a wrapper that dispatches based on object type."""
        handlers = self._registry[name]
        
        # Find a meaningful handler for @wraps (not the fallback)
        meaningful_handler = handlers[0][1]  # Default to first
        for expected_type, handler_fn in handlers:
            if expected_type is not None:  # Skip fallback handlers
                meaningful_handler = handler_fn
                break
        
        @wraps(meaningful_handler)
        def wrapper(att: Attachment) -> Union[Attachment, AttachmentCollection]:
            # Check if this is a splitter function (expects text parameter)
            import inspect
            first_handler = handlers[0][1]
            sig = inspect.signature(first_handler)
            params = list(sig.parameters.values())
            
            # If second parameter is annotated as 'str', this is likely a splitter
            is_splitter = (len(params) >= 2 and 
                          params[1].annotation == str)
            
            if is_splitter:
                # For splitters, pass the text content
                content = att.text if att.text else ""
                
                # Try to find a matching handler based on type annotations
                for expected_type, handler_fn in handlers:
                    if expected_type is None:
                        return handler_fn(att, content)
                    elif expected_type == str:
                        return handler_fn(att, content)
                
                # Fallback to first handler
                return handlers[0][1](att, content)
            
            # Original logic for modifiers/presenters
            if att._obj is None:
                # Use fallback handler
                for expected_type, handler_fn in handlers:
                    if expected_type is None:
                        return handler_fn(att)
                return att
            
            obj_type_name = type(att._obj).__name__
            obj_type_full_name = f"{type(att._obj).__module__}.{type(att._obj).__name__}"
            
            # Try to find a matching handler based on type annotations
            for expected_type, handler_fn in handlers:
                if expected_type is None:
                    continue
                    
                try:
                    # Handle string type annotations with enhanced matching
                    if isinstance(expected_type, str):
                        # Check if it's a regex pattern (starts with r' or contains regex metacharacters)
                        if self._is_regex_pattern(expected_type):
                            if self._match_regex_pattern(obj_type_name, obj_type_full_name, expected_type):
                                return handler_fn(att, att._obj)
                        else:
                            # Try multiple matching strategies for regular type strings
                            
                            # 1. Exact full module.class match
                            if obj_type_full_name == expected_type:
                                return handler_fn(att, att._obj)
                            
                            # 2. Extract class name and try exact match
                            expected_class_name = expected_type.split('.')[-1]
                            if obj_type_name == expected_class_name:
                                return handler_fn(att, att._obj)
                            
                            # 3. Try inheritance check for known patterns
                            if self._check_type_inheritance(att._obj, expected_type):
                                return handler_fn(att, att._obj)
                            
                    elif isinstance(att._obj, expected_type):
                        return handler_fn(att, att._obj)
                except (TypeError, AttributeError):
                    continue
            
            # Fallback to first handler with no type requirement
            for expected_type, handler_fn in handlers:
                if expected_type is None:
                    return handler_fn(att)
            
            return att
        
        return wrapper
    
    def _check_type_inheritance(self, obj, expected_type_str: str) -> bool:
        """Check if object inherits from the expected type using dynamic import."""
        try:
            # Handle common inheritance patterns
            if expected_type_str == 'PIL.Image.Image':
                # Special case for PIL Images - check if it's any PIL Image subclass
                try:
                    from PIL import Image
                    return isinstance(obj, Image.Image)
                except ImportError:
                    return False
            
            # For other types, try to dynamically import and check
            if '.' in expected_type_str:
                module_path, class_name = expected_type_str.rsplit('.', 1)
                try:
                    import importlib
                    module = importlib.import_module(module_path)
                    expected_class = getattr(module, class_name)
                    return isinstance(obj, expected_class)
                except (ImportError, AttributeError):
                    return False
            
            return False
        except Exception:
            return False
    
    def _is_regex_pattern(self, type_str: str) -> bool:
        """Check if a type string is intended as a regex pattern."""
        # Check for explicit regex prefix first
        if type_str.startswith('r\'') or type_str.startswith('r"'):
            return True
        
        # Don't treat normal module.class.name patterns as regex
        # These are common patterns like 'PIL.Image.Image', 'pandas.DataFrame'
        if self._looks_like_module_path(type_str):
            return False
            
        # Check for regex metacharacters that indicate this is actually a regex
        regex_indicators = [
            r'\*',  # Asterisks
            r'\+',  # Plus signs
            r'\?',  # Question marks
            r'\[',  # Character classes
            r'\(',  # Groups
            r'\|',  # Alternation
            r'\$',  # End anchors
            r'\^',  # Start anchors
        ]
        
        # If it contains regex metacharacters, treat as regex
        import re
        for indicator in regex_indicators:
            if re.search(indicator, type_str):
                return True
            
        return False
    
    def _looks_like_module_path(self, type_str: str) -> bool:
        """Check if a string looks like a normal module.class.name path."""
        # Simple heuristic: if it's just alphanumeric, dots, and underscores,
        # and doesn't contain obvious regex metacharacters, treat as module path
        import re
        # Allow letters, numbers, dots, underscores
        if re.match(r'^[a-zA-Z_][a-zA-Z0-9_.]*$', type_str):
            return True
        return False
    
    def _match_regex_pattern(self, obj_type_name: str, obj_type_full_name: str, pattern: str) -> bool:
        """Match object type against a regex pattern."""
        try:
            import re
            
            # Clean up the pattern if it has r' prefix
            clean_pattern = pattern
            if pattern.startswith('r\'') and pattern.endswith('\''):
                clean_pattern = pattern[2:-1]
            elif pattern.startswith('r"') and pattern.endswith('"'):
                clean_pattern = pattern[2:-1]
            
            # Try matching against both short and full type names
            if re.match(clean_pattern, obj_type_name) or re.match(clean_pattern, obj_type_full_name):
                return True
                
            return False
        except Exception:
            return False

    def _make_adapter_wrapper(self, name: str):
        """Create a wrapper for adapter functions."""
        adapter_fn = self._registry[name]
        
        # Don't use @wraps here because it copies the original function's signature,
        # but we need to preserve the *args, **kwargs signature for VerbFunction detection
        def wrapper(att: Attachment, *args, **kwargs):
            # Call the adapter and return result directly (exit the attachment pipeline)
            result = adapter_fn(att, *args, **kwargs)
            return result
        
        # Manually copy some attributes without affecting the signature
        wrapper.__name__ = getattr(adapter_fn, '__name__', name)
        wrapper.__doc__ = getattr(adapter_fn, '__doc__', None)
        
        return wrapper


class SmartVerbNamespace(VerbNamespace):
    """VerbNamespace with __dir__ support for runtime autocomplete."""
    
    def __init__(self, registry):
        super().__init__(registry)

    def __dir__(self):
        """Return list of attributes for IDE autocomplete."""
        # Get the default attributes
        attrs = set(object.__dir__(self))
        
        # Add all registered function names
        attrs.update(self._registry.keys())
        
        return sorted(attrs)

    @property
    def __all__(self):
        """Provide __all__ for static analysis tools."""
        return list(self._registry.keys())

    def register_new_function(self, name):
        """Call this when dynamically adding new functions."""
        # Functions will be accessible via __getattr__
        pass


# Helper functions for convenient attachment creation
def attach(path: str) -> Attachment:
    """Create an Attachment from a file path."""
    return Attachment(path)

def A(path: str) -> Attachment:
    """Short alias for attach()."""
    return Attachment(path)


def _create_helpful_error_attachment(att: Attachment, import_error: ImportError, loader_name: str) -> Attachment:
    """Create a helpful error attachment for missing dependencies."""
    error_msg = str(import_error).lower()
    
    # Map common import errors to helpful messages
    dependency_map = {
        'requests': {
            'packages': ['requests'],
            'description': 'Download files from URLs and access web content',
            'use_case': 'URL processing'
        },
        'beautifulsoup4': {
            'packages': ['beautifulsoup4'],
            'description': 'Parse HTML and extract content from web pages',
            'use_case': 'Web scraping and HTML parsing'
        },
        'bs4': {
            'packages': ['beautifulsoup4'],
            'description': 'Parse HTML and extract content from web pages', 
            'use_case': 'Web scraping and HTML parsing'
        },
        'pandas': {
            'packages': ['pandas'],
            'description': 'Process CSV files and structured data',
            'use_case': 'Data analysis and CSV processing'
        },
        'pil': {
            'packages': ['Pillow'],
            'description': 'Process images (resize, rotate, convert formats)',
            'use_case': 'Image processing'
        },
        'pillow': {
            'packages': ['Pillow'],
            'description': 'Process images (resize, rotate, convert formats)',
            'use_case': 'Image processing'
        },
        'pillow-heif': {
            'packages': ['pillow-heif'],
            'description': 'Support HEIC/HEIF image formats from Apple devices',
            'use_case': 'HEIC image processing'
        },
        'pptx': {
            'packages': ['python-pptx'],
            'description': 'Process PowerPoint presentations',
            'use_case': 'PowerPoint processing'
        },
        'python-pptx': {
            'packages': ['python-pptx'],
            'description': 'Process PowerPoint presentations',
            'use_case': 'PowerPoint processing'
        },
        'docx': {
            'packages': ['python-docx'],
            'description': 'Process Word documents',
            'use_case': 'Word document processing'
        },
        'openpyxl': {
            'packages': ['openpyxl'],
            'description': 'Process Excel spreadsheets',
            'use_case': 'Excel processing'
        },
        'pdfplumber': {
            'packages': ['pdfplumber'],
            'description': 'Extract text and tables from PDF files',
            'use_case': 'PDF processing'
        },
        'zipfile': {
            'packages': [],  # Built-in module
            'description': 'Process ZIP archives',
            'use_case': 'Archive processing'
        }
    }
    
    # Find which dependency is missing
    missing_deps = []
    descriptions = []
    use_cases = []
    
    for dep_name, info in dependency_map.items():
        if dep_name in error_msg:
            if info['packages']:  # Skip built-in modules
                missing_deps.extend(info['packages'])
                descriptions.append(info['description'])
                use_cases.append(info['use_case'])
    
    # Remove duplicates while preserving order
    missing_deps = list(dict.fromkeys(missing_deps))
    descriptions = list(dict.fromkeys(descriptions))
    use_cases = list(dict.fromkeys(use_cases))
    
    # Fallback if we can't identify the specific dependency
    if not missing_deps:
        missing_deps = ['required-package']
        descriptions = ['process this file type']
        use_cases = ['file processing']
    
    deps_str = ' '.join(missing_deps)
    description = ', '.join(descriptions)
    use_case = ', '.join(use_cases)
    
    att.text = f"""🚫 **Missing Dependencies for {use_case.title()}**

**File:** `{att.path}`
**Loader:** `{loader_name}`
**Issue:** Cannot process this file because required packages are not installed.

**Quick Fix:**
```bash
pip install {deps_str}
```

**Or with uv:**
```bash
uv pip install {deps_str}
```

**What this enables:**
{description}

**Alternative Solutions:**
1. Install the optional dependencies: `pip install attachments[all]`
2. Use a different file format if possible
3. Convert the file to a supported format

**Original Error:** {str(import_error)}
"""
    
    att.metadata.update({
        'error_type': 'missing_dependencies',
        'helpful_error': True,
        'missing_packages': missing_deps,
        'loader_name': loader_name,
        'original_error': str(import_error)
    })
    return att


def _create_github_url_error_attachment(att: Attachment) -> Attachment:
    """Create a helpful error attachment for GitHub blob URLs."""
    raw_url = att.path.replace('/blob/', '/raw/')
    
    att.text = f"""💡 **GitHub URL Detected**

**Original URL:** `{att.path}`
**Suggested Raw URL:** `{raw_url}`

**Issue:** GitHub blob URLs show the file viewer, not the raw file content.

**Quick Fix:** Use the raw URL instead:
```python
from attachments import Attachments
ctx = Attachments("{raw_url}")
```

**Why this happens:**
- GitHub blob URLs (with `/blob/`) show the file in GitHub's web interface
- Raw URLs (with `/raw/`) provide direct access to file content
- Attachments needs direct file access to process content

**Alternative:** Download the file locally and use the local path instead.
"""
    
    att.metadata.update({
        'error_type': 'github_url',
        'helpful_error': True,
        'suggested_url': raw_url,
        'original_url': att.path
    })
    return att


