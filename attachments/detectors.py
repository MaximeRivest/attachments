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