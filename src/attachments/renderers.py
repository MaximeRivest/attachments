"""Content rendering logic."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any
import xml.etree.ElementTree as ET

class BaseRenderer(ABC):
    """Abstract base class for content renderers."""
    @abstractmethod
    def render(self, parsed_content):
        """Renders parsed content into an LLM-friendly format."""
        pass

class RendererRegistry:
    """Manages registration and retrieval of renderers."""
    def __init__(self):
        self.renderers = {}
        self.default_renderer = None

    def register(self, name, renderer_instance, default=False):
        """Registers a renderer instance."""
        if not isinstance(renderer_instance, BaseRenderer):
            raise TypeError("Renderer instance must be a subclass of BaseRenderer.")
        self.renderers[name] = renderer_instance
        if default or not self.default_renderer:
            self.default_renderer = renderer_instance

    def get_renderer(self, name=None):
        """Retrieves a registered renderer by name, or the default renderer."""
        if name:
            renderer = self.renderers.get(name)
            if not renderer:
                raise ValueError(f"No renderer registered with name '{name}'.")
            return renderer
        if not self.default_renderer:
            raise ValueError("No default renderer set and no renderer name provided.")
        return self.default_renderer

    def set_default_renderer(self, name_or_instance):
        """Sets the default renderer by name or instance."""
        if isinstance(name_or_instance, str):
            renderer = self.renderers.get(name_or_instance)
            if not renderer:
                raise ValueError(f"No renderer registered with name '{name_or_instance}'.")
            self.default_renderer = renderer
        elif isinstance(name_or_instance, BaseRenderer):
            # Optionally, register if not already known by a name
            self.default_renderer = name_or_instance
        else:
            raise TypeError("Provide a registered renderer name or a BaseRenderer instance.")

class DefaultXMLRenderer(BaseRenderer):
    """Renders parsed content into a default XML-like string format."""
    def render(self, attachments_data: List[Dict[str, Any]]) -> str:
        root = ET.Element("attachments")
        for item_data in attachments_data:
            item_id = item_data.get("id", "unknown")
            item_type = item_data.get("type", "unknown")
            original_path = item_data.get("original_path_str", item_data.get("file_path", "N/A"))

            attachment_element = ET.SubElement(root, "attachment")
            attachment_element.set("id", item_id)
            attachment_element.set("type", item_type)
            attachment_element.set("original_path", original_path)

            content_text = item_data.get("text", "")
            
            content_element = ET.SubElement(attachment_element, "content")
            # Using a direct assignment for CDATA. 
            # ET doesn't have a specific CDATA type, but this is a common way to handle it.
            # Actual CDATA wrapping might need to happen during serialization if the library doesn't do it.
            if content_text: # Only add text if it's not empty
                content_element.text = content_text # Store as regular text; XML serializer should handle escaping.
                                                # For literal CDATA, one might need a custom serializer or to build the string manually.
            else:
                # If there's no text content, we can leave the content tag empty
                # or add a comment, or omit it. For now, an empty tag is fine.
                pass

        # Serialize to string with pretty print
        # ET.indent(root) # Available in Python 3.9+
        xml_str = ET.tostring(root, encoding="utf-8").decode("utf-8")
        
        # Basic pretty printing for older Python versions or if ET.indent is not sufficient
        try:
            import xml.dom.minidom
            dom = xml.dom.minidom.parseString(xml_str)
            return dom.toprettyxml(indent="  ")
        except ImportError:
            # Fallback if minidom is not available (though it's standard)
            return xml_str

class PlainTextRenderer(BaseRenderer):
    """Renders parsed content into a simple plain text string, 
    concatenating the 'text' field of each attachment.
    Ideal for simple LLM text prompts where images are handled separately.
    """
    def render(self, parsed_items):
        """Renders a list of parsed items into a single plain text string.

        Args:
            parsed_items: A list of dictionaries, where each dictionary
                          represents a parsed file and contains at least 'text'.
        Returns:
            A string concatenating the text content of each item, separated by double newlines.
        """
        if not parsed_items:
            return ""

        text_parts = []
        for item in parsed_items:
            text_content = item.get('text', '')
            # No XML sanitization needed for plain text output
            text_parts.append(text_content)
        
        # Join with double newlines to separate content from different attachments
        return "\n\n".join(text_parts).strip()

# Example usage (for testing the renderer directly):
# if __name__ == '__main__':
#     renderer = DefaultXMLRenderer()
#     sample_data = [
#         {'type': 'pdf', 'id': 'pdf1', 'text': 'Hello PDF world!', 'num_pages': 1},
#         {'type': 'pptx', 'id': 'pptx1', 'text': 'Hello PPTX world!', 'num_slides': 3}
#     ]
#     print(renderer.render(sample_data)) 