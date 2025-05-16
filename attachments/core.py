import os
import re
from urllib.parse import urlparse # Added for URL parsing
import requests                   # Added for downloading URLs
import tempfile                   # Added for temporary file handling
import io                         # For in-memory byte streams (image base64 encoding)
import base64                     # For base64 encoding
from PIL import Image

from .detectors import Detector
from .parsers import ParserRegistry, PDFParser, PPTXParser, HTMLParser, ImageParser
from .renderers import RendererRegistry, DefaultXMLRenderer, PlainTextRenderer
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
        
        # Register ImageParser for various image types
        image_parser = ImageParser()
        self.parser_registry.register('jpeg', image_parser)
        self.parser_registry.register('png', image_parser)
        self.parser_registry.register('gif', image_parser)
        self.parser_registry.register('bmp', image_parser)
        self.parser_registry.register('webp', image_parser)
        self.parser_registry.register('tiff', image_parser)
        
        # Register renderers
        self.renderer_registry.register('xml', DefaultXMLRenderer(), default=True) # Make DefaultXMLRenderer the default
        self.renderer_registry.register('text', PlainTextRenderer()) 

    def _parse_path_string(self, path_str):
        """Parses a path string which might include slicing indices.
        Example: "path/to/file.pdf[:10, -3:]"
        Returns: (file_path, indices_str or None)
        """
        # Regex to capture path and optional slice part (e.g. [...])
        match = re.match(r'(.+?)(\[.*\])?$', path_str)
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
    
    @property
    def images(self):
        """Returns a list of base64 encoded image strings suitable for LLM APIs.
        Each string is in the format: data:image/<format>;base64,<encoded_data>
        """
        base64_images = []
        image_item_types = ['jpeg', 'png', 'gif', 'bmp', 'webp', 'tiff'] # Types considered images

        for item_data in self.attachments_data:
            if item_data.get('type') in image_item_types and 'image_object' in item_data:
                img_obj = item_data['image_object']
                output_format = item_data.get('output_format', 'jpeg').lower()
                # Ensure format is pillow-compatible (jpg -> jpeg)
                if output_format == 'jpg': 
                    output_format = 'jpeg' 
                
                quality = item_data.get('output_quality', 90)
                
                # Handle Pillow format compatibility for saving (e.g. Pillow saves as JPEG not JPG)
                pillow_save_format = output_format.upper()
                if pillow_save_format == "JPG": pillow_save_format = "JPEG"

                # Some modes are not directly saveable in all formats (e.g. P mode for JPEG)
                # Convert to RGB/RGBA before saving if necessary, based on output format
                save_img = img_obj
                if pillow_save_format == 'JPEG':
                    if save_img.mode == 'RGBA' or save_img.mode == 'LA': # JPEG doesn't support alpha
                        save_img = save_img.convert('RGB')
                    elif save_img.mode == 'P': # Palette mode
                         save_img = save_img.convert('RGB') 
                elif pillow_save_format == 'PNG':
                    if save_img.mode not in ['RGB', 'RGBA', 'L', 'P']: # PNG supports these
                         save_img = save_img.convert('RGBA') # Convert to RGBA to be safe for PNG
                
                try:
                    buffered = io.BytesIO()
                    save_params = {}
                    if pillow_save_format == 'JPEG':
                        save_params['quality'] = quality
                        save_params['optimize'] = True # Good to have
                    elif pillow_save_format == 'PNG':
                        save_params['optimize'] = True
                    # WEBP also supports quality
                    elif pillow_save_format == 'WEBP':
                        save_params['quality'] = quality

                    save_img.save(buffered, format=pillow_save_format, **save_params)
                    img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
                    
                    # Determine MIME type for the data URI
                    mime_type = f"image/{output_format}"
                    
                    base64_images.append(f"data:{mime_type};base64,{img_base64}")
                except Exception as e_save_b64:
                    print(f"Warning: Could not convert image {item_data.get('file_path', 'unknown')} to base64 (format: {output_format}): {e_save_b64}")
        return base64_images

    def render(self, renderer_name=None):
        """Renders the processed attachments using a specified or default renderer."""
        renderer = self.renderer_registry.get_renderer(renderer_name)
        return renderer.render(self.attachments_data)

    def __str__(self):
        """String representation uses the default renderer (now DefaultXMLRenderer)."""
        return self.render() 

    def __repr__(self):
        """Return an unambiguous string representation of the Attachments object."""
        if not self.original_paths_with_indices:
            return "Attachments()"
        # Use repr() for each path string to correctly escape quotes if they are part of the path
        path_reprs = [repr(p) for p in self.original_paths_with_indices]
        return f"Attachments({', '.join(path_reprs)})"

    def _repr_markdown_(self):
        """Return a Markdown representation for IPython/Jupyter.
        Displays images and provides summaries for other file types.
        """
        if not self.attachments_data:
            return "_No attachments processed._"

        md_parts = ["### Attachments Summary"]
        image_item_types = ['jpeg', 'png', 'gif', 'bmp', 'webp', 'tiff']

        # Pre-generate base64 for all images in one go if needed, or do it one by one
        # For simplicity here, let's iterate and generate/retrieve as needed.
        # We could map item IDs or original_path_str to their base64 from self.images if that property always reflects the latest state.
        # However, self.images applies default conversions. For _repr_markdown_ we might want a small standard thumbnail.
        # Let's refine this: generate a small thumbnail for display.

        for i, item in enumerate(self.attachments_data):
            item_id = item.get('id', f'item{i+1}')
            item_type = item.get('type', 'N/A')
            original_path_str = item.get('original_path_str', 'N/A')
            processed_file_path = item.get('file_path', 'N/A') # This is original_file_path_or_url
            
            md_parts.append(f"**ID:** `{item_id}` (`{item_type}` from `{original_path_str}`)")

            if item_type in image_item_types and 'image_object' in item:
                img_obj = item['image_object'] # This is the (potentially transformed by user ops) image
                temp_img_for_display = img_obj.copy() # Work on a copy for thumbnailing
                
                # Create a thumbnail for display, e.g., max width 200px
                # This uses the same resampling as resize, but could be a simpler one for speed.
                max_thumb_width = 200 
                current_w, current_h = temp_img_for_display.size
                if current_w > max_thumb_width:
                    aspect_ratio = current_h / current_w
                    thumb_h = int(max_thumb_width * aspect_ratio)
                    temp_img_for_display.thumbnail((max_thumb_width, thumb_h), Image.Resampling.LANCZOS)
                
                # Determine a suitable format for embedding (PNG for alpha, otherwise JPEG)
                thumb_output_format = 'png' if temp_img_for_display.mode == 'RGBA' else 'jpeg'
                pillow_save_format = thumb_output_format.upper()
                
                save_img_for_display = temp_img_for_display
                if pillow_save_format == 'JPEG' and save_img_for_display.mode == 'RGBA':
                    save_img_for_display = save_img_for_display.convert('RGB')
                elif pillow_save_format == 'PNG' and save_img_for_display.mode not in ['RGB', 'RGBA', 'L', 'P']:
                    save_img_for_display = save_img_for_display.convert('RGBA')

                try:
                    buffered = io.BytesIO()
                    save_params_thumb = {'optimize': True}
                    if pillow_save_format == 'JPEG': save_params_thumb['quality'] = 75 # Slightly lower for thumbs
                    
                    save_img_for_display.save(buffered, format=pillow_save_format, **save_params_thumb)
                    img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
                    mime_type = f"image/{thumb_output_format}"
                    alt_text = os.path.basename(processed_file_path)
                    md_parts.append(f"![{alt_text}](data:{mime_type};base64,{img_base64})")
                    md_parts.append(f"  *Original Dimensions: {item.get('width')}x{item.get('height')} {item.get('original_format', '')} {item.get('original_mode', '')}*"+
                                      (f", Operations: `{item.get('applied_operations')}`" if item.get('applied_operations') else "") + 
                                      f", Output as: `{item.get('output_format')}`")

                except Exception as e_repr_md_img:
                    md_parts.append(f"  *Error generating image preview: {e_repr_md_img}*")
            else:
                # Textual summary for non-image types or images without objects
                md_parts.append(f"  - **Processed File Path:** `{processed_file_path}`")
                total_pages_or_slides = item.get('num_pages') or item.get('num_slides')
                indices_processed = item.get('indices_processed')
                
                if total_pages_or_slides is not None:
                    item_label = "Pages" if 'num_pages' in item else "Slides"
                    if indices_processed and len(indices_processed) != total_pages_or_slides:
                        md_parts.append(f"  - **Processed {item_label}:** `{', '.join(map(str, indices_processed))}` (Total: {total_pages_or_slides})")
                    else:
                        md_parts.append(f"  - **Total {item_label}:** `{total_pages_or_slides}` (All processed)")
                
                text_snippet = item.get('text', '')[:150].replace('\n', ' ') 
                if text_snippet:
                    quoted_snippet_with_ellipsis = f'"{text_snippet}..."'
                    md_parts.append(f"  - **Content Snippet:** `{quoted_snippet_with_ellipsis}`")
            md_parts.append("---") # Separator

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