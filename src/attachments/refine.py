from .core import Attachment, refiner
from typing import Union
import os

# --- REFINERS ---

@refiner
def truncate(att: Attachment, limit: int = None) -> Attachment:
    """Truncate text content to specified character limit."""
    # Get limit from DSL commands or parameter
    if limit is None:
        limit = int(att.commands.get('truncate', 1000))
    
    if att.text and len(att.text) > limit:
        att.text = att.text[:limit] + "..."
        # Add metadata about truncation
        att.metadata.setdefault('processing', []).append({
            'operation': 'truncate',
            'original_length': len(att.text) + len("...") - 3,
            'truncated_length': len(att.text)
        })
    
    return att

@refiner
def add_headers(att: Attachment) -> Attachment:
    """Add markdown headers to text content."""
    if att.text:
        # Check if a header already exists for this file anywhere in the text
        filename = getattr(att, 'path', 'Document')
        
        # Common header patterns that presenters might use
        header_patterns = [
            f"# {filename}",                    # Full path header
            f"# PDF Document: {filename}",       # PDF presenter pattern
            f"# Image: {filename}",              # Image presenter pattern  
            f"# Presentation: {filename}",       # PowerPoint presenter pattern
            f"## Data from {filename}",          # DataFrame presenter pattern
            f"Data from {filename}",             # Plain text presenter pattern
            f"PDF Document: {filename}",         # Plain text PDF pattern
        ]
        
        # Also check for just the basename in headers (in case of long paths)
        basename = os.path.basename(filename) if filename else 'Document'
        if basename != filename:
            header_patterns.extend([
                f"# {basename}",
                f"# PDF Document: {basename}",
                f"# Image: {basename}",
                f"# Presentation: {basename}",
                f"## Data from {basename}",
            ])
        
        # Check if any header pattern already exists
        has_header = any(pattern in att.text for pattern in header_patterns)
        
        # Only add header if none exists
        if not has_header:
            att.text = f"# {filename}\n\n{att.text}"
    
    return att

@refiner
def format_tables(att: Attachment) -> Attachment:
    """Format table content for better readability."""
    if att.text:
        # Simple table formatting - could be enhanced
        att.text = att.text.replace('\t', ' | ')
    return att

@refiner
def tile_images(input_obj: Union['AttachmentCollection', Attachment]) -> Attachment:
    """Combine multiple images into a tiled grid.
    
    Works with:
    - AttachmentCollection: Each attachment contributes images
    - Single Attachment: Multiple images in att.images list (e.g., PDF pages)
    
    DSL Commands:
    - [tile:2x2] - 2x2 grid
    - [tile:3x1] - 3x1 grid  
    - [tile:4] - 4x4 grid
    - [tile:false] - Disable tiling (keep images separate)
    
    Default: 2x2 grid for multiple images (can be disabled with tile:false)
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
        from .core import Attachment, AttachmentCollection
        import io
        import base64
        
        # Collect all images and get tile configuration
        images = []
        tile_config = '2x2'  # default
        
        if isinstance(input_obj, AttachmentCollection):
            # Handle AttachmentCollection - collect images from all attachments
            for att in input_obj.attachments:
                if hasattr(att, '_obj') and isinstance(att._obj, Image.Image):
                    images.append(att._obj)
                elif att.images:
                    # Decode base64 images
                    for img_b64 in att.images:
                        try:
                            # Handle both data URLs and raw base64
                            if img_b64.startswith('data:image/'):
                                img_data_b64 = img_b64.split(',', 1)[1]
                            else:
                                img_data_b64 = img_b64
                            
                            img_data = base64.b64decode(img_data_b64)
                            img = Image.open(io.BytesIO(img_data))
                            images.append(img.convert('RGB'))
                        except Exception:
                            continue
            
            # Get tile config from first attachment
            if input_obj.attachments:
                tile_config = input_obj.attachments[0].commands.get('tile', '2x2')
                
        else:
            # Handle single Attachment with multiple images (e.g., PDF pages)
            att = input_obj
            tile_config = att.commands.get('tile', '2x2')
            
            if hasattr(att, '_obj') and isinstance(att._obj, Image.Image):
                images.append(att._obj)
            elif att.images:
                # Decode base64 images from att.images list
                for img_b64 in att.images:
                    try:
                        # Handle both data URLs and raw base64
                        if img_b64.startswith('data:image/'):
                            img_data_b64 = img_b64.split(',', 1)[1]
                        else:
                            img_data_b64 = img_b64
                        
                        img_data = base64.b64decode(img_data_b64)
                        img = Image.open(io.BytesIO(img_data))
                        images.append(img.convert('RGB'))
                    except Exception:
                        continue
        
        # Check if tiling is disabled
        if tile_config.lower() in ('false', 'no', 'off', 'disable', 'disabled'):
            # Tiling disabled - return original images without tiling
            if isinstance(input_obj, Attachment):
                return input_obj
            else:
                return Attachment("")
        
        if not images:
            # No images to tile, return original or empty attachment
            if isinstance(input_obj, Attachment):
                return input_obj
            else:
                return Attachment("")
        
        # If only one image, no need to tile
        if len(images) == 1:
            if isinstance(input_obj, Attachment):
                return input_obj
            else:
                return Attachment("")
        
        # Parse tile configuration (e.g., "2x2", "3x1", "4")
        if 'x' in tile_config:
            cols, rows = map(int, tile_config.split('x'))
        else:
            # Square grid
            size = int(tile_config)
            cols = rows = size
        
        # Calculate how many tiles we need for all images
        img_count = len(images)
        images_per_tile = cols * rows
        num_tiles = (img_count + images_per_tile - 1) // images_per_tile  # Ceiling division
        
        if num_tiles == 0:
            # No images to tile, return original or empty attachment
            if isinstance(input_obj, Attachment):
                return input_obj
            else:
                return Attachment("")
        
        # Create result attachment
        if isinstance(input_obj, Attachment):
            result = input_obj  # Preserve original attachment properties
        else:
            result = Attachment("")
        
        # Generate multiple tiles if needed
        tiled_images = []
        
        for tile_idx in range(num_tiles):
            start_idx = tile_idx * images_per_tile
            end_idx = min(start_idx + images_per_tile, img_count)
            tile_images_subset = images[start_idx:end_idx]
            
            if not tile_images_subset:
                continue
            
            # Calculate actual grid size for this tile (may be smaller for last tile)
            actual_img_count = len(tile_images_subset)
            if actual_img_count < images_per_tile:
                # For partial tiles, use optimal layout
                import math
                actual_cols = min(cols, actual_img_count)
                actual_rows = math.ceil(actual_img_count / actual_cols)
            else:
                actual_cols, actual_rows = cols, rows
            
            # Resize all images to same size (use the smallest dimensions for efficiency)
            min_width = min(img.size[0] for img in tile_images_subset)
            min_height = min(img.size[1] for img in tile_images_subset)
            
            # Don't make images too small
            min_width = max(min_width, 100)
            min_height = max(min_height, 100)
            
            resized_images = [img.resize((min_width, min_height)) for img in tile_images_subset]
            
            # Create tiled image for this tile
            tile_width = min_width * actual_cols
            tile_height = min_height * actual_rows
            tiled_img = Image.new('RGB', (tile_width, tile_height), 'white')
            
            for i, img in enumerate(resized_images):
                row = i // actual_cols
                col = i % actual_cols
                x = col * min_width
                y = row * min_height
                tiled_img.paste(img, (x, y))
                
                # Add watermark with document path in bottom corner
                try:
                    from PIL import ImageDraw, ImageFont
                    
                    # Get the document path for watermark
                    if isinstance(input_obj, Attachment) and input_obj.path:
                        # Extract just the filename for cleaner watermark
                        doc_name = os.path.basename(input_obj.path)
                        
                        # Create drawing context for this tile section
                        draw = ImageDraw.Draw(tiled_img)
                        
                        # Try to use a small font, fallback to default if not available
                        try:
                            font_size = max(20, min_height // 25)  # Much larger: increased minimum to 20, better ratio
                            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)
                        except:
                            try:
                                font = ImageFont.load_default()
                            except:
                                font = None
                        
                        if font:
                            # Calculate text position (bottom-right corner of this tile)
                            text = f"📄 {doc_name}"
                            
                            # Get text dimensions
                            bbox = draw.textbbox((0, 0), text, font=font)
                            text_width = bbox[2] - bbox[0]
                            text_height = bbox[3] - bbox[1]
                            
                            # Position in bottom-right corner with small margin
                            margin = max(8, font_size // 3)  # Increased margin for better spacing
                            text_x = x + min_width - text_width - margin
                            text_y = y + min_height - text_height - margin
                            
                            # Draw solid background for better readability
                            bg_padding = max(4, font_size // 4)  # Larger padding for bigger font
                            bg_coords = [
                                text_x - bg_padding, 
                                text_y - bg_padding,
                                text_x + text_width + bg_padding,
                                text_y + text_height + bg_padding
                            ]
                            
                            # Create a semi-transparent overlay for the background
                            overlay = Image.new('RGBA', tiled_img.size, (0, 0, 0, 0))
                            overlay_draw = ImageDraw.Draw(overlay)
                            overlay_draw.rectangle(bg_coords, fill=(0, 0, 0, 180))  # Semi-transparent black
                            
                            # Composite the overlay onto the main image
                            tiled_img = Image.alpha_composite(tiled_img.convert('RGBA'), overlay).convert('RGB')
                            
                            # Redraw on the composited image
                            draw = ImageDraw.Draw(tiled_img)
                            
                            # Draw the text in white
                            draw.text((text_x, text_y), text, fill=(255, 255, 255), font=font)
                            
                except Exception as e:
                    # If watermarking fails, continue without it
                    pass
            
            # Convert tiled image to base64
            buffer = io.BytesIO()
            tiled_img.save(buffer, format='PNG')
            buffer.seek(0)
            img_data = base64.b64encode(buffer.read()).decode()
            
            # Determine output format based on input format
            if isinstance(input_obj, Attachment) and input_obj.images and input_obj.images[0].startswith('data:image/'):
                # Input was data URLs, output as data URL
                tiled_images.append(f"data:image/png;base64,{img_data}")
            else:
                # Input was raw base64, output as raw base64
                tiled_images.append(img_data)
        
        # Replace images list with tiled images
        result.images = tiled_images
        
        # Update metadata
        result.metadata.setdefault('processing', []).append({
            'operation': 'tile_images',
            'grid_size': f"{cols}x{rows}",
            'original_count': img_count,
            'tiles_created': num_tiles,
            'images_per_tile': images_per_tile,
            'tile_config': tile_config
        })
        
        return result
            
    except ImportError:
        raise ImportError("Pillow is required for image tiling. Install with: pip install Pillow")
    except Exception as e:
        raise ValueError(f"Could not tile images: {e}")

@refiner
def resize_images(att: Attachment) -> Attachment:
    """Resize images (in base64) based on DSL commands and return as base64.
    
    Supports:
    - Percentage scaling: [resize_images:50%]
    - Specific dimensions: [resize_images:800x600] 
    - Proportional width: [resize_images:800]
    """
    try:
        from PIL import Image
        import io
        import base64

        # Get resize specification from DSL commands
        resize_spec = att.commands.get('resize_images', '800')

        resized_images_b64 = []
        for img_b64 in getattr(att, "images", []):
            try:
                # Handle both data URLs and raw base64
                if img_b64.startswith('data:image/'):
                    # Extract base64 data from data URL
                    img_data_b64 = img_b64.split(',', 1)[1]
                else:
                    # Raw base64 data
                    img_data_b64 = img_b64
                
                img_data = base64.b64decode(img_data_b64)
                img = Image.open(io.BytesIO(img_data))
                img = img.convert("RGB")
                
                # Get original dimensions
                original_width, original_height = img.size
                
                # Parse resize specification (same logic as modify.resize)
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
                
                # Resize the image
                img_resized = img.resize((new_width, new_height))
                
                # Convert back to base64
                buffer = io.BytesIO()
                img_resized.save(buffer, format="PNG")
                buffer.seek(0)
                img_resized_b64 = base64.b64encode(buffer.read()).decode()
                
                # Return in the same format as input (data URL or raw base64)
                if img_b64.startswith('data:image/'):
                    resized_images_b64.append(f"data:image/png;base64,{img_resized_b64}")
                else:
                    resized_images_b64.append(img_resized_b64)
                    
            except (ValueError, ZeroDivisionError) as e:
                # If one image fails, skip it but log the error
                att.metadata.setdefault('processing_errors', []).append({
                    'operation': 'resize_images',
                    'error': f"Invalid resize specification '{resize_spec}': {str(e)}",
                    'image_index': len(resized_images_b64)
                })
                continue
            except Exception as e:
                # If one image fails for other reasons, skip it
                att.metadata.setdefault('processing_errors', []).append({
                    'operation': 'resize_images', 
                    'error': f"Failed to process image: {str(e)}",
                    'image_index': len(resized_images_b64)
                })
                continue

        att.images = resized_images_b64

        # Update metadata with detailed information
        att.metadata.setdefault('processing', []).append({
            'operation': 'resize_images',
            'resize_spec': resize_spec,
            'images_processed': len(resized_images_b64),
            'images_failed': len(getattr(att, 'images', [])) - len(resized_images_b64)
        })

        return att

    except ImportError:
        raise ImportError("Pillow is required for image resizing. Install with: pip install Pillow")
    except Exception as e:
        raise ValueError(f"Could not resize images: {e}")

@refiner
def add_repo_headers(att: Attachment) -> Attachment:
    """Add repository-aware headers to file content.
    
    For files from repositories, adds headers with:
    - Relative path from repo root
    - File type/language detection
    - File size information
    """
    if not att.text:
        return att
    
    # Check if this is from a repository
    if att.metadata.get('from_repo'):
        repo_path = att.metadata.get('repo_path', '')
        rel_path = att.metadata.get('relative_path', att.path)
        
        # Detect file type/language
        file_ext = os.path.splitext(rel_path)[1].lower()
        language = _detect_language(file_ext)
        
        # Get file size
        try:
            file_size = os.path.getsize(att.path)
            size_str = _format_file_size(file_size)
        except:
            size_str = "unknown"
        
        # Create header
        header = f"## File: `{rel_path}`\n\n"
        if language:
            header += f"**Language**: {language}  \n"
        header += f"**Size**: {size_str}  \n"
        header += f"**Path**: `{rel_path}`\n\n"
        
        # Add separator
        header += "```" + (language.lower() if language else "") + "\n"
        footer = "\n```\n\n"
        
        att.text = header + att.text + footer
    else:
        # Use regular add_headers for non-repo files
        return add_headers(att)
    
    return att

def _detect_language(file_ext: str) -> str:
    """Detect programming language from file extension."""
    language_map = {
        '.py': 'Python',
        '.js': 'JavaScript', 
        '.ts': 'TypeScript',
        '.jsx': 'JSX',
        '.tsx': 'TSX',
        '.java': 'Java',
        '.c': 'C',
        '.cpp': 'C++',
        '.cc': 'C++',
        '.cxx': 'C++',
        '.h': 'C Header',
        '.hpp': 'C++ Header',
        '.cs': 'C#',
        '.php': 'PHP',
        '.rb': 'Ruby',
        '.go': 'Go',
        '.rs': 'Rust',
        '.swift': 'Swift',
        '.kt': 'Kotlin',
        '.scala': 'Scala',
        '.sh': 'Shell',
        '.bash': 'Bash',
        '.zsh': 'Zsh',
        '.fish': 'Fish',
        '.ps1': 'PowerShell',
        '.html': 'HTML',
        '.htm': 'HTML',
        '.css': 'CSS',
        '.scss': 'SCSS',
        '.sass': 'Sass',
        '.less': 'Less',
        '.xml': 'XML',
        '.json': 'JSON',
        '.yaml': 'YAML',
        '.yml': 'YAML',
        '.toml': 'TOML',
        '.ini': 'INI',
        '.cfg': 'Config',
        '.conf': 'Config',
        '.md': 'Markdown',
        '.rst': 'reStructuredText',
        '.txt': 'Text',
        '.sql': 'SQL',
        '.r': 'R',
        '.R': 'R',
        '.m': 'MATLAB',
        '.pl': 'Perl',
        '.lua': 'Lua',
        '.vim': 'Vim Script',
        '.dockerfile': 'Dockerfile',
        '.makefile': 'Makefile',
        '.cmake': 'CMake',
        '.gradle': 'Gradle',
        '.maven': 'Maven',
        '.sbt': 'SBT'
    }
    
    return language_map.get(file_ext, '')

def _format_file_size(size_bytes: int) -> str:
    """Format file size in human readable format."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f}TB" 