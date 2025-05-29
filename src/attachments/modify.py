from .core import Attachment, modifier

# Use string literals for type annotations to avoid import issues
# The actual imports are handled by the loader functions


# --- MODIFIERS ---

@modifier
def pages(att: Attachment) -> Attachment:
    """Fallback pages modifier - stores page commands for later processing."""
    # This fallback handles the case when object isn't loaded yet
    # The actual page selection will happen in the type-specific modifiers
    return att

@modifier
def pages(att: Attachment, pdf: 'pdfplumber.PDF') -> Attachment:
    """Extract specific pages from PDF."""
    if 'pages' not in att.commands:
        return att
    
    pages_spec = att.commands['pages']
    selected_pages = []
    
    # Parse page specification
    for part in pages_spec.split(','):
        part = part.strip()
        if '-' in part and not part.startswith('-'):
            start, end = map(int, part.split('-'))
            selected_pages.extend(range(start, end + 1))
        elif part == '-1':
            try:
                total_pages = len(pdf.pages)
                selected_pages.append(total_pages)
            except:
                selected_pages.append(1)
        else:
            selected_pages.append(int(part))
    
    att.metadata['selected_pages'] = selected_pages
    return att


@modifier
def pages(att: Attachment, pres: 'pptx.Presentation') -> Attachment:
    """Extract specific slides from PowerPoint."""
    if 'pages' not in att.commands:
        return att
    
    pages_spec = att.commands['pages']
    selected_slides = []
    
    for part in pages_spec.split(','):
        part = part.strip()
        if '-' in part and not part.startswith('-'):
            start, end = map(int, part.split('-'))
            selected_slides.extend(range(start - 1, end))
        elif part == '-1':
            try:
                selected_slides.append(len(pres.slides) - 1)
            except:
                selected_slides.append(0)
        else:
            selected_slides.append(int(part) - 1)
    
    att.metadata['selected_slides'] = selected_slides
    return att


@modifier
def limit(att: Attachment, df: 'pandas.DataFrame') -> Attachment:
    """Limit pandas DataFrame rows."""
    if 'limit' in att.commands:
        try:
            limit_val = int(att.commands['limit'])
            att._obj = df.head(limit_val)
        except:
            pass
    return att


@modifier
def select(att: Attachment, df: 'pandas.DataFrame') -> Attachment:
    """Select columns from pandas DataFrame."""
    if 'select' in att.commands:
        try:
            columns = [c.strip() for c in att.commands['select'].split(',')]
            att._obj = df[columns]
        except:
            pass
    return att


@modifier
def select(att: Attachment, soup: 'bs4.BeautifulSoup') -> Attachment:
    """
    Generic select modifier that works with different object types.
    Can be used with both command syntax and direct arguments.
    """
    # Check if we have a select command from attachy syntax or direct argument
    if 'select' not in att.commands:
        return att
    
    selector = att.commands['select']
    
    # If we have a BeautifulSoup object, handle CSS selection
    if att._obj and hasattr(att._obj, 'select'):
        # Use CSS selector to find matching elements
        selected_elements = att._obj.select(selector)
        
        if not selected_elements:
            # If no elements found, create empty soup
            from bs4 import BeautifulSoup
            new_soup = BeautifulSoup("", 'html.parser')
        elif len(selected_elements) == 1:
            # If single element, use it directly
            from bs4 import BeautifulSoup
            new_soup = BeautifulSoup(str(selected_elements[0]), 'html.parser')
        else:
            # If multiple elements, wrap them in a container
            from bs4 import BeautifulSoup
            container_html = ''.join(str(elem) for elem in selected_elements)
            new_soup = BeautifulSoup(f"<div>{container_html}</div>", 'html.parser')
        
        # Update the attachment with selected content
        att._obj = new_soup
        
        # Update metadata to track the selection
        att.metadata.update({
            'selector': selector,
            'selected_count': len(selected_elements),
            'selection_applied': True
        })
    
    return att

@modifier  
def crop(att: Attachment, img: 'PIL.Image.Image') -> Attachment:
    """Crop: [crop:x1,y1,x2,y2] (box: left, upper, right, lower)"""
    if 'crop' not in att.commands:
        return att
    box = att.commands['crop']
    # Accept string "x1,y1,x2,y2" or tuple/list
    if isinstance(box, str):
        try:
            box = [int(x) for x in box.split(',')]
        except Exception:
            raise ValueError(f"Invalid crop box format: {att.commands['crop']!r}")
    if not (isinstance(box, (list, tuple)) and len(box) == 4):
        raise ValueError(f"Crop box must be 4 values (x1,y1,x2,y2), got: {box!r}")
    x1, y1, x2, y2 = box
    # Use the box as provided, do not reorder coordinates
    if x2 <= x1 or y2 <= y1:
        raise ValueError(f"Invalid crop box: right <= left or lower <= upper ({x1},{y1},{x2},{y2})")
    att._obj = img.crop((x1, y1, x2, y2))
    return att

@modifier
def rotate(att: Attachment, img: 'PIL.Image.Image') -> Attachment:
    """Rotate: [rotate:degrees] (positive = clockwise)"""
    if 'rotate' in att.commands:
        att._obj = img.rotate(-float(att.commands['rotate']), expand=True)
    return att

@modifier
def resize(att: Attachment, img: 'PIL.Image.Image') -> Attachment:
    """Resize: [resize:50%] or [resize:800x600] or [resize:800]"""
    if 'resize' not in att.commands:
        return att
    
    resize_spec = att.commands['resize']
    original_width, original_height = img.size
    
    try:
        if resize_spec.endswith('%'):
            # Percentage scaling: "50%" -> scale to 50% of original size
            percentage = float(resize_spec[:-1]) / 100.0
            new_width = int(original_width * percentage)
            new_height = int(original_height * percentage)
        elif 'x' in resize_spec:
            # Dimension specification: "800x600" -> specific width and height
            width_str, height_str = resize_spec.split('x', 1)
            new_width = int(width_str)
            new_height = int(height_str)
        else:
            # Single dimension: "800" -> scale proportionally to this width
            new_width = int(resize_spec)
            aspect_ratio = original_height / original_width
            new_height = int(new_width * aspect_ratio)
        
        # Ensure minimum size of 1x1
        new_width = max(1, new_width)
        new_height = max(1, new_height)
        
        att._obj = img.resize((new_width, new_height))
        att.metadata.update({
            'resize_applied': True,
            'original_size': (original_width, original_height),
            'new_size': (new_width, new_height),
            'resize_spec': resize_spec
        })
        
    except (ValueError, ZeroDivisionError) as e:
        # If resize fails, keep original image and log the error
        att.metadata.update({
            'resize_error': f"Invalid resize specification '{resize_spec}': {str(e)}"
        })
    
    return att

@modifier
def watermark(att: Attachment, img: 'PIL.Image.Image') -> Attachment:
    """Add watermark to image: [watermark:text] or [watermark:text|position|style]
    
    DSL Commands:
    - [watermark:My Text] - Simple text watermark (bottom-right)
    - [watermark:My Text|bottom-left] - Custom position
    - [watermark:My Text|center|large] - Custom position and style
    - [watermark:auto] - Auto watermark with filename
    
    Positions: bottom-right, bottom-left, top-right, top-left, center
    Styles: small, medium, large (affects font size and background)
    
    By default, applies auto watermark if no watermark command is specified.
    """
    # Apply default auto watermark if no command specified
    if 'watermark' not in att.commands:
        att.commands['watermark'] = 'auto'
    
    try:
        from PIL import ImageDraw, ImageFont, Image
        import os
        
        # Parse watermark command
        watermark_spec = att.commands['watermark']
        parts = watermark_spec.split('|')
        
        # Extract parameters
        text = parts[0].strip()
        position = parts[1].strip() if len(parts) > 1 else 'bottom-right'
        style = parts[2].strip() if len(parts) > 2 else 'medium'
        
        # Handle auto watermark
        if text.lower() == 'auto':
            if att.path:
                filename = os.path.basename(att.path)
                if len(filename) > 25:
                    filename = filename[:22] + "..."
                text = f"📄 {filename}"
            else:
                text = "📄 Image"
        
        # Create a copy of the image to modify
        watermarked_img = img.copy()
        draw = ImageDraw.Draw(watermarked_img)
        
        # Configure font based on style
        img_width, img_height = watermarked_img.size
        
        if style == 'small':
            font_size = max(8, min(img_width, img_height) // 80)
            bg_padding = 1
        elif style == 'large':
            font_size = max(16, min(img_width, img_height) // 30)
            bg_padding = 4
        else:  # medium (default)
            font_size = max(12, min(img_width, img_height) // 50)
            bg_padding = 2
        
        # Try to load font
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)
        except:
            try:
                font = ImageFont.load_default()
            except:
                # If no font available, skip watermarking
                return att
        
        # Get text dimensions
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        # Calculate position
        margin = max(5, font_size // 2)
        
        if position == 'bottom-right':
            text_x = img_width - text_width - margin
            text_y = img_height - text_height - margin
        elif position == 'bottom-left':
            text_x = margin
            text_y = img_height - text_height - margin
        elif position == 'top-right':
            text_x = img_width - text_width - margin
            text_y = margin
        elif position == 'top-left':
            text_x = margin
            text_y = margin
        elif position == 'center':
            text_x = (img_width - text_width) // 2
            text_y = (img_height - text_height) // 2
        else:
            # Default to bottom-right for unknown positions
            text_x = img_width - text_width - margin
            text_y = img_height - text_height - margin
        
        # Ensure text stays within image bounds
        text_x = max(0, min(text_x, img_width - text_width))
        text_y = max(0, min(text_y, img_height - text_height))
        
        # Draw background rectangle
        bg_coords = [
            text_x - bg_padding,
            text_y - bg_padding,
            text_x + text_width + bg_padding,
            text_y + text_height + bg_padding
        ]
        
        # Create a semi-transparent overlay for the background
        overlay = Image.new('RGBA', watermarked_img.size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        
        # Choose background transparency based on style
        if style == 'large':
            bg_alpha = 160  # More transparent for large text
        else:
            bg_alpha = 180  # Semi-transparent for smaller text
        
        overlay_draw.rectangle(bg_coords, fill=(0, 0, 0, bg_alpha))
        
        # Composite the overlay onto the main image
        watermarked_img = Image.alpha_composite(watermarked_img.convert('RGBA'), overlay).convert('RGB')
        
        # Redraw on the composited image
        draw = ImageDraw.Draw(watermarked_img)
        
        # Draw the text in white
        draw.text((text_x, text_y), text, fill=(255, 255, 255), font=font)
        
        # Update the attachment with watermarked image
        att._obj = watermarked_img
        
        # Add metadata about watermarking
        att.metadata.setdefault('processing', []).append({
            'operation': 'watermark',
            'text': text,
            'position': position,
            'style': style,
            'font_size': font_size
        })
        
        return att
        
    except Exception as e:
        # If watermarking fails, return original attachment
        att.metadata.setdefault('processing_errors', []).append({
            'operation': 'watermark',
            'error': str(e)
        })
    return att


# --- URL MORPHING MODIFIER ---

@modifier
def morph_to_detected_type(att: Attachment, response: 'requests.Response') -> Attachment:
    """
    Intelligently detect file type from URL response using enhanced matchers.
    
    This modifier leverages the enhanced matcher system which checks file extensions,
    Content-Type headers, and magic numbers. No hardcoded lists needed!
    
    Usage: attach(url) | load.url_to_response | modify.morph_to_detected_type | [existing matchers]
    """
    from pathlib import Path
    from urllib.parse import urlparse
    from io import BytesIO
    
    # Preserve original URL for display purposes
    original_url = att.metadata.get('original_url', att.path)
    parsed_url = urlparse(original_url)
    
    # Keep the original URL as the path for display, but also save it in metadata
    att.path = original_url
    
    # Store content in memory - matchers need this for Content-Type and magic number detection!
    att._file_content = BytesIO(response.content)
    att._file_content.seek(0)
    att._response = response
    
    # Clear _obj so subsequent loaders can properly load the detected type
    att._obj = None
    
    # Update metadata with detection info AND preserve display URL
    att.metadata.update({
        'detection_method': 'enhanced_matcher_based',
        'response_content_type': response.headers.get('content-type', ''),
        'content_length': len(response.content),
        'is_binary': _is_likely_binary(response.content[:1024]),  # Check first 1KB
        'display_url': original_url,  # Preserve for presenters to use instead of temp paths
    })
    
    return att


def _is_likely_binary(content_sample: bytes) -> bool:
    """Check if content appears to be binary (has non-text bytes)."""
    if not content_sample:
        return False
    
    # Check for null bytes (strong indicator of binary)
    if b'\x00' in content_sample:
        return True
    
    # Check percentage of non-printable characters
    try:
        # Try to decode as UTF-8
        content_sample.decode('utf-8')
        # If successful, it's likely text
        return False
    except UnicodeDecodeError:
        # If decode fails, it's likely binary
        return True


# Removed all the old hardcoded detection functions - they are no longer needed!
# The enhanced matchers in matchers.py now handle all the intelligence.