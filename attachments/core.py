import os
import re
from urllib.parse import urlparse # Added for URL parsing
import requests                   # Added for downloading URLs
import tempfile                   # Added for temporary file handling

from .detectors import Detector
from .parsers import ParserRegistry, PDFParser, PPTXParser, HTMLParser
from .renderers import RendererRegistry, DefaultXMLRenderer
from .exceptions import DetectionError, ParsingError

class Attachments:
    """Core class for handling attachments."""
    def __init__(self, *paths):
        self.detector = Detector()
        self.parser_registry = ParserRegistry()
        self.renderer_registry = RendererRegistry()
        self._register_default_components()

        self.attachments_data = []
        # Store the original path specifications for __repr__
        self.original_paths_with_indices = [] 
        if paths:
            if isinstance(paths[0], list):
                self.original_paths_with_indices = list(paths[0])
            else:
                self.original_paths_with_indices = list(paths)
        
        self._process_paths(self.original_paths_with_indices) # Pass the stored list

    def _register_default_components(self):
        """Registers default parsers and renderers."""
        self.parser_registry.register('pdf', PDFParser())
        self.parser_registry.register('pptx', PPTXParser())
        self.parser_registry.register('html', HTMLParser())
        self.renderer_registry.register('default_xml', DefaultXMLRenderer(), default=True)

    def _parse_path_string(self, path_str):
        """Parses a path string which might include slicing indices.
        Example: "path/to/file.pdf[:10, -3:]"
        Returns: (file_path, indices_str or None)
        """
        # Regex to capture path and optional slice part (e.g. [...])
        match = re.match(r'(.+?)(\\[.*\\])?$', path_str)
        if not match:
            # If no match (e.g. empty string or malformed), return the original string stripped
            # and None for indices. This handles empty path_str gracefully.
            return path_str.strip(), None 
        
        file_path = match.group(1).strip() # Strip whitespace from the path part
        indices_str = match.group(2)
        
        if indices_str:
            # Remove the outer brackets for the parser
            indices_str = indices_str[1:-1]
            # It's also good practice to strip the content of indices_str, 
            # though parse_index_string might handle internal spaces.
            indices_str = indices_str.strip() 
            
        return file_path, indices_str

    def _process_paths(self, paths_to_process):
        """Processes a list of path strings, which can be local files or URLs."""
        
        for i, path_str in enumerate(paths_to_process):
            if not isinstance(path_str, str):
                print(f"Warning: Item '{path_str}' is not a string path and will be skipped.")
                continue

            file_path, indices = self._parse_path_string(path_str)
            
            is_url = False
            temp_file_path_for_parsing = None # Path to the temporary file if URL is downloaded
            original_file_path_or_url = file_path # This will be stored in parsed_content['file_path']

            try:
                parsed_url = urlparse(file_path)
                if parsed_url.scheme in ('http', 'https', 'ftp'):
                    is_url = True
            except ValueError: # Handle cases where file_path might be an invalid URL causing urlparse to fail
                is_url = False

            if is_url:
                try:
                    print(f"Attempting to download content from URL: {file_path}")
                    response = requests.get(file_path, stream=True, timeout=10)
                    response.raise_for_status()

                    # Get Content-Type header
                    content_type_header = response.headers.get('Content-Type')
                    print(f"URL {file_path} has Content-Type: {content_type_header}")

                    url_path_for_ext = parsed_url.path
                    _, potential_ext = os.path.splitext(url_path_for_ext)
                    
                    with tempfile.NamedTemporaryFile(delete=False, suffix=potential_ext or None, mode='wb') as tmp_file:
                        for chunk in response.iter_content(chunk_size=8192):
                            tmp_file.write(chunk)
                        temp_file_path_for_parsing = tmp_file.name
                    
                    print(f"Successfully downloaded URL {file_path} to temporary file: {temp_file_path_for_parsing}")
                    path_for_detector_and_parser = temp_file_path_for_parsing
                
                except requests.exceptions.RequestException as e_req:
                    print(f"Warning: Failed to download URL '{file_path}': {e_req}. Skipping.")
                    continue # Skip to next path_str
                except Exception as e_url_handle: # Catch any other errors during temp file handling
                    print(f"Warning: An unexpected error occurred while handling URL '{file_path}': {e_url_handle}. Skipping.")
                    if temp_file_path_for_parsing and os.path.exists(temp_file_path_for_parsing):
                         os.remove(temp_file_path_for_parsing) # Clean up if temp file was created before error
                    continue
            else: # It's a local path
                if not os.path.exists(file_path):
                    print(f"Warning: File '{file_path}' not found and will be skipped.")
                    continue
                path_for_detector_and_parser = file_path

            # --- Common processing logic for local files or downloaded URL content --- 
            try:
                # Pass content_type_header if it's a URL and we got it
                detected_file_type_arg = None
                if is_url and 'content_type_header' in locals() and content_type_header:
                    detected_file_type_arg = content_type_header
                
                file_type = self.detector.detect(path_for_detector_and_parser, content_type=detected_file_type_arg)
                
                if not file_type:
                    print(f"Warning: Could not detect file type for '{path_for_detector_and_parser}' (from input '{path_str}'). Skipping.")
                    continue

                parser = self.parser_registry.get_parser(file_type)
                parsed_content = parser.parse(path_for_detector_and_parser, indices=indices)
                
                parsed_content['type'] = file_type
                parsed_content['id'] = f"{file_type}{i+1}" # Simple unique ID
                parsed_content['original_path_str'] = path_str 
                # Store the original URL or local file path, not the temp file path, for user reference.
                parsed_content['file_path'] = original_file_path_or_url 
                
                self.attachments_data.append(parsed_content)

            except ValueError as e_parser_val: # Raised by get_parser if type not found
                print(f"Warning: {e_parser_val} Skipping input '{path_str}'.")
            except ParsingError as e_parse:
                print(f"Error parsing input '{path_str}': {e_parse}. Skipping.")
            except Exception as e_proc: # Catch-all for other processing errors
                print(f"An unexpected error occurred processing input '{path_str}': {e_proc}. Skipping.")
            
            finally:
                # Clean up the temporary file if one was created for a URL
                if is_url and temp_file_path_for_parsing and os.path.exists(temp_file_path_for_parsing):
                    try:
                        os.remove(temp_file_path_for_parsing)
                        print(f"Cleaned up temporary file: {temp_file_path_for_parsing}")
                    except Exception as e_clean:
                        print(f"Warning: Could not clean up temporary file {temp_file_path_for_parsing}: {e_clean}")
    
    def render(self, renderer_name=None):
        """Renders the processed attachments using a specified or default renderer."""
        renderer = self.renderer_registry.get_renderer(renderer_name)
        return renderer.render(self.attachments_data)

    def __str__(self):
        """String representation uses the default renderer."""
        return self.render()

    def __repr__(self):
        """Return an unambiguous string representation of the Attachments object."""
        if not self.original_paths_with_indices:
            return "Attachments()"
        # Use repr() for each path string to correctly escape quotes if they are part of the path
        path_reprs = [repr(p) for p in self.original_paths_with_indices]
        return f"Attachments({', '.join(path_reprs)})"

    def _repr_markdown_(self):
        """Return a Markdown representation for IPython/Jupyter."""
        if not self.attachments_data:
            return "_No attachments processed._"

        md_parts = ["### Attachments Summary"]
        for item in self.attachments_data:
            md_parts.append(f"- **ID:** `{item.get('id', 'N/A')}`")
            md_parts.append(f"  - **Type:** `{item.get('type', 'N/A')}`")
            md_parts.append(f"  - **Original Input:** `{item.get('original_path_str', 'N/A')}`")
            md_parts.append(f"  - **Processed File Path:** `{item.get('file_path', 'N/A')}`")
            
            total_pages_or_slides = item.get('num_pages') or item.get('num_slides')
            indices_processed = item.get('indices_processed')
            
            if total_pages_or_slides is not None:
                item_label = "Pages" if 'num_pages' in item else "Slides"
                if indices_processed and len(indices_processed) != total_pages_or_slides:
                    md_parts.append(f"  - **Processed {item_label}:** `{', '.join(map(str, indices_processed))}` (Total in file: {total_pages_or_slides})")
                else:
                    md_parts.append(f"  - **Total {item_label} in File:** `{total_pages_or_slides}` (All processed)")
            else: # Should not happen if parser works correctly
                 md_parts.append(f"  - **Pages/Slides:** _Data not available_")
            
            # Add a small snippet of text content if available
            text_snippet = item.get('text', '')[:100].replace('\n', ' ') # First 100 chars, newlines to spaces
            if text_snippet:
                # Construct the quoted snippet part separately to avoid f-string quote confusion
                quoted_snippet_with_ellipsis = f'"{text_snippet}..."'
                md_parts.append(f"  - **Content Snippet:** `{quoted_snippet_with_ellipsis}`")
            md_parts.append("") # Add a blank line for spacing between entries

        return "\n".join(md_parts)
    
    def set_renderer(self, renderer_instance_or_name):
        """Sets the default renderer for this Attachments instance."""
        if isinstance(renderer_instance_or_name, str):
            # This assumes the renderer is already registered in the global/instance registry
            self.renderer_registry.set_default_renderer(renderer_instance_or_name)
        elif isinstance(renderer_instance_or_name, self.renderer_registry.renderers[next(iter(self.renderer_registry.renderers))].__class__.__bases__[0]): # Bit hacky check for BaseRenderer
            # If it's an instance, we might want to register it if it's not already
            # For now, just set it as default directly on the instance's registry
            # This part needs to align with how RendererRegistry handles external instances.
            # A simpler approach: renderer_registry.register("custom_temp", renderer_instance_or_name, default=True)
            # Or expect users to register it first.
            self.renderer_registry.default_renderer = renderer_instance_or_name # Direct override
        else:
            raise TypeError("Invalid type for renderer. Must be a registered renderer name or a BaseRenderer instance.")

    # Placeholder for future methods like pipe, save_config, load_config
    def pipe(self, custom_preprocess_func):
        # To be implemented
        # This would likely iterate over self.attachments_data and apply the function
        print(f"Piping with {custom_preprocess_func}")
        return self

    def save_config(self, config_path):
        # To be implemented
        print(f"Saving config to {config_path}")

    def load_config(self, config_path):
        # To be implemented
        print(f"Loading config from {config_path}") 