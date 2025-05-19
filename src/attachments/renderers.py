"""Content rendering logic."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any
import xml.etree.ElementTree as ET
import re

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
    def _sanitize_xml_attr(self, value):
        """Ensure value is a string and escape/replace invalid XML attribute characters."""
        if value is None:
            return ""
        value = str(value)
        # Remove control characters except tab, newline, carriage return
        value = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', value)
        # Replace invalid XML attribute chars (", <, >, &, ')
        value = value.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        value = value.replace('"', '&quot;').replace("'", '&apos;')
        return value

    def _sanitize_xml_text(self, value):
        """Ensure value is a string and escape/replace invalid XML text characters."""
        if value is None:
            return ""
        value = str(value)
        # Remove control characters except tab, newline, carriage return
        value = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', value)
        # ElementTree will escape &, <, > automatically in text, but we can pre-escape for safety
        value = value.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        return value

    def render(self, attachments_data: List[Dict[str, Any]]) -> str:
        root = ET.Element("attachments")
        for item_data in attachments_data:
            item_id = self._sanitize_xml_attr(item_data.get("id", "unknown"))
            item_type = self._sanitize_xml_attr(item_data.get("type", "unknown"))
            original_path = self._sanitize_xml_attr(item_data.get("original_path_str", item_data.get("file_path", "N/A")))

            attachment_element = ET.SubElement(root, "attachment")
            attachment_element.set("id", item_id)
            attachment_element.set("type", item_type)
            attachment_element.set("original_path", original_path)

            content_text = item_data.get("text", "")
            content_element = ET.SubElement(attachment_element, "content")
            if content_text:
                content_element.text = self._sanitize_xml_text(content_text)
            else:
                pass

        xml_str = ET.tostring(root, encoding="utf-8").decode("utf-8")
        try:
            import xml.dom.minidom
            dom = xml.dom.minidom.parseString(xml_str)
            return dom.toprettyxml(indent="  ")
        except Exception as e:
            print("[attachments] XML rendering error. Invalid XML string was:\n", xml_str)
            print("Exception:", e)
            raise

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