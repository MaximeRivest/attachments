"""Tiling modifier that creates contact sheet mosaics from images."""

import base64
import io
import math
from typing import List, Optional

try:
    from PIL import Image, ImageDraw, ImageFont
    _pil_available = True
except ImportError:
    _pil_available = False

from ..core.decorators import modifier
from ..core.attachment import Attachment


class TiledContent:
    """Container for content with a tiled contact sheet overview."""
    
    def __init__(self, original_content, tiled_image: str, individual_images: List[str]):
        self.original_content = original_content
        self.tiled_image = tiled_image  # Base64 contact sheet
        self.individual_images = individual_images
        self.images = [tiled_image] + individual_images  # Tiled first, then individuals
    
    def __str__(self) -> str:
        return str(self.original_content)


def create_tiled_contact_sheet(images: List[str], 
                               thumb_width: int = 200, 
                               thumb_height: int = 150,
                               spacing: int = 10) -> Optional[str]:
    """Create a tiled contact sheet mosaic from a list of images."""
    if not images or not _pil_available:
        return None
    
    try:
        # Calculate grid dimensions (roughly square)
        num_images = len(images)
        cols = math.ceil(math.sqrt(num_images))
        rows = math.ceil(num_images / cols)
        
        # Create the contact sheet
        contact_width = cols * thumb_width + (cols - 1) * spacing
        contact_height = rows * thumb_height + (rows - 1) * spacing
        contact_sheet = Image.new('RGB', (contact_width, contact_height), color='white')
        
        for idx, img_data_url in enumerate(images):
            # Extract base64 data and create PIL image
            if not img_data_url.startswith("data:image/"):
                continue
                
            base64_data = img_data_url.split(",", 1)[1]
            img_bytes = base64.b64decode(base64_data)
            slide_img = Image.open(io.BytesIO(img_bytes))
            
            # Resize to thumbnail
            slide_img.thumbnail((thumb_width, thumb_height), Image.Resampling.LANCZOS)
            
            # Calculate position
            row = idx // cols
            col = idx % cols
            x = col * (thumb_width + spacing)
            y = row * (thumb_height + spacing)
            
            # Paste onto contact sheet
            contact_sheet.paste(slide_img, (x, y))
        
        # Add labels if we have font support
        try:
            font = ImageFont.load_default()
            draw = ImageDraw.Draw(contact_sheet)
            
            for idx in range(min(num_images, rows * cols)):
                row = idx // cols
                col = idx % cols
                x = col * (thumb_width + spacing)
                y = row * (thumb_height + spacing)
                
                # Add small page number
                draw.text((x + 5, y + 5), str(idx + 1), fill='red', font=font)
                
        except Exception:
            pass  # No font support, skip labels
        
        # Convert contact sheet to base64
        contact_byte_arr = io.BytesIO()
        contact_sheet.save(contact_byte_arr, format='PNG')
        contact_bytes = contact_byte_arr.getvalue()
        contact_b64 = base64.b64encode(contact_bytes).decode('utf-8')
        
        return f"data:image/png;base64,{contact_b64}"
        
    except Exception as e:
        print(f"Warning: Could not create tiled overview: {e}")
        return None


@modifier
def tile(att: Attachment) -> Attachment:
    """
    Create a tiled contact sheet from document images.
    
    This modifier takes an attachment that can generate images (like PDFs, PowerPoints)
    and creates a contact sheet mosaic showing all pages/slides as thumbnails.
    
    Args:
        att: Attachment with content that can generate images
        
    Returns:
        Modified attachment with TiledContent that includes contact sheet
    """
    if not _pil_available:
        print("Warning: PIL not available, skipping tiling")
        return att
    
    # Get images from the current content
    from ..presenters.images import images as present_images
    
    try:
        # Present the content as images
        image_result = present_images(att)
        if not image_result or not image_result.content:
            # No images to tile
            return att
        
        individual_images = image_result.content
        
        # Create tiled contact sheet
        tiled_image = create_tiled_contact_sheet(individual_images)
        
        if tiled_image:
            # Create new content with tiled overview
            tiled_content = TiledContent(
                original_content=att.content,
                tiled_image=tiled_image,
                individual_images=individual_images
            )
            
            # Return new attachment with tiled content
            return Attachment(
                content=tiled_content,
                source=att.source + "[tiled]"
            )
        else:
            return att
            
    except Exception as e:
        print(f"Warning: Could not apply tiling: {e}")
        return att 