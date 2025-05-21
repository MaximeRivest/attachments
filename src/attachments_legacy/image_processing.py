import base64
import io
from PIL import Image, ImageOps, ExifTags
from typing import Dict, Any, Optional, Tuple, List
from .exceptions import ImageProcessingError

# Placeholder for image processing module 

DEFAULT_IMAGE_OUTPUT_FORMAT = "jpeg" # Common default
IMAGE_WIDTH_LIMIT = 2048 # A sensible default limit for image width processing 
DEFAULT_IMAGE_QUALITY = 75

def get_image_metadata(img: Image.Image) -> Dict[str, Any]:
    metadata = {}
    try:
        exif_attr = getattr(img, '_getexif', None)
        if exif_attr is not None:
            exif_data_raw = exif_attr() if callable(exif_attr) else exif_attr
        else:
            exif_data_raw = None
        if exif_data_raw is not None:
            exif_data = {ExifTags.TAGS.get(tag, tag): value for tag, value in exif_data_raw.items()}
            # Basic serialization: ensure values are simple types for broader compatibility (e.g., XML, JSON)
            metadata['exif'] = {k: v for k, v in exif_data.items() if isinstance(v, (str, int, float, bool, bytes))}
            if 'exif' in metadata and isinstance(metadata['exif'], dict):
                for key, val in metadata['exif'].items():
                    if isinstance(val, bytes):
                        try:
                            metadata['exif'][key] = val.decode('utf-8', errors='replace')
                        except UnicodeDecodeError:
                            metadata['exif'][key] = f'bytes_len_{len(val)}' # Placeholder for non-decodable bytes
            
            if 'DateTimeOriginal' in exif_data: metadata['datetime_original'] = exif_data['DateTimeOriginal']
            if 'Make' in exif_data: metadata['camera_make'] = exif_data['Make']
            if 'Model' in exif_data: metadata['camera_model'] = exif_data['Model']
            if 'GPSInfo' in exif_data:
                gps_info_raw = exif_data['GPSInfo']
                gps_info_processed = {}
                for k, v in gps_info_raw.items():
                    tag_name = ExifTags.GPSTAGS.get(k, k)
                    gps_info_processed[tag_name] = v
                metadata['gps_info'] = gps_info_processed

    except Exception: # pylint: disable=broad-except
        metadata['exif'] = None # Indicate failure to extract or process EXIF
    return metadata

def parse_image_op_string(ops_str: Optional[str], 
                          initial_format: str, 
                          initial_width: int, 
                          initial_height: int, 
                          initial_quality: int) -> Tuple[Dict[str, Any], List[str]]:
    """Helper to parse the image operation string into a dictionary of requested operations."""
    op_requests: Dict[str, Any] = {
        'format': initial_format,
        'resize': None, 
        'quality': initial_quality,
        'rotate': None 
    }
    summary_parts: List[str] = []

    if not ops_str:
        return op_requests, summary_parts

    # Ensure ops_str is treated as a string before stripping, and handle potential empty string after strip
    ops_str_cleaned = ops_str.lower().strip('[]')
    if not ops_str_cleaned: # If ops string was just "[]"
        return op_requests, summary_parts
        
    operations = ops_str_cleaned.split(',')
    for op_detail_str in operations:
        op_detail_str = op_detail_str.strip() # Strip each part
        if not op_detail_str: continue # Skip empty parts from "op1,,op2"

        parts = op_detail_str.split(':', 1)
        if len(parts) != 2:
            continue
        op_key, op_value = parts[0].strip(), parts[1].strip()

        if op_key == 'format':
            if op_value in ['jpg', 'jpeg', 'png', 'webp', 'gif', 'bmp', 'tiff']:
                op_requests['format'] = 'jpeg' if op_value == 'jpg' else op_value
                summary_parts.append(f"format to {op_requests['format']}")
        elif op_key == 'resize':
            try:
                if 'x' not in op_value: continue # Ensure 'x' is present
                w_str, h_str = op_value.split('x', 1)
                w: Any = int(w_str) if w_str != 'auto' else 'auto'
                h: Any = int(h_str) if h_str != 'auto' else 'auto'
                
                # Validate numeric parts if not 'auto'
                if isinstance(w, int) and w <= 0: continue
                if isinstance(h, int) and h <= 0: continue
                if w == 'auto' and h == 'auto' and (initial_width == 0 or initial_height == 0) : # Avoid div by zero if original dims are unknown/zero
                    continue


                op_requests['resize'] = (w, h)
                summary_parts.append(f"resize to {w_str}x{h_str}")
            except ValueError:
                pass # Invalid resize format
        elif op_key == 'quality':
            try:
                q = int(op_value)
                if 0 <= q <= 100:
                    op_requests['quality'] = q
                    summary_parts.append(f"quality to {q}")
            except ValueError:
                pass 
        elif op_key == 'rotate':
            try:
                angle = float(op_value)
                op_requests['rotate'] = angle
                summary_parts.append(f"rotate by {angle}°")
            except ValueError:
                pass
        elif op_key == 'grayscale' or op_key == 'greyscale':
            op_requests['grayscale'] = True
            summary_parts.append("to grayscale")
            
    return op_requests, summary_parts

def process_image_operations(
    img: Image.Image, 
    ops_str: Optional[str], 
    original_format: str, 
    default_format: str, 
    default_quality: int
) -> Tuple[Image.Image, Dict[str, Any], str, int]:
    """Applies image operations based on an operation string."""
    img_modified = img.copy() # Work on a copy
    applied_ops_summary: Dict[str, Any] = {}

    # Use original_format as the initial_format for parsing.
    # default_quality is the fallback if no quality op is found or if it's invalid.
    op_requests, _ = parse_image_op_string(ops_str, 
                                         original_format, 
                                         img.width, 
                                         img.height, 
                                         default_quality) # default_quality acts as initial_quality for parsing

    # Determine target format and quality based on parsed ops or fallbacks
    target_format = op_requests.get('format', original_format).lower()
    target_quality = op_requests.get('quality', default_quality)

    # If at least one NON-format operation is requested (resize / rotate / grayscale / quality)
    # and the caller did not explicitly set a new format, fall back to the default_format.
    explicit_format_requested = ops_str is not None and 'format' in ops_str.lower()
    non_format_ops_requested = any([
        op_requests.get('resize'),
        op_requests.get('rotate') is not None,
        op_requests.get('grayscale'),
        (ops_str is not None and 'quality' in ops_str.lower())
    ])
    if non_format_ops_requested and not explicit_format_requested:
        target_format = default_format.lower()

    # Apply resize if requested
    if op_requests.get('resize'):
        w_op, h_op = op_requests['resize'] # w_op, h_op can be 'auto' or int
        orig_w, orig_h = img_modified.size
        
        final_w, final_h = orig_w, orig_h # Start with original dimensions

        # Determine actual target dimensions
        if w_op == 'auto' and h_op == 'auto':
            pass # No change
        elif w_op == 'auto':
            if isinstance(h_op, int) and h_op > 0 and orig_h > 0:
                final_h = h_op
                final_w = int(orig_w * (h_op / orig_h))
            # else: invalid 'auto' combination or zero original dimension, no resize
        elif h_op == 'auto':
            if isinstance(w_op, int) and w_op > 0 and orig_w > 0:
                final_w = w_op
                final_h = int(orig_h * (w_op / orig_w))
            # else: invalid 'auto' combination or zero original dimension, no resize
        elif isinstance(w_op, int) and isinstance(h_op, int) and w_op > 0 and h_op > 0:
            final_w, final_h = w_op, h_op
        
        # Only apply resize if dimensions actually change and are valid
        if (final_w != orig_w or final_h != orig_h) and final_w > 0 and final_h > 0:
            current_w_for_limit, current_h_for_limit = final_w, final_h
            # Apply IMAGE_WIDTH_LIMIT
            if current_w_for_limit > IMAGE_WIDTH_LIMIT:
                ratio = IMAGE_WIDTH_LIMIT / current_w_for_limit
                final_w = IMAGE_WIDTH_LIMIT
                final_h = int(current_h_for_limit * ratio)
                applied_ops_summary['resize_adjusted_to_limit'] = (final_w, final_h) # Note adjustment
            
            if final_w > 0 and final_h > 0: # Ensure dimensions are still valid after potential adjustment
                try:
                    img_modified = img_modified.resize((final_w, final_h), Image.Resampling.LANCZOS)
                    applied_ops_summary['resize'] = op_requests['resize'] # Store original 'auto' request for clarity
                except Exception: # pylint: disable=broad-except
                    # If resize fails, remove from summary if it was added
                    if 'resize' in applied_ops_summary: del applied_ops_summary['resize']
                    if 'resize_adjusted_to_limit' in applied_ops_summary: del applied_ops_summary['resize_adjusted_to_limit']

    # Apply rotation if requested
    if op_requests.get('rotate') is not None:
        try:
            angle = float(op_requests['rotate'])
            img_modified = img_modified.rotate(angle, expand=True) # expand=True is important
            applied_ops_summary['rotate'] = angle
        except (ValueError, TypeError, Exception): # pylint: disable=broad-except
            pass # Failed to rotate

    # Apply grayscale if requested
    if op_requests.get('grayscale'):
        try:
            img_modified = ImageOps.grayscale(img_modified)
            applied_ops_summary['grayscale'] = True
        except Exception: # pylint: disable=broad-except
            pass # Failed to grayscale

    # Summarize format change if it occurred and is different from original
    if explicit_format_requested and target_format != original_format.lower():
        applied_ops_summary['format'] = target_format
    
    # Always record the output quality so downstream consumers/tests can rely on it
    applied_ops_summary['quality'] = target_quality

    return img_modified, applied_ops_summary, target_format, target_quality

def pil_to_base64(img_obj: Image.Image, item_data: dict) -> str:
    '''Converts a Pillow Image object to a base64 encoded string.'''
    # Use output_format from item_data if available, otherwise output_format_for_base64, then default
    output_format_str = item_data.get('output_format', 
                             item_data.get('output_format_for_base64', 
                                           DEFAULT_IMAGE_OUTPUT_FORMAT)).lower()
    if output_format_str == 'jpg': output_format_str = 'jpeg'

    quality_val = item_data.get('output_quality')
    # Use DEFAULT_IMAGE_QUALITY (global, now 75) only if quality_val is strictly None from item_data
    quality = quality_val if quality_val is not None else DEFAULT_IMAGE_QUALITY

    # Ensure quality is int and in range, otherwise use global default
    if not isinstance(quality, int) or not (0 <= quality <= 100):
        quality = DEFAULT_IMAGE_QUALITY


    buffer = io.BytesIO()
    try:
        img_to_save = img_obj
        # Handle transparency for JPEG
        if output_format_str == 'jpeg' and img_obj.mode in ('RGBA', 'LA', 'P'):
            # Create a white background image
            background = Image.new("RGB", img_obj.size, (255, 255, 255))
            # Paste the image onto the background using the alpha channel as a mask
            if img_obj.mode == 'P': # Palette mode, convert to RGBA first
                img_converted_to_rgba = img_obj.convert("RGBA")
                background.paste(img_converted_to_rgba, mask=img_converted_to_rgba.split()[-1])
            else: # RGBA or LA
                background.paste(img_obj, mask=img_obj.split()[-1]) # Use alpha from original
            img_to_save = background
        
        img_to_save.save(buffer, format=output_format_str, quality=quality)
    except Exception as e:
        # If save with quality fails, try without quality (for formats that don't support it like GIF)
        if 'quality' in str(e).lower():
            try:
                buffer = io.BytesIO() # Reset buffer
                img_to_save.save(buffer, format=output_format_str)
            except Exception as e_no_quality:
                # If still fails, raise with the no_quality error
                raise ImageProcessingError(f"Could not convert image to base64 (format: {output_format_str}): {e_no_quality}") from e_no_quality
        else:
            # If it's not a quality error, raise the original error
            raise ImageProcessingError(f"Could not convert image to base64 (format: {output_format_str}): {e}") from e

    return base64.b64encode(buffer.getvalue()).decode('utf-8') 