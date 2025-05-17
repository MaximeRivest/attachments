# src/attachments/config.py

class Config:
    def __init__(self):
        # Markdown rendering options
        self.MARKDOWN_IMAGE_GALLERY_STYLE: str = 'html' # Can be 'html' or potentially other formats
        self.MARKDOWN_IMAGE_MAX_WIDTH_PX: int = 600
        self.MARKDOWN_IMAGE_MAX_HEIGHT_PX: int = 600 # Maintained for potential future use
        self.MARKDOWN_AUDIO_PREVIEW_STYLE: str = 'html' # For audio previews

        # Default audio processing parameters
        self.DEFAULT_AUDIO_FORMAT: str = 'wav'
        self.DEFAULT_AUDIO_SAMPLERATE: int = 16000  # Hz
        self.DEFAULT_AUDIO_CHANNELS: int = 1       # 1 for mono, 2 for stereo
        self.DEFAULT_AUDIO_BITRATE: str = '64k'   # Default bitrate for processed audio like mp3, ogg

        # Default image processing parameters
        self.DEFAULT_IMAGE_OUTPUT_FORMAT: str = 'jpeg' # Default format for image operations if not specified
        self.DEFAULT_IMAGE_QUALITY: int = 85          # For lossy formats like JPEG/WEBP (1-100)
        
        # Verbosity and Error Handling
        self.RAISE_EXCEPTIONS_ON_PARSE_FAILURE: bool = False # If True, parsing errors will raise exceptions instead of being collected.
                                                              # This is more for direct use of parsers than the Attachments class.
        # Add other configuration options as needed 