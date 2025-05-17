"""File parsing logic."""

from abc import ABC, abstractmethod
import os
from typing import Dict, Any, Optional, Tuple, List

from PIL import Image, UnidentifiedImageError, ExifTags, ImageOps
from pillow_heif import register_heif_opener

try:
    register_heif_opener()
    HAS_PILLOW_HEIF = True
except ImportError:
    HAS_PILLOW_HEIF = False
    # PillowHeifUnidentifiedImageError will not be defined here, 
    # but HAS_PILLOW_HEIF check in ImageParser.parse() should prevent issues.
except RuntimeError: 
    HAS_PILLOW_HEIF = False
    # Similarly, PillowHeifUnidentifiedImageError won't be defined.

from pydub import AudioSegment 
from pydub.exceptions import CouldntDecodeError

# Local project imports - Correcting formatting and ensuring they are exactly as needed
from attachments.exceptions import ParsingError
from .image_processing import (
    process_image_operations, get_image_metadata, 
    DEFAULT_IMAGE_OUTPUT_FORMAT, DEFAULT_IMAGE_QUALITY
)
from .audio_processing import (
    process_audio_operations, get_audio_metadata,
    DEFAULT_AUDIO_FORMAT, DEFAULT_AUDIO_SAMPLERATE,
    DEFAULT_AUDIO_CHANNELS, DEFAULT_AUDIO_BITRATE
)
from .config import Config as ActualConfig 

# Integration for markitdown
from markitdown import MarkItDown
from markitdown import MarkItDownException, UnsupportedFormatException, FileConversionException, MissingDependencyException

class BaseParser(ABC):
    """Abstract base class for file parsers."""
    def __init__(self, config: Optional[ActualConfig] = None):
        self._config = config if config else ActualConfig()
        if hasattr(self._config, 'MARKITDOWN_INSTANCE') and self._config.MARKITDOWN_INSTANCE:
            self.md_converter = self._config.MARKITDOWN_INSTANCE
        else:
            self.md_converter = MarkItDown()

    @abstractmethod
    def parse(self, file_path: str, indices: Optional[str] = None) -> Dict[str, Any]:
        pass # Will be implemented by subclasses

# Placeholder classes to be replaced next - these are just to allow a staged edit.
class PDFParser(BaseParser):
    """Parses PDF files using the configured markitdown instance."""
    def parse(self, file_path: str, indices: Optional[str] = None) -> Dict[str, Any]:
        try:
            # Note: `indices` (for page selection) is not directly passed to 
            # markitdown's generic .convert() here. If markitdown's PDF handler 
            # (e.g., via pdfminer.six) uses a specific config or environment for page ranges,
            # that would need to be set up on the MarkItDown instance itself or via conversion_options.
            # For this generic parser, we assume it converts all pages or respects its own defaults.
            markdown_text = self.md_converter.convert(file_path).markdown
            return {
                "text": markdown_text,
                "original_basename": os.path.basename(file_path),
                "file_path": file_path,
            }
        except (MarkItDownException, FileConversionException, MissingDependencyException) as e:
            raise ParsingError(message=f"Error processing PDF '{file_path}' with markitdown: {e}", file_path=file_path, parser_name=self.__class__.__name__) from e
        except Exception as e: 
            raise ParsingError(message=f"Failed to parse PDF '{file_path}': {e}", file_path=file_path, parser_name=self.__class__.__name__) from e

class HTMLParser(BaseParser):
    """Parses HTML files or URLs using the configured markitdown instance."""
    def parse(self, file_path_or_url: str, indices: Optional[str] = None) -> Dict[str, Any]:
        # `indices` is typically not used for HTML to Markdown conversion.
        try:
            markdown_text = self.md_converter.convert(file_path_or_url).markdown
            return {
                "text": markdown_text,
                "original_basename": os.path.basename(file_path_or_url),
                "file_path": file_path_or_url, # Could be URL
            }
        except (MarkItDownException, FileConversionException, MissingDependencyException) as e:
            raise ParsingError(message=f"Error processing HTML '{file_path_or_url}' with markitdown: {e}", file_path=file_path_or_url, parser_name=self.__class__.__name__) from e
        except Exception as e:
            raise ParsingError(message=f"Failed to parse HTML '{file_path_or_url}': {e}", file_path=file_path_or_url, parser_name=self.__class__.__name__) from e

class DOCXParser(BaseParser):
    """Parses DOCX files using the configured markitdown instance."""
    def parse(self, file_path: str, indices: Optional[str] = None) -> Dict[str, Any]:
        # `indices` is typically not used for DOCX to Markdown.
        try:
            markdown_text = self.md_converter.convert(file_path).markdown
            return {
                "text": markdown_text,
                "original_basename": os.path.basename(file_path),
                "file_path": file_path,
            }
        except (MarkItDownException, FileConversionException, MissingDependencyException) as e:
            raise ParsingError(message=f"Error processing DOCX '{file_path}' with markitdown: {e}", file_path=file_path, parser_name=self.__class__.__name__) from e
        except Exception as e:
            raise ParsingError(message=f"Failed to parse DOCX '{file_path}': {e}", file_path=file_path, parser_name=self.__class__.__name__) from e

class ODTParser(BaseParser):
    """Parses ODT files using the configured markitdown instance."""
    def parse(self, file_path: str, indices: Optional[str] = None) -> Dict[str, Any]:
        # `indices` is typically not used for ODT to Markdown.
        try:
            markdown_text = self.md_converter.convert(file_path).markdown
            return {
                "text": markdown_text,
                "original_basename": os.path.basename(file_path),
                "file_path": file_path,
            }
        except FileNotFoundError:
            raise ParsingError(message="File not found", file_path=file_path, parser_name=self.__class__.__name__) from None
        except UnsupportedFormatException: # Specifically catch this from markitdown
            # If markitdown doesn't support ODT, return empty text and don't raise ParsingError
            # A warning could be logged here if logging was set up
            # print(f"Warning: Markitdown does not support ODT file: {file_path}. Returning empty text.")
            return {
                "text": "", # Empty text as ODT could not be converted
                "original_basename": os.path.basename(file_path),
                "file_path": file_path,
                "conversion_error": "ODT format not supported by the current Markitdown configuration."
            }
        except (MarkItDownException, FileConversionException, MissingDependencyException) as e: # Other markitdown errors
            raise ParsingError(message=f"Error processing ODT '{file_path}' with markitdown: {e}", file_path=file_path, parser_name=self.__class__.__name__) from e
        except Exception as e: # Other unexpected errors
            raise ParsingError(message=f"Failed to parse ODT '{file_path}': {e}", file_path=file_path, parser_name=self.__class__.__name__) from e

class PPTXParser(BaseParser):
    """Parses PPTX files using the configured markitdown instance."""
    def parse(self, file_path: str, indices: Optional[str] = None) -> Dict[str, Any]:
        try:
            # Note: `indices` (for slide selection) is not directly passed here.
            # Similar to PDFParser, this would depend on how markitdown's PPTX handler 
            # (e.g., via python-pptx) is configured or uses conversion_options.
            markdown_text = self.md_converter.convert(file_path).markdown 
            return {
                "text": markdown_text,
                "original_basename": os.path.basename(file_path),
                "file_path": file_path,
            }
        except (MarkItDownException, FileConversionException, MissingDependencyException) as e:
            raise ParsingError(message=f"Error processing PPTX '{file_path}' with markitdown: {e}", file_path=file_path, parser_name=self.__class__.__name__) from e
        except Exception as e:
            raise ParsingError(message=f"Failed to parse PPTX '{file_path}': {e}", file_path=file_path, parser_name=self.__class__.__name__) from e

# ImageParser and AudioParser __init__ are fine from previous step.
# Their full parse methods will be restored/verified after document parsers.
class ImageParser(BaseParser):
    def __init__(self, config: Optional[ActualConfig] = None):
        self._config = config if config else ActualConfig()
        self.default_output_format = getattr(self._config, 'DEFAULT_IMAGE_OUTPUT_FORMAT', DEFAULT_IMAGE_OUTPUT_FORMAT)
        self.default_quality = getattr(self._config, 'DEFAULT_IMAGE_QUALITY', DEFAULT_IMAGE_QUALITY)

    def parse(self, file_path: str, indices: Optional[str] = None) -> Dict[str, Any]:
        file_ext_lower = os.path.splitext(file_path)[1].lower()
        if file_ext_lower in ['.heic', '.heif'] and not HAS_PILLOW_HEIF:
            raise ParsingError(
                message=(
                    f"Processing {file_ext_lower.upper()} file '{file_path}' requires 'pillow_heif'. "
                    f"Install it: pip install pillow-heif"
                ),
                file_path=file_path,
                parser_name=self.__class__.__name__
            )

        img = None
        try:
            img = Image.open(file_path)
            img.load() 
        except FileNotFoundError:
            raise ParsingError(message=f"Image file not found: {file_path}", file_path=file_path, parser_name=self.__class__.__name__) from None
        except UnidentifiedImageError as e:
            error_message_str = f"Cannot identify image file: {os.path.basename(file_path)}."
            if file_ext_lower in ['.heic', '.heif'] and not HAS_PILLOW_HEIF:
                error_message_str = f"Pillow (with pillow_heif) cannot identify HEIC/HEIF image: {os.path.basename(file_path)}. File may be corrupt or an unsupported variant."
            
            if not HAS_PILLOW_HEIF and file_ext_lower in ['.heic', '.heif']:
                 error_message_str += " pillow_heif is not installed or failed to initialize."

            raise ParsingError(
                message=error_message_str,
                file_path=file_path,
                parser_name=self.__class__.__name__
            ) from e
        except Exception as e:
            raise ParsingError(message=f"Error loading image {file_path} using Pillow: {e}", file_path=file_path, parser_name=self.__class__.__name__) from e

        parsed_data: Dict[str, Any] = {
            "text": "",
            "original_basename": os.path.basename(file_path),
            "file_path": file_path,
            "image_object": img,
            "original_format": img.format,
            "original_mode": img.mode,
            "original_dimensions": img.size,
            "dimensions_after_ops": img.size,
            "operations_applied": {},
            "output_format": self.default_output_format,
            "output_quality": self.default_quality,
            "output_format_for_base64": "png" if img.format and img.format.upper() in ["HEIC", "HEIF"] else self.default_output_format,
        }
        
        pillow_metadata = get_image_metadata(img)
        parsed_data.update(pillow_metadata)
        if img.format:
            parsed_data['original_format'] = img.format

        current_format = (img.format or self.default_output_format).lower()

        if indices:
            try:
                img_after_ops, applied_ops, final_fmt, final_qual = process_image_operations(
                    img, 
                    indices, 
                    original_format=current_format,
                    default_format=self.default_output_format, 
                    default_quality=self.default_quality
                )
                
                parsed_data["image_object"] = img_after_ops
                parsed_data["operations_applied"] = applied_ops
                parsed_data["dimensions_after_ops"] = img_after_ops.size
                parsed_data["output_format"] = final_fmt.lower()
                parsed_data["output_quality"] = final_qual

                # Update base64 output format based on final_fmt or applied_ops format
                # HEIC/HEIF is a special case, always aiming for PNG for base64 unless format op changes it.
                if img.format and img.format.upper() in ["HEIC", "HEIF"]:
                    if 'format' in applied_ops and applied_ops['format'] != 'png':
                        parsed_data["output_format_for_base64"] = applied_ops['format']
                    else:
                        parsed_data["output_format_for_base64"] = "png" # Default for HEIC base64
                elif 'format' in applied_ops:
                    parsed_data["output_format_for_base64"] = applied_ops['format']
                else:
                    parsed_data["output_format_for_base64"] = final_fmt # Fallback to final_fmt from ops

            except Exception as e_ops: # pylint: disable=broad-except
                # Operations failed, try to use original image properties
                parsed_data["operations_applied"] = {"error_processing_ops": str(e_ops)}
                parsed_data["dimensions_after_ops"] = img.size
                parsed_data["output_format"] = img.format.lower() if img.format else self.default_output_format
                # Quality should remain the parser's default if ops fail, as no specific quality was successfully applied
                parsed_data["output_quality"] = self.default_quality 
                
                if img.format and img.format.upper() in ["HEIC", "HEIF"]:
                    parsed_data["output_format_for_base64"] = "png"
                else:
                    parsed_data["output_format_for_base64"] = img.format.lower() if img.format else self.default_output_format
        else: 
            # No operations string provided, use original image format and parser's default quality
            parsed_data["output_format"] = img.format.lower() if img.format else self.default_output_format
            parsed_data["output_quality"] = self.default_quality # No ops, so this is the effective quality
            
            if img.format and img.format.upper() in ["HEIC", "HEIF"]:
                parsed_data["output_format_for_base64"] = "png"
            else:
                parsed_data["output_format_for_base64"] = img.format.lower() if img.format else self.default_output_format

        if parsed_data.get("output_format_for_base64"):
            parsed_data["output_format_for_base64"] = str(parsed_data["output_format_for_base64"]).lower()
            if parsed_data["output_format_for_base64"] == 'jpg':
                parsed_data["output_format_for_base64"] = 'jpeg'

        return parsed_data

class AudioParser(BaseParser):
    def __init__(self, config: Optional[ActualConfig] = None):
        self._config = config if config else ActualConfig()
        self.default_output_format = getattr(self._config, 'DEFAULT_AUDIO_FORMAT', DEFAULT_AUDIO_FORMAT)
        self.default_samplerate = getattr(self._config, 'DEFAULT_AUDIO_SAMPLERATE', DEFAULT_AUDIO_SAMPLERATE)
        self.default_channels = getattr(self._config, 'DEFAULT_AUDIO_CHANNELS', DEFAULT_AUDIO_CHANNELS)
        self.default_bitrate = getattr(self._config, 'DEFAULT_AUDIO_BITRATE', DEFAULT_AUDIO_BITRATE)

    def parse(self, file_path: str, indices: Optional[str] = None) -> Dict[str, Any]:
        if not AudioSegment: # Global from pydub import
            raise ParsingError("pydub is not installed or available.")

        try:
            audio_segment = AudioSegment.from_file(file_path)
        except FileNotFoundError:
            raise ParsingError(message=f"Audio file not found: {file_path}") from None
        except CouldntDecodeError as e:
            raise ParsingError(message=f"Could not decode audio '{file_path}'. Corrupt or unsupported? Pydub: {e}", file_path=file_path, parser_name=self.__class__.__name__) from e
        except Exception as e:
            raise ParsingError(message=f"Error loading audio '{file_path}' with pydub: {e}", file_path=file_path, parser_name=self.__class__.__name__) from e

        original_basename = os.path.basename(file_path)
        
        parsed_data: Dict[str, Any] = {
            "text": "", 
            "original_basename": original_basename,
            "file_path": file_path,
            "audio_segment": audio_segment, 
        }
        
        # Call utility from .audio_processing
        metadata = get_audio_metadata(audio_segment, file_path)
        parsed_data.update(metadata)

        # Call utility from .audio_processing
        # Pass relevant defaults from self (which are config-aware)
        processed_segment, applied_ops, out_fmt, out_sr, out_ch, out_br = process_audio_operations(
            audio_segment,
            indices, # ops_str
            default_format=self.default_output_format,
            default_samplerate=self.default_samplerate,
            default_channels=self.default_channels,
            default_bitrate=self.default_bitrate
        )

        parsed_data["audio_segment"] = processed_segment
        parsed_data["operations_applied"] = applied_ops
        parsed_data["output_format"] = out_fmt
        parsed_data["output_samplerate"] = out_sr
        parsed_data["output_channels"] = out_ch
        parsed_data["output_bitrate"] = out_br
        
        base_fn, _ = os.path.splitext(original_basename)
        parsed_data["processed_filename_for_api"] = f"{base_fn}.{out_fmt}"

        desc_parts = [f"Audio: {original_basename}"]
        if metadata.get('original_duration_seconds') is not None:
            desc_parts.append(f"Duration: {metadata['original_duration_seconds']:.2f}s")
        if applied_ops:
            ops_str_parts = [f"{k}: {v}" for k, v in applied_ops.items()]
            if ops_str_parts:
                 desc_parts.append(f"Ops: {', '.join(ops_str_parts)}")
        parsed_data["descriptive_text"] = ". ".join(desc_parts) + "."

        return parsed_data

class ParserRegistry:
    """Manages registration and retrieval of parsers."""
    def __init__(self):
        self.parsers: Dict[str, BaseParser] = {}
        self._config: Optional[ActualConfig] = None # To pass to parsers if needed

    def configure(self, config: ActualConfig):
        """Allows global configuration to be passed to the registry, and thus to parsers."""
        self._config = config
        # If parsers are already registered, one might re-initialize them with new config,
        # but current parser __init__ takes config, so new instances get it.

    def register(self, file_type: str, parser_class: type[BaseParser]): # Takes class now
        """Registers a parser class for a given file type."""
        if not issubclass(parser_class, BaseParser):
            raise TypeError("Parser class must be a subclass of BaseParser.")
        # Instantiate the parser, passing the registry's config
        self.parsers[file_type.lower()] = parser_class(config=self._config)

    def get_parser(self, file_type: str) -> BaseParser:
        """Retrieves a registered parser instance by file type."""
        parser = self.parsers.get(file_type.lower())
        
        # Fallback for common type variations (e.g. jpg -> jpeg)
        if not parser:
            if file_type.lower() in ['jpg', 'jpeg']:
                parser = self.parsers.get('jpeg')
            elif file_type.lower() in ['htm', 'html']:
                parser = self.parsers.get('html')
            elif file_type.lower() in ['heic', 'heif']:
                parser = self.parsers.get('heif') or self.parsers.get('heic')
        
        if not parser:
            available = list(self.parsers.keys())
            raise ValueError(f"No parser registered for file type '{file_type}'. Available: {available}")
        return parser

    def unregister(self, file_type: str):
        """Unregisters a parser for a given file type."""
        if file_type.lower() in self.parsers:
            del self.parsers[file_type.lower()]
        # else: # Optionally raise an error or log a warning
            # print(f"Warning: No parser for '{file_type}' to unregister.")

    def list_registered_parsers(self) -> List[str]: 
        """Returns a list of all registered file types."""
        return list(self.parsers.keys())

    def update_parser_config(self, config: ActualConfig):
        """Updates the config for all registered parsers."""
        self._config = config
        for file_type in self.parsers:
            parser_class = type(self.parsers[file_type]) # Get the class of the current instance
            self.parsers[file_type] = parser_class(config=self._config) # Re-instantiate with new config