import os
import re
from urllib.parse import urlparse # Added for URL parsing
import requests                   # Added for downloading URLs
import tempfile                   # Added for temporary file handling
import io                         # For in-memory byte streams (image base64 encoding)
import base64                     # For base64 encoding
from PIL import Image
import mimetypes # For guessing MIME types
from typing import List, Dict, Tuple, Optional, Any, Union, cast
from collections import defaultdict

from .detectors import Detector
from .parsers import ParserRegistry, PDFParser, PPTXParser, HTMLParser, ImageParser, AudioParser, DOCXParser, ODTParser
from .renderers import RendererRegistry, DefaultXMLRenderer, PlainTextRenderer
from .exceptions import DetectionError, ParsingError
from .image_processing import DEFAULT_IMAGE_OUTPUT_FORMAT, DEFAULT_IMAGE_QUALITY
from .config import Config as ActualConfig

# Provide a default gemeinsame_config if not already defined elsewhere
gemeinsame_config = ActualConfig()

class Attachments:
    """Core class for handling attachments."""
    def __init__(self, *paths_or_urls, config: Optional['ActualConfig'] = None, **kwargs):
        self._config = gemeinsame_config if config is None else config
        self.parser_registry = ParserRegistry() # Use a single registry instance
        self.renderer_registry = RendererRegistry() # Initialize renderer registry
        self.detector = Detector() # Initialize detector
        self._register_default_components() # Register default parsers and renderers
        # Ensure custom parsers from config are registered if provided
        if getattr(self._config, "CUSTOM_PARSERS", None):
            for key, parser_class in self._config.CUSTOM_PARSERS.items():
                self.parser_registry.register(key, parser_class)
        
        self.attachments_data: List[Dict[str, Any]] = []
        self._unprocessed_inputs: List[Tuple[str, str]] = [] # Reinstate this line
        self._ids = set() # To ensure unique IDs
        self._next_id_counters = defaultdict(int) # For generating type-specific IDs like pdf1, image1
        self.verbose = kwargs.get('verbose', False) # Capture verbose for potential use

        # Determine the actual list of path strings to process and for internal state
        _paths_for_processing_and_internal_state: List[str]
        
        if len(paths_or_urls) == 1 and isinstance(paths_or_urls[0], (list, tuple)):
            # Case: Attachments(["path1", "path2"]) or Attachments(("path1", "path2"))
            # We expect paths_or_urls[0] to be an iterable of strings.
            # _process_paths will validate each item later.
            _paths_for_processing_and_internal_state = list(paths_or_urls[0])
        else:
            # Case: Attachments("path1", "path2", ...) or Attachments()
            # paths_or_urls is already a tuple of the items.
            _paths_for_processing_and_internal_state = list(paths_or_urls)

        self.original_paths_with_indices = _paths_for_processing_and_internal_state

        if self.original_paths_with_indices: # Check the attribute that's now consistently a flat list
            self._process_paths(self.original_paths_with_indices) # Process using this flat list

    def _register_default_components(self):
        """Registers default parsers and renderers."""
        self.parser_registry.register('pdf', PDFParser())
        self.parser_registry.register('pptx', PPTXParser())
        self.parser_registry.register('html', HTMLParser())
        
        # Register DOCX and ODT Parsers
        self.parser_registry.register('docx', DOCXParser())
        self.parser_registry.register('odt', ODTParser())
        
        # Register ImageParser for various image types
        image_parser = ImageParser(config=self._config)
        self.parser_registry.register('jpeg', image_parser)
        self.parser_registry.register('png', image_parser)
        self.parser_registry.register('gif', image_parser)
        self.parser_registry.register('bmp', image_parser)
        self.parser_registry.register('webp', image_parser)
        self.parser_registry.register('tiff', image_parser)
        self.parser_registry.register('heic', image_parser)
        self.parser_registry.register('heif', image_parser)
        
        # Register AudioParser for audio types
        audio_parser = AudioParser()
        audio_types = ['flac', 'm4a', 'mp3', 'mp4_audio', 'mpeg_audio', 'oga', 'ogg_audio', 'wav', 'webm_audio']
        for atype in audio_types:
            self.parser_registry.register(atype, audio_parser)
        
        # Register renderers
        self.renderer_registry.register('xml', DefaultXMLRenderer(), default=True) # Make DefaultXMLRenderer the default
        self.renderer_registry.register('text', PlainTextRenderer()) 

    def _parse_path_string(self, path_str):
        """Parses a path string which might include slicing indices.
        Example: "path/to/file.pdf[:10, -3:]"
        Returns: (file_path, indices_str or None)
        """
        match = re.match(r'(.+?)(\[.*\])?$', path_str)
        if not match:
            return path_str.strip(), None 
        
        file_path = match.group(1).strip() 
        indices_str = match.group(2)
        
        if indices_str:
            indices_str = indices_str[1:-1]
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
            temp_file_path_for_parsing = None 
            original_file_path_or_url = file_path 

            try:
                parsed_url = urlparse(file_path)
                if parsed_url.scheme in ('http', 'https', 'ftp'):
                    is_url = True
            except ValueError: 
                is_url = False

            if is_url:
                try:
                    if self.verbose:
                        print(f"Attempting to download content from URL: {file_path}")
                    
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
                        'Accept-Encoding': 'gzip, deflate', 
                    }
                    response = requests.get(file_path, stream=True, timeout=10, headers=headers)
                    response.raise_for_status()

                    content_type_header = response.headers.get('Content-Type')
                    if self.verbose:
                        print(f"URL {file_path} has Content-Type: {content_type_header}")

                    url_path_for_ext = parsed_url.path
                    _, potential_ext = os.path.splitext(url_path_for_ext)
                    
                    with tempfile.NamedTemporaryFile(delete=False, suffix=potential_ext or None, mode='wb') as tmp_file:
                        for chunk in response.iter_content(chunk_size=8192):
                            tmp_file.write(chunk)
                        temp_file_path_for_parsing = tmp_file.name
                    
                    if self.verbose:
                        print(f"Successfully downloaded URL {file_path} to temporary file: {temp_file_path_for_parsing}")
                    path_for_detector_and_parser = temp_file_path_for_parsing
                
                except requests.RequestException as e_req:
                    print(f"Warning: Failed to download URL '{file_path}': {e_req}. Skipping.")
                    continue 
                except Exception as e_url_handle: 
                    print(f"Warning: An unexpected error occurred while handling URL '{file_path}': {e_url_handle}. Skipping.")
                    if temp_file_path_for_parsing and os.path.exists(temp_file_path_for_parsing):
                         os.remove(temp_file_path_for_parsing) 
                    continue
            else: 
                # This block is for local file paths
                if not os.path.exists(file_path):
                    print(f"Warning: File '{file_path}' not found and will be skipped.")
                    continue
                # If we are here, the local file exists
                path_for_detector_and_parser = file_path

            try:
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
                parsed_content['id'] = f"{file_type}{i+1}" 
                parsed_content['original_path_str'] = path_str 
                parsed_content['file_path'] = original_file_path_or_url 

                known_audio_types = ['flac', 'm4a', 'mp3', 'mp4_audio', 'mpeg_audio', 'oga', 'ogg_audio', 'wav', 'webm_audio']
                if file_type in known_audio_types:
                    parsed_content['original_format'] = file_type # Add original_format for audio
                    if 'original_basename' not in parsed_content: # Fallback if parser didn't provide it
                         parsed_content['original_basename'] = os.path.basename(original_file_path_or_url)
                    
                    mime_type = None
                    # 1. From Content-Type header (for URLs)
                    if is_url and 'content_type_header' in locals() and content_type_header:
                        header_mime = content_type_header.split(';')[0].strip().lower()
                        if header_mime and header_mime != 'application/octet-stream':
                            mime_type = header_mime
                    
                    # 2. From mimetypes.guess_type() if not determined by header
                    if not mime_type:
                        guessed_mime, _ = mimetypes.guess_type(original_file_path_or_url)
                        if guessed_mime and guessed_mime != 'application/octet-stream':
                            mime_type = guessed_mime

                    # 3. Apply specific overrides if Detector identified a specific audio type
                    #    This ensures our desired audio MIME takes precedence if guess was generic or video-related.
                    specific_audio_mime_map = {
                        'mp3': 'audio/mpeg', 
                        'm4a': 'audio/m4a', # mimetypes might say audio/mp4, which is also fine for .m4a
                        'mp4_audio': 'audio/mp4',
                        'wav': 'audio/wav', 
                        'flac': 'audio/flac', 
                        'ogg_audio': 'audio/ogg',
                        'oga': 'audio/ogg', 
                        'webm_audio': 'audio/webm', 
                        'mpeg_audio': 'audio/mpeg'
                    }

                    if file_type in specific_audio_mime_map:
                        preferred_mime = specific_audio_mime_map[file_type]
                        # Override if:
                        # - current mime_type is a video type for an _audio classified file_type
                        # - current mime_type is 'audio/x-wav' and we prefer 'audio/wav'
                        # - no mime_type was determined yet
                        # - current mime_type is different from preferred and not an accepted alternative (e.g. audio/mp4 for m4a)
                        if (mime_type and mime_type.startswith('video/') and file_type.endswith('_audio')) or \
                           (file_type == 'wav' and mime_type == 'audio/x-wav') or \
                           (not mime_type) or \
                           (mime_type != preferred_mime and not (file_type == 'm4a' and mime_type == 'audio/mp4')):
                            mime_type = preferred_mime
                    
                    parsed_content['mime_type'] = mime_type if mime_type else 'application/octet-stream'

                self.attachments_data.append(parsed_content)

            except ValueError as e_parser_val: 
                print(f"Warning: {e_parser_val} Skipping input '{path_str}'.")
            except ParsingError as e_parse:
                print(f"Error parsing input '{path_str}': {e_parse}. Skipping.")
            except Exception as e:
                print(f"An unexpected error occurred processing input '{path_str}': {e}. Skipping.")
            
            finally:
                if is_url and temp_file_path_for_parsing and os.path.exists(temp_file_path_for_parsing):
                    try:
                        os.remove(temp_file_path_for_parsing)
                        if self.verbose:
                            print(f"Cleaned up temporary file: {temp_file_path_for_parsing}")
                    except Exception as e_clean:
                        print(f"Warning: Could not clean up temporary file {temp_file_path_for_parsing}: {e_clean}")
    @property
    def images(self):
        """Returns a list of base64 encoded strings for all processed images.
        The output format for the base64 string respects item_data['output_format'] if set,
        otherwise defaults to self._config.DEFAULT_IMAGE_OUTPUT_FORMAT.
        """
        base64_images = []
        image_item_types = ['jpeg', 'png', 'gif', 'bmp', 'webp', 'tiff', 'heic', 'heif']
        for item_data in self.attachments_data:
            if item_data.get('type') in image_item_types and 'image_object' in item_data:
                try:
                    # Determine output format: use item's specified output_format or config default
                    output_format = item_data.get('output_format', self._config.DEFAULT_IMAGE_OUTPUT_FORMAT).lower()
                    if output_format == 'jpg': # common alias
                        output_format = 'jpeg'
                    
                    # Determine quality: use item's specified output_quality or config default
                    quality = item_data.get('output_quality', self._config.DEFAULT_IMAGE_QUALITY)
                    
                    buffered = io.BytesIO()
                    save_params = {}
                    if output_format in ['jpeg', 'webp']:
                        save_params['quality'] = quality
                    
                    # Ensure image is in a mode that can be saved to the target format
                    img_to_save = item_data['image_object']
                    if output_format == 'jpeg' and img_to_save.mode == 'RGBA':
                        img_to_save = img_to_save.convert('RGB')
                    elif output_format == 'png' and img_to_save.mode not in ['RGB', 'RGBA', 'L', 'P']:
                         # PNG supports various modes, but convert to RGB/RGBA for broader compatibility if complex
                         if img_to_save.mode not in ('1', 'L', 'P', 'RGB', 'RGBA', 'CMYK', 'YCbCr', 'LAB', 'HSV'):
                            img_to_save = img_to_save.convert('RGBA') # Safe bet for PNG

                    img_to_save.save(buffered, format=output_format.upper(), **save_params)
                    base64_str = base64.b64encode(buffered.getvalue()).decode('utf-8')
                    mime_type = f"image/{output_format}"
                    base64_images.append(f"data:{mime_type};base64,{base64_str}")
                except Exception as e:
                    if self.verbose:
                        print(f"Error converting image {item_data.get('id', '')} to base64 for .images property: {e}")
                    base64_images.append(f"Error: Could not generate base64 for image {item_data.get('id', '')}")
        return base64_images

    @property
    def audios(self):
        """Returns a list of dictionaries, each representing an audio file prepared for API submission.
        Each dictionary contains: {
            'filename': str,      # Filename with processed extension (e.g., 'speech.wav')
            'file_object': BytesIO, # In-memory bytes of the processed audio, with .name set to filename
            'content_type': str   # MIME type for the processed format (e.g., 'audio/wav')
        }
        """
        prepared_audios = []
        known_audio_types = ['flac', 'm4a', 'mp3', 'mp4_audio', 'mpeg_audio', 'oga', 'ogg_audio', 'wav', 'webm_audio']

        for item_data in self.attachments_data:
            if item_data.get('type') in known_audio_types and 'audio_segment' in item_data:
                audio_segment = item_data['audio_segment']
                # Use processed_filename_for_api from AudioParser (e.g., "input.wav")
                output_filename = item_data.get('processed_filename_for_api', 'processed_audio.dat')
                # Use output_format from AudioParser (e.g., "wav")
                output_format = item_data.get('output_format', 'wav').lower()
                # Bitrate for export, if specified (e.g., "128k")
                output_bitrate = item_data.get('output_bitrate') # This is a string like "128k" or None

                # Determine MIME type for the *output* format
                output_mime_map = {
                    'wav': 'audio/wav',
                    'mp3': 'audio/mpeg',
                    'flac': 'audio/flac',
                    'ogg': 'audio/ogg', # Covers oga, ogg_audio
                    'opus': 'audio/opus', # pydub uses 'opus' for export with libopus
                    'm4a': 'audio/m4a', # Or 'audio/mp4'
                    'aac': 'audio/aac',  # pydub can export aac (often in m4a container)
                    'webm': 'audio/webm', # Added for webm
                    'mp4': 'audio/mp4'   # Added for mp4 (audio in mp4 container)
                }
                # Use a more specific MIME type based on the output_format if possible
                content_type = output_mime_map.get(output_format, item_data.get('mime_type', 'application/octet-stream'))
                
                # If output_format is 'opus', pydub might use 'opus' codec if available and settings imply.
                # pydub's export(format="ogg") can produce ogg vorbis or ogg opus.
                # If the user explicitly asked for 'opus' format, content_type should be 'audio/opus'.
                if output_format == 'opus':
                    content_type = 'audio/opus'
                elif output_format == 'm4a' and item_data.get('applied_operations', {}).get('format') == 'aac':
                     content_type = 'audio/aac' # if user asked for aac and container is m4a

                try:
                    buffered = io.BytesIO()
                    export_params = {}
                    if output_bitrate:
                        # Only apply bitrate for formats where it makes sense (e.g., mp3)
                        # OGG (Vorbis/Opus) typically uses quality settings, not fixed bitrate.
                        # FLAC is lossless, bitrate is not applicable in the same way.
                        if output_format not in ['ogg', 'opus', 'flac', 'wav']:
                           export_params['bitrate'] = output_bitrate
                    
                    # pydub export parameters can also include 'parameters' for ffmpeg options
                    # e.g. parameters=["-ar", "16000"] for sample rate, but we did this with set_frame_rate
                    # For channels, we used set_channels.
                    # Default codec for "ogg" is vorbis. To get opus, use format="opus".
                    
                    audio_segment.export(buffered, format=output_format, **export_params)
                    
                    buffered.seek(0) # Reset stream position to the beginning
                    file_object = buffered
                    file_object.name = output_filename # Set the name attribute on BytesIO

                    prepared_audios.append({
                        'filename': output_filename,
                        'file_object': file_object,
                        'content_type': content_type
                    })
                except Exception as e:
                    if self.verbose:
                        # fn = output_filename # fn might not be defined if export_params failed early
                        # It's safer to use item_data or a known value if output_filename might not exist yet.
                        # For simplicity, let's assume output_filename is usually available if we reach here.
                        # However, to be robust: use item_data.get('processed_filename_for_api', 'unknown_audio')
                        filename_for_error = item_data.get('processed_filename_for_api', item_data.get('original_basename', 'unknown_audio'))
                        print(f"Warning: Could not process/export audio segment for {filename_for_error} (format: {output_format}): {e}")
        return prepared_audios

    def render(self, renderer_name=None):
        """Renders the processed attachments using a specified or default renderer."""
        renderer = self.renderer_registry.get_renderer(renderer_name)
        return renderer.render(self.attachments_data)

    def __str__(self):
        """String representation uses the default renderer (now DefaultXMLRenderer)."""
        return self.render()

    def __repr__(self):
        """Return an unambiguous string representation of the Attachments object."""
        if not self.original_paths_with_indices: # Ensure this uses the correct attribute name
            return "Attachments()"
        path_reprs = [repr(p) for p in self.original_paths_with_indices]
        if self.verbose:
            return f"Attachments({', '.join(path_reprs)}, verbose=True)"
        else:
            return f"Attachments({', '.join(path_reprs)})"

    def __getitem__(self, index):
        """Allows indexing into the Attachments object to get a new Attachments object
        with a subset of the original paths."""
        if isinstance(index, int):
            selected_path = self.original_paths_with_indices[index] # Ensure this uses the correct attribute name
            # When creating a new Attachments object, pass the config and verbose status
            return Attachments(selected_path, config=self._config, verbose=self.verbose)
        elif isinstance(index, slice):
            selected_paths_list = self.original_paths_with_indices[index] # Ensure this uses the correct attribute name
            # When creating a new Attachments object, pass the config and verbose status
            return Attachments(*selected_paths_list, config=self._config, verbose=self.verbose) 
        else:
            raise TypeError(f"Attachments indices must be integers or slices, not {type(index).__name__}")

    def _repr_markdown_(self) -> str:
        """Return a Markdown representation for IPython/Jupyter.
        Displays images and provides summaries for other file types.
        """
        self._original_verbose_for_debug = self.verbose # Store original verbose state

        md_parts = ["### Attachments Summary"]

        if not self.attachments_data and not self._unprocessed_inputs:
            md_parts.append("\n_No attachments processed and no processing errors._")
            return "\n".join(md_parts)
        
        num_processed = len(self.attachments_data)
        num_inputs = len(self.original_paths_with_indices) # Ensure this uses the correct attribute name
        
        md_parts.append(f"Successfully processed {num_processed} item(s) from {num_inputs} initial input(s).")
        if num_inputs == num_processed and num_inputs > 0:
            md_parts.append("\nSuccessfully processed all initial inputs.")
        elif num_inputs > num_processed and num_processed > 0:
            md_parts.append(f"\n{num_inputs - num_processed} input(s) could not be processed. See warnings/errors.")
        elif num_processed == 0 and num_inputs > 0:
            md_parts.append("\nNo inputs could be processed. See warnings/errors.")

        item_summaries = []
        image_gallery_items = []
        audio_gallery_items = []

        # Define type lists here for clarity in conditions below
        image_item_types = ['jpeg', 'png', 'gif', 'bmp', 'webp', 'tiff', 'heic', 'heif']
        audio_item_types = ['flac', 'm4a', 'mp3', 'wav', 'ogg', 'opus', 'aac']

        for item_index, item in enumerate(self.attachments_data):
            item_type = item.get('type', 'unknown').lower()
            item_id = item.get('id', f'item{item_index + 1}')
            input_str_display = item.get('original_path_str', item.get('file_path', 'N/A'))
            
            summary = []
            summary.append(f"**ID:** `{item_id}` (`{item_type}` from `{input_str_display}`)")

            if 'original_format' in item and item['original_format']:
                summary.append(f"  - **Original Format:** `{item['original_format'].upper()}`")
            if 'original_mode' in item and item['original_mode']:
                summary.append(f"  - **Original Mode:** `{item['original_mode']}`")
            if item.get('dimensions_after_ops'):
                dims = item['dimensions_after_ops']
                summary.append(f"  - **Dimensions (after ops):** `{dims[0]}x{dims[1]}`")
            if item.get('page_count') is not None:
                 summary.append(f"  - **Pages:** `{item['page_count']}`")
            if item.get('operations_applied') and isinstance(item['operations_applied'], dict) and item['operations_applied']:
                ops_summary = self._format_operations_for_markdown(item['operations_applied'])
                if ops_summary:
                    summary.append(f"  - **Operations:** `{ops_summary}`")
            if item.get('output_format'):
                summary.append(f"  - **Output as:** `{item['output_format']}`")
            
            text_snippet = item.get('text', '')
            if item_type not in image_item_types + audio_item_types: # Don't show full text for images/audio in main summary
                if text_snippet:
                    text_snippet = text_snippet.replace('\n', ' ').strip()
                    text_snippet = (text_snippet[:150] + '...') if len(text_snippet) > 150 else text_snippet
                    summary.append(f"  - **Content:** `{text_snippet}`")
            elif item_type in audio_item_types and text_snippet: # For audio, text_snippet is the descriptive summary
                summary.append(f"  - **Content:** `{text_snippet}`")

            item_summaries.append("\n".join(summary))
            
            # Prepare for image gallery (original logic)
            if item_type in image_item_types and self.verbose:
                try:
                    base64_img = self._render_image_to_base64(item)
                    img_alt = item.get('original_basename', item_id)
                    img_title = f"{item_id}: {item.get('original_basename', '')} (Type: {item_type})"
                    output_fmt_for_data_uri = item.get('output_format_for_base64', 
                                          item.get('output_format', self._config.DEFAULT_IMAGE_OUTPUT_FORMAT)).lower()
                    image_gallery_items.append(f'<img src="data:image/{output_fmt_for_data_uri};base64,{base64_img}" alt="{img_alt}" title="{img_title}" style="max-width:{self._config.MARKDOWN_IMAGE_MAX_WIDTH_PX}px; height:auto; margin:5px;"/>')
                except Exception as e:
                    image_gallery_items.append(f"_Could not render preview for {item_id} ({item.get('original_basename', '')}) due to: {e}_<br/>")
            
            # Prepare for audio gallery (original logic)
            eligible_audio_preview_format = item.get('output_format', '').lower() in ['mp3', 'ogg', 'opus', 'aac', 'm4a']
            if item_type in audio_item_types and self.verbose and eligible_audio_preview_format:
                try:
                    base64_audio, audio_mime_type = self._render_audio_to_base64(item)
                    audio_title = f"{item_id}: {item.get('original_basename', '')} (Type: {item_type}, Output: {item.get('output_format')})"
                    audio_gallery_items.append(f'<audio controls title="{audio_title}" style="margin:5px;">\n  <source src="data:{audio_mime_type};base64,{base64_audio}" type="{audio_mime_type}">\n  Your browser does not support the audio element.\n</audio>')
                except Exception as e:
                    audio_gallery_items.append(f"_Could not render audio preview for {item_id} ({item.get('original_basename', '')}) due to: {e}_<br/>")

        if item_summaries:
            md_parts.append("\n" + "\n---\n".join(item_summaries))
        
        if image_gallery_items and self.verbose:
            md_parts.append("\n\n### Image Previews")
            if self._config.MARKDOWN_IMAGE_GALLERY_STYLE == 'html':
                md_parts.append("\n" + "\n".join(image_gallery_items)) # Simple join for HTML items
            # Add other styles like 'grid' if needed
        
        if audio_gallery_items and self.verbose:
            md_parts.append("\n\n### Audio Previews")
            if self._config.MARKDOWN_AUDIO_PREVIEW_STYLE == 'html': # Assuming a similar config for audio
                md_parts.append("\n" + "\n".join(audio_gallery_items))

        # Restore original verbose state if it was changed for debug (it wasn't here, but good practice if it were)
        # self.verbose = getattr(self, '_original_verbose_for_debug', self.verbose)
        # delattr(self, '_original_verbose_for_debug') # Clean up temp attribute

        return "\n".join(md_parts)
    
    def set_renderer(self, renderer_instance_or_name):
        """Sets the default renderer for this Attachments instance."""
        if isinstance(renderer_instance_or_name, str):
            self.renderer_registry.set_default_renderer(renderer_instance_or_name)
        # Check if it's an instance of a class that inherits from BaseRenderer
        # This is a more robust check than checking __bases__[0]
        elif any(isinstance(renderer_instance_or_name, base_cls) for base_cls in self.renderer_registry.renderers[next(iter(self.renderer_registry.renderers))].__class__.__mro__ if base_cls is not object and hasattr(base_cls, 'render')) :
            # A bit complex: find a registered renderer instance, get its class, get its MRO, check if our instance is one of those (excluding object)
            # and if it has a render method. This is to check against BaseRenderer indirectly.
            # A simpler way, if BaseRenderer is imported: isinstance(renderer_instance_or_name, BaseRenderer)
            self.renderer_registry.default_renderer = renderer_instance_or_name 
        else:
            raise TypeError("Invalid type for renderer. Must be a registered renderer name or a BaseRenderer instance.")

    def pipe(self, custom_preprocess_func):
        print(f"Piping with {custom_preprocess_func}")
        return self

    def save_config(self, config_path):
        print(f"Saving config to {config_path}")

    def load_config(self, config_path):
        print(f"Loading config from {config_path}")

    def set_default_renderer(self, renderer_key: str, renderer_instance):
        """Sets the default renderer for this Attachments instance."""
        if not isinstance(renderer_key, str):
            raise TypeError("Renderer key must be a string.")
        # A more complete implementation would check if renderer_instance is valid
        # Assuming self._config.RENDERER_REGISTRY was meant if RENDERER_REGISTRY is on Config
        # If RENDERER_REGISTRY is directly on self, then self.RENDERER_REGISTRY
        # Based on common patterns, it might be self.renderer_registry if it's an attribute initialized in __init__
        # The previous successful diff showed self.renderer_registry.register(...)
        self.renderer_registry.register(renderer_key, renderer_instance, set_default=True)
        # print(f"Default renderer set to: {renderer_key}")
        return # Explicit return to ensure method block is clean

    # It's crucial that what follows is syntactically valid.
    # Adding a placeholder for the next potential method or end of class.
    def another_method_or_end_of_class_placeholder(self):
        pass

    # Potentially other methods follow, or end of class / file 

    def _format_operations_for_markdown(self, operations: Dict[str, Any]) -> str:
        """Helper to format the operations dictionary for Markdown output."""
        if not operations or not isinstance(operations, dict):
            return ""
        
        parts = []
        for key, value in operations.items():
            if isinstance(value, tuple) and len(value) == 2 and all(isinstance(v, (int, float)) for v in value):
                # Likely dimensions like resize: (100, 200)
                parts.append(f"{key}: {value[0]}x{value[1]}")
            elif isinstance(value, (str, int, float, bool)):
                parts.append(f"{key}: {value}")
            # Add more specific formatting if needed for other types
            else:
                parts.append(f"{key}: {str(value)}") # Fallback to string representation
        return ", ".join(parts)

    # Basic iteration and length

    # Potentially other methods follow, or end of class / file 

    def _render_image_to_base64(self, item_data: Dict[str, Any]) -> str:
        """Helper to render an image item to a base64 string for Markdown embedding.
        Returns only the base64 encoded string part.
        """
        if 'image_object' not in item_data:
            # This case should ideally not be reached if called from _repr_markdown_
            # which checks for image_object's presence implicitly via item_type in image_item_types
            # and relies on ImageParser to always provide image_object for image types.
            # However, as a safeguard:
            raise ValueError(f"Item data for ID '{item_data.get('id', 'unknown')}' does not contain an image_object.")

        img_to_save = item_data['image_object']
        
        # Determine output format for the base64 string in Markdown.
        # Uses 'output_format_for_base64' if specified in item_data (e.g. by a parser for specific preview needs),
        # otherwise falls back to the item's general 'output_format' (from operations),
        # finally defaults to config's DEFAULT_IMAGE_OUTPUT_FORMAT.
        output_format = item_data.get('output_format_for_base64',
                                      item_data.get('output_format', self._config.DEFAULT_IMAGE_OUTPUT_FORMAT)).lower()
        if output_format == 'jpg':  # common alias
            output_format = 'jpeg'

        quality = item_data.get('output_quality', self._config.DEFAULT_IMAGE_QUALITY)

        buffered = io.BytesIO()
        save_params = {}
        if output_format in ['jpeg', 'webp']:
            save_params['quality'] = quality

        # Ensure image is in a mode that can be saved to the target format
        # This conversion logic should ideally mirror what .images property does, or be centralized.
        if output_format == 'jpeg' and img_to_save.mode == 'RGBA':
            img_to_save = img_to_save.convert('RGB')
        elif output_format == 'png' and img_to_save.mode not in ['RGB', 'RGBA', 'L', 'P', '1']:
            # PNG supports various modes, but convert to RGB/RGBA for broader compatibility if complex
            # Pillow's list of modes: 1, L, P, RGB, RGBA, CMYK, YCbCr, LAB, HSV, I, F.
            # We'll convert if not one of the simpler/common ones directly savable to PNG without issues.
            if img_to_save.mode not in ('1', 'L', 'P', 'RGB', 'RGBA'): # Stricter set for direct save
                 img_to_save = img_to_save.convert('RGBA') # Safe bet for PNG

        img_to_save.save(buffered, format=output_format.upper(), **save_params)
        return base64.b64encode(buffered.getvalue()).decode('utf-8')

    def _render_audio_to_base64(self, item_data: Dict[str, Any]) -> Tuple[str, str]:
        """Helper to render an audio item to a base64 string and its MIME type for Markdown embedding.
        Returns: (base64_encoded_audio_string, mime_type_string)
        """
        if 'audio_segment' not in item_data:
            raise ValueError(f"Item data for ID '{item_data.get('id', 'unknown')}' does not contain an audio_segment.")

        audio_segment = item_data['audio_segment']
        
        # Determine output format. Prefers item's 'output_format' (from ops), else config default.
        output_format = item_data.get('output_format', self._config.DEFAULT_AUDIO_FORMAT).lower()
        # Determine bitrate. Prefers item's 'output_bitrate' (from ops), else config default.
        output_bitrate = item_data.get('output_bitrate', self._config.DEFAULT_AUDIO_BITRATE)

        # MIME type mapping (could be a class/static variable or a helper)
        output_mime_map = {
            'wav': 'audio/wav', 'mp3': 'audio/mpeg', 'flac': 'audio/flac',
            'ogg': 'audio/ogg', 'opus': 'audio/opus', 
            'm4a': 'audio/m4a', # pydub often uses 'mp4' container for m4a/aac
            'aac': 'audio/aac', 
            'webm': 'audio/webm',
            'mp4': 'audio/mp4' # For audio explicitly in mp4 container
        }
        # Start with a generic guess or the map value
        mime_type = output_mime_map.get(output_format, 'application/octet-stream')

        # Refine MIME type based on format nuances
        if output_format == 'opus': # Opus is distinct
            mime_type = 'audio/opus'
        elif output_format == 'm4a':
             # If format is m4a, pydub exports as 'mp4'. MIME can be audio/m4a or audio/mp4.
             # Let's prefer audio/m4a for clarity if the request was for m4a.
             # If an explicit 'aac' operation led to m4a, 'audio/aac' might also be considered.
            mime_type = 'audio/m4a' 
            if item_data.get('applied_operations', {}).get('format') == 'aac': # If format op was 'aac'
                 pass # Keep as audio/m4a, or consider audio/aac if more specific for the codec.
                      # For HTML5 <audio>, audio/m4a or audio/mp4 (with AAC codec) is common.
        elif output_format == 'mp3':
            mime_type = 'audio/mpeg'


        buffered = io.BytesIO()
        export_params = {}
        # Apply bitrate only for formats where pydub supports it directly via 'bitrate' param
        # and where it's meaningful (e.g., not for lossless like WAV, FLAC).
        # pydub uses 'None' to signify auto/default bitrate for many formats.
        if output_bitrate and output_format not in ['ogg', 'opus', 'flac', 'wav']:
            export_params['bitrate'] = output_bitrate

        try:
            audio_segment.export(buffered, format=output_format, **export_params)
        except Exception as e:
            # Provide more context in case of export failure
            err_msg = (f"Failed to export audio segment for ID '{item_data.get('id', 'unknown')}' "
                       f"to format '{output_format}' with params {export_params}: {e}")
            # Depending on how critical this is for _repr_markdown_, either re-raise or log and return error indicator
            raise ParsingError(err_msg) from e # Re-raise as ParsingError to be caught by _repr_markdown_


        buffered.seek(0) # Reset stream position for reading
        base64_audio_str = base64.b64encode(buffered.getvalue()).decode('utf-8')
        return base64_audio_str, mime_type

    # Potentially other methods follow, or end of class / file 