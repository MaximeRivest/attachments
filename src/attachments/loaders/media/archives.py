"""Archive loaders - ZIP files containing images."""

import io
from ...core import Attachment, loader, AttachmentCollection
from ... import matchers


@loader(match=matchers.zip_match)
def zip_to_images(att: Attachment) -> 'AttachmentCollection':
    """Load ZIP file containing images into AttachmentCollection with automatic input source handling."""
    try:
        import zipfile
        from PIL import Image
        
        attachments = []
        
        # Use the new input_source property - no more repetitive patterns!
        zip_source = att.input_source
        
        with zipfile.ZipFile(zip_source, 'r') as zip_file:
            for file_info in zip_file.filelist:
                if file_info.filename.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.heic', '.heif')):
                    # Create attachment for each image
                    img_att = Attachment(file_info.filename)
                    
                    # Copy commands from original attachment (for vectorized processing)
                    img_att.commands = att.commands.copy()
                    
                    # Load image from zip
                    with zip_file.open(file_info.filename) as img_file:
                        img_data = img_file.read()
                        img = Image.open(io.BytesIO(img_data))
                        img_att._obj = img
                        
                        # Store metadata
                        img_att.metadata.update({
                            'format': getattr(img, 'format', 'Unknown'),
                            'size': getattr(img, 'size', (0, 0)),
                            'mode': getattr(img, 'mode', 'Unknown'),
                            'from_zip': att.path,
                            'zip_filename': file_info.filename
                        })
                    
                    attachments.append(img_att)
        
        return AttachmentCollection(attachments)
        
    except ImportError:
        raise ImportError("Pillow is required for image processing. Install with: pip install Pillow")
    except Exception as e:
        raise ValueError(f"Could not load ZIP file: {e}") 