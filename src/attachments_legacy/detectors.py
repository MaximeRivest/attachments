"""Attachment detection logic."""

class Detector:
    """Manages file type detection."""
    def __init__(self):
        self.detection_methods = {}
        # Register default types
        self._register_defaults()

    def _register_defaults(self):
        """Registers default common file types."""
        self.register('pdf', extensions=['.pdf'])
        self.register('pptx', extensions=['.pptx'])
        self.register('html', extensions=['.html', '.htm'])
        # Image types
        self.register('jpeg', extensions=['.jpg', '.jpeg'])
        self.register('png', extensions=['.png'])
        self.register('gif', extensions=['.gif'])
        self.register('bmp', extensions=['.bmp'])
        self.register('webp', extensions=['.webp'])
        self.register('tiff', extensions=['.tif', '.tiff'])
        self.register('heic', extensions=['.heic'])
        self.register('heif', extensions=['.heif'])

        # Audio types - based on OpenAI Whisper and ElevenLabs Scribe lists
        self.register('flac', extensions=['.flac'])
        self.register('m4a', extensions=['.m4a'])
        self.register('mp3', extensions=['.mp3'])
        self.register('mp4_audio', extensions=['.mp4']) # Distinguish from video mp4 if necessary later
        self.register('mpeg_audio', extensions=['.mpeg', '.mpg', '.mpga']) # .mpeg/.mpg can be video too
        self.register('oga', extensions=['.oga']) # Ogg Audio
        self.register('ogg_audio', extensions=['.ogg']) # .ogg can be video (Theora) or audio (Vorbis)
        self.register('wav', extensions=['.wav', '.wave'])
        self.register('webm_audio', extensions=['.webm']) # .webm can be video (VP8/VP9) or audio (Opus/Vorbis)

        # Word processing documents
        self.register('docx', extensions=['.docx'])
        self.register('odt', extensions=['.odt'])

    def register(self, name, extensions=None, regex=None, custom_method=None):
        """Registers a detection method."""
        # Placeholder for registration logic
        if extensions:
            self.detection_methods[name] = {'type': 'extension', 'value': extensions}
        elif regex:
            self.detection_methods[name] = {'type': 'regex', 'value': regex}
        elif custom_method:
            self.detection_methods[name] = {'type': 'custom', 'value': custom_method}
        else:
            raise ValueError("Either extensions, regex, or custom_method must be provided.")

    def detect(self, file_path, content_type=None):
        """Detects the type of a file based on registered methods and content_type."""
        # Priority 1: Content-Type header (if provided)
        if content_type:
            # Simple mapping for common types. This can be expanded.
            # Content-Type can also have parameters like charset, e.g., "text/html; charset=UTF-8"
            main_type = content_type.split(';')[0].strip().lower()
            if main_type == 'text/html':
                return 'html'
            elif main_type == 'application/pdf':
                return 'pdf'
            elif main_type == 'application/vnd.openxmlformats-officedocument.presentationml.presentation':
                return 'pptx'
            # Word processing MIME types
            elif main_type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
                return 'docx'
            elif main_type == 'application/vnd.oasis.opendocument.text':
                return 'odt'
            # Image MIME types
            elif main_type == 'image/jpeg':
                return 'jpeg'
            elif main_type == 'image/png':
                return 'png'
            elif main_type == 'image/gif':
                return 'gif'
            elif main_type == 'image/bmp':
                return 'bmp'
            elif main_type == 'image/webp':
                return 'webp'
            elif main_type == 'image/tiff':
                return 'tiff'
            elif main_type == 'image/heic':
                return 'heic'
            elif main_type == 'image/heif':
                return 'heif'
            # Audio MIME types
            elif main_type == 'audio/flac' or main_type == 'audio/x-flac':
                return 'flac'
            elif main_type == 'audio/m4a' or main_type == 'audio/x-m4a' or (main_type == 'audio/mp4' and file_path.lower().endswith('.m4a')): # audio/mp4 can be m4a
                return 'm4a'
            elif main_type == 'audio/mpeg': # Covers mp3, mpga
                # More specific check for mp3 extension if mime is generic audio/mpeg
                if file_path.lower().endswith('.mp3'):
                    return 'mp3'
                return 'mpeg_audio' # Default for audio/mpeg if not .mp3
            elif main_type == 'audio/mp3': # Explicit mp3
                 return 'mp3'
            elif main_type == 'audio/mp4': # If not m4a, could be mp4 audio
                 return 'mp4_audio'
            elif main_type == 'audio/ogg': # Covers oga (Vorbis, Opus, FLAC in Ogg)
                 # Prefer oga if extension matches, else generic ogg_audio
                if file_path.lower().endswith('.oga'):
                    return 'oga'
                return 'ogg_audio'
            elif main_type == 'audio/opus': # Often in .ogg or .opus containers
                 return 'ogg_audio' # Or define 'opus' type if distinct handling needed
            elif main_type == 'audio/wav' or main_type == 'audio/x-wav' or main_type == 'audio/wave':
                return 'wav'
            elif main_type == 'audio/webm':
                return 'webm_audio'
            # Add more MIME type mappings here as needed
            # Fallback for other audio/* types
            elif main_type.startswith('audio/'):
                # Generic audio type if no specific match, rely on extension then
                # This part helps if a new audio MIME type appears but has a known extension
                # Let extension check handle it below.
                pass
            # Add more MIME type mappings here as needed
            # Fallback for other image/* types if not specifically handled above,
            # could attempt to map to a generic image type or rely on extension.
            # For now, explicit mapping is safer.

        # Priority 2: Extension-based detection (existing logic)
        import os
        _, ext = os.path.splitext(file_path)
        ext = ext.lower()

        for name, method_info in self.detection_methods.items():
            if method_info['type'] == 'extension':
                if ext in method_info['value']:
                    return name
            elif method_info['type'] == 'regex':
                # Placeholder for regex matching
                # import re
                # if re.match(method_info['value'], file_path):
                #     return name
                pass # Implement regex logic
            elif method_info['type'] == 'custom':
                # Placeholder for custom method execution
                # if method_info['value'](file_path):
                #     return name
                pass # Implement custom method logic
        return None # Default to None if no type detected 