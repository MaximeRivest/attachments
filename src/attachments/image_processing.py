import base64
import io
from PIL import Image, ImageOps
from .exceptions import ImageProcessingError

# Placeholder for image processing module 

DEFAULT_IMAGE_OUTPUT_FORMAT = "jpeg" # Common default
IMAGE_WIDTH_LIMIT = 2048 # A sensible default limit for image width processing 
DEFAULT_IMAGE_QUALITY = 85

def pil_to_base64(img_obj: Image.Image, item_data: dict) -> str:
    '''Converts a Pillow Image object to a base64 encoded string.'''
    output_format_str = item_data.get('output_format_for_base64', DEFAULT_IMAGE_OUTPUT_FORMAT).lower()
    if output_format_str == 'jpg': output_format_str = 'jpeg'

    quality_val = item_data.get('output_quality')
    quality = quality_val if quality_val is not None else DEFAULT_IMAGE_QUALITY

    if not isinstance(quality, int) or not (0 <= quality <= 100):
        quality = DEFAULT_IMAGE_QUALITY

    buffer = io.BytesIO()
    try:
        img_to_save = img_obj
        if output_format_str == 'jpeg' and img_obj.mode in ('RGBA', 'LA', 'P'):
            if img_obj.mode == 'P':
                img_converted_to_rgba = img_obj.convert("RGBA")
                background = Image.new("RGB", img_converted_to_rgba.size, (255, 255, 255))
                background.paste(img_converted_to_rgba, mask=img_converted_to_rgba.split()[-1])
            else:
                background = Image.new(img_obj.mode[:-1], img_obj.size, (255, 255, 255))
                background.paste(img_obj, mask=img_obj.split()[-1])
            img_to_save = background
        
        img_to_save.save(buffer, format=output_format_str, quality=quality)
    except Exception as e:
        if 'quality' in str(e).lower():
            try:
                buffer = io.BytesIO()
                img_to_save.save(buffer, format=output_format_str)
            except Exception as e_no_quality:
                raise ImageProcessingError(f'''Could not convert image to base64 (format: {output_format_str}): {e_no_quality}''') from e_no_quality
        else:
            raise ImageProcessingError(f'''Could not convert image to base64 (format: {output_format_str}): {e}''') from e

    return base64.b64encode(buffer.getvalue()).decode('utf-8') 