import os
import re
from urllib.parse import urlparse # Added for URL parsing
import requests                   # Added for downloading URLs
import tempfile                   # Added for temporary file handling
import io                         # For in-memory byte streams (image base64 encoding)
import base64                     # For base64 encoding
from PIL import Image
import mimetypes # For guessing MIME types

from .detectors import Detector
from .parsers import ParserRegistry, PDFParser, PPTXParser, HTMLParser, ImageParser, AudioParser
from .renderers import RendererRegistry, DefaultXMLRenderer, PlainTextRenderer
from .exceptions import DetectionError, ParsingError

class Attachments:
    """Core class for handling attachments."""
    def __init__(self, *paths, verbose=False):
        self.detector = Detector()
        self.parser_registry = ParserRegistry()
        self.renderer_registry = RendererRegistry()
        self._register_default_components()
        self.verbose = verbose

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
                
                except requests.exceptions.RequestException as e_req:
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
        """Returns a list of base64 encoded image strings suitable for LLM APIs.
        Each string is in the format: data:image/<format>;base64,<encoded_data>
        """
        base64_images = []
        image_item_types = ['jpeg', 'png', 'gif', 'bmp', 'webp', 'tiff', 'heic', 'heif']

        for item_data in self.attachments_data:
            if item_data.get('type') in image_item_types and 'image_object' in item_data:
                img_obj = item_data['image_object']
                output_format = item_data.get('output_format', 'jpeg').lower()
                if output_format == 'jpg': 
                    output_format = 'jpeg' 
                
                quality = item_data.get('output_quality', 90)
                
                pillow_save_format = output_format.upper()
                if pillow_save_format == "JPG": pillow_save_format = "JPEG"

                save_img = img_obj
                if pillow_save_format == 'JPEG':
                    if save_img.mode == 'RGBA' or save_img.mode == 'LA': 
                        save_img = save_img.convert('RGB')
                    elif save_img.mode == 'P': 
                         save_img = save_img.convert('RGB') 
                elif pillow_save_format == 'PNG':
                    if save_img.mode not in ['RGB', 'RGBA', 'L', 'P']: 
                         save_img = save_img.convert('RGBA') 
                
                try:
                    buffered = io.BytesIO()
                    save_params = {}
                    if pillow_save_format == 'JPEG':
                        save_params['quality'] = quality
                        save_params['optimize'] = True 
                    elif pillow_save_format == 'PNG':
                        save_params['optimize'] = True
                    elif pillow_save_format == 'WEBP':
                        save_params['quality'] = quality

                    save_img.save(buffered, format=pillow_save_format, **save_params)
                    img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
                    
                    mime_type = f"image/{output_format}"
                    
                    base64_images.append(f"data:{mime_type};base64,{img_base64}")
                except Exception as e_save_b64:
                    print(f"Warning: Could not convert image {item_data.get('file_path', 'unknown')} to base64 (format: {output_format}): {e_save_b64}")
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
        if not self.original_paths_with_indices:
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
            selected_path = self.original_paths_with_indices[index]
            return Attachments(selected_path, verbose=self.verbose)
        elif isinstance(index, slice):
            selected_paths_list = self.original_paths_with_indices[index]
            return Attachments(selected_paths_list, verbose=self.verbose) 
        else:
            raise TypeError(f"Attachments indices must be integers or slices, not {type(index).__name__}")

    def _repr_markdown_(self):
        """Return a Markdown representation for IPython/Jupyter.
        Displays images and provides summaries for other file types.
        """
        if not self.attachments_data:
            return "_No attachments processed._"

        md_parts = ["### Attachments Summary"]
        image_item_types = ['jpeg', 'png', 'gif', 'bmp', 'webp', 'tiff', 'heic', 'heif']
        known_audio_types = ['flac', 'm4a', 'mp3', 'mp4_audio', 'mpeg_audio', 'oga', 'ogg_audio', 'wav', 'webm_audio']
        
        collected_image_previews = [] 
        collected_audio_previews = [] # New list for audio

        for i, item in enumerate(self.attachments_data):
            item_id = item.get('id', f'item{i+1}')
            item_type = item.get('type', 'N/A')
            original_path_str = item.get('original_path_str', 'N/A')
            # file_path is the original user-provided string, which might be a URL or local path.
            # original_filename_for_api is better for display if it's an audio/image file.
            display_name = item.get('original_filename_for_api', os.path.basename(item.get('file_path', 'N/A')))

            # For audio, prefer the processed filename for API if available and more descriptive
            if item_type in known_audio_types and 'processed_filename_for_api' in item:
                display_name = item.get('processed_filename_for_api')

            md_parts.append(f"**ID:** `{item_id}` (`{item_type}` from `{original_path_str}`)")

            if item_type in image_item_types and 'image_object' in item:
                md_parts.append(f"  - **Dimensions (after ops):** `{item.get('width', 'N/A')}x{item.get('height', 'N/A')}`")
                md_parts.append(f"  - **Original Format:** `{item.get('original_format', 'N/A')}`")
                md_parts.append(f"  - **Original Mode:** `{item.get('original_mode', 'N/A')}`")
                if item.get('applied_operations'):
                    ops_str = str(item.get('applied_operations')) 
                    md_parts.append(f"  - **Operations:** `{ops_str}`")
                md_parts.append(f"  - **Output as:** `{item.get('output_format', 'N/A')}`")
                
                try:
                    img_obj = item['image_object'] 
                    temp_img_for_display = img_obj.copy() 
                    max_thumb_width = 100 
                    max_thumb_height = 100 
                    temp_img_for_display.thumbnail((max_thumb_width, max_thumb_height), Image.Resampling.LANCZOS)
                    thumb_output_format = 'png' if temp_img_for_display.mode == 'RGBA' else 'jpeg'
                    pillow_save_format = thumb_output_format.upper()
                    save_img_for_display = temp_img_for_display
                    if pillow_save_format == 'JPEG' and save_img_for_display.mode == 'RGBA':
                        save_img_for_display = save_img_for_display.convert('RGB')
                    elif pillow_save_format == 'PNG' and save_img_for_display.mode not in ['RGB', 'RGBA', 'L', 'P']:
                        save_img_for_display = save_img_for_display.convert('RGBA')
                    buffered = io.BytesIO()
                    save_params_thumb = {'optimize': True}
                    if pillow_save_format == 'JPEG': save_params_thumb['quality'] = 75
                    save_img_for_display.save(buffered, format=pillow_save_format, **save_params_thumb)
                    img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
                    mime_type = f"image/{thumb_output_format}"
                    alt_text = display_name
                    collected_image_previews.append((item_id, alt_text, f"data:{mime_type};base64,{img_base64}"))
                except Exception as e_thumb_gen:
                    collected_image_previews.append((item_id, display_name, None, f"Error generating preview: {e_thumb_gen}"))
            
            elif item_type in known_audio_types:
                md_parts.append(f"  - **File Name (processed):** `{display_name}`")
                md_parts.append(f"  - **Original File Name:** `{item.get('original_basename', 'N/A')}`")
                md_parts.append(f"  - **Detected Input Type:** `{item.get('type', 'N/A')}`")
                md_parts.append(f"  - **Processed Output Format:** `{item.get('output_format', 'N/A')}`")
                md_parts.append(f"  - **Processed Sample Rate:** `{item.get('output_samplerate', 'N/A')}`")
                md_parts.append(f"  - **Processed Channels:** `{item.get('output_channels', 'N/A')}`")
                if item.get('output_bitrate'):
                    md_parts.append(f"  - **Requested Bitrate:** `{item.get('output_bitrate')}`")
                
                mime_type_for_display = item.get('mime_type', 'N/A') # This is the original MIME
                # For the .audios property, we derive a content_type for the *output* format.
                # For display here, showing original and output details separately is clearer.
                md_parts.append(f"  - **Original MIME Type:** `{mime_type_for_display}`")

                text_snippet = item.get('text', '') # This is the rich text from AudioParser
                md_parts.append(f"  - **Details:** `{text_snippet}`")

                # Attempt to generate audio preview for markdown
                # We need to find the corresponding processed audio from self.audios
                # This relies on self.audios being called or its logic being accessible
                # Matching by original_path_str and ops could be one way if IDs are not stable enough.
                # For simplicity, we'll iterate through self.audios and match based on original_path_str
                # or a more robust identifier if available.
                # Let's assume item_data's 'processed_filename_for_api' is unique enough for this context.
                
                # Find the corresponding audio data from the self.audios property
                # This is a bit inefficient as self.audios re-processes.
                # A better way would be to cache the results of self.audios or make its components available.
                # For now, let's make a targeted call to get the specific audio BytesIO
                
                target_filename_for_preview = item.get('processed_filename_for_api')
                audio_preview_data = None
                # Iterate through the results of the audios property to find the matching file
                for audio_api_item in self.audios: # This will re-process all audios, can be slow
                    if audio_api_item['filename'] == target_filename_for_preview:
                        audio_preview_data = audio_api_item
                        break
                
                if audio_preview_data:
                    try:
                        audio_bytes = audio_preview_data['file_object'].getvalue()
                        audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
                        audio_mime_type = audio_preview_data['content_type']
                        audio_player_html = f'<audio controls src="data:{audio_mime_type};base64,{audio_base64}"></audio>'
                        collected_audio_previews.append((item_id, display_name, audio_player_html))
                    except Exception as e_audio_preview:
                        collected_audio_previews.append((item_id, display_name, None, f"Error generating audio preview: {e_audio_preview}"))
                else:
                    # This case might happen if self.audios logic filters out some items or filenames don't match.
                    if self.verbose: print(f"Markdown preview: Could not find matching audio data for {target_filename_for_preview} in self.audios results.")
                    collected_audio_previews.append((item_id, display_name, None, "Audio data not readily available for preview."))

            else: # For other types like PDF, PPTX, HTML
                # Use processed_file_path for these as they don't have 'original_filename_for_api' usually
                processed_file_path_display = item.get('file_path', 'N/A') # This is original_file_path_or_url
                md_parts.append(f"  - **Source:** `{processed_file_path_display}`")
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
            md_parts.append("---") 

        if collected_image_previews:
            md_parts.append("\n### Image Previews")
            num_columns = 3
            header_cells = ["&nbsp;"] * num_columns 
            md_parts.append(f"| {' | '.join(header_cells)} |")
            md_parts.append(f"|{'---:|' * num_columns}") # Align content to right for typical image cells

            row_images = []
            for i, preview_data in enumerate(collected_image_previews):
                _item_id, alt_text, data_uri, error_msg = (*preview_data, None) if len(preview_data) == 3 else preview_data
                
                if data_uri:
                    cell_content = f"![{alt_text}]({data_uri})<br/><sup>{_item_id}: {alt_text}</sup>" # Add ID & alt text below image
                else:
                    cell_content = f"*{alt_text} - Error generating preview: {error_msg}*"
                row_images.append(cell_content)
                
                if len(row_images) == num_columns or (i == len(collected_image_previews) - 1):
                    while len(row_images) < num_columns:
                        row_images.append("&nbsp;") 
                    md_parts.append(f"| {' | '.join(row_images)} |")
                    row_images = []

        # Add Audio Previews section
        if collected_audio_previews:
            md_parts.append("\n### Audio Previews")
            # For audio, a simple list format might be better than a table due to player height
            for audio_id, audio_name, player_html, error_msg in [(ca[0], ca[1], ca[2] if len(ca) > 2 and ca[2] else None, ca[3] if len(ca) > 3 else (ca[2] if len(ca) == 3 and ca[2] is None else None) ) for ca in collected_audio_previews]: # Ensure correct unpacking
                if player_html:
                    md_parts.append(f"- **{audio_id}:** {audio_name}<br/>{player_html}")
                else:
                    error_detail = error_msg or "Could not generate player."
                    md_parts.append(f"- **{audio_id}:** {audio_name} - *{error_detail}*")
                md_parts.append("---")

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