"""Content rendering logic."""

from abc import ABC, abstractmethod

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
    def render(self, parsed_items):
        """Renders a list of parsed items into an XML-like string.

        Args:
            parsed_items: A list of dictionaries, where each dictionary
                          represents a parsed file and contains at least
                          'type', 'id', and 'text'.
        Returns:
            A string in an XML-like format.
        """
        if not parsed_items:
            return ""

        output_parts = ["<attachments>"]
        for item in parsed_items:
            # Ensure basic keys are present
            item_type = item.get('type', 'unknown')
            item_id = item.get('id', 'item') # This ID needs to be generated in Attachments class
            text_content = item.get('text', '')
            # Sanitize text content for XML/HTML-like structures
            # A more robust sanitization might be needed for production
            text_content = text_content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

            output_parts.append(f"  <attachment id=\"{item_id}\" type=\"{item_type}\">")
            # Add other metadata if available, e.g., num_pages, num_slides
            if 'num_pages' in item:
                output_parts.append(f"    <meta name=\"num_pages\" value=\"{item['num_pages']}\" />")
            if 'num_slides' in item:
                output_parts.append(f"    <meta name=\"num_slides\" value=\"{item['num_slides']}\" />")
            
            output_parts.append(f"    <content>\n{text_content}\n    </content>")
            output_parts.append(f"  </attachment>")
        output_parts.append("</attachments>")
        return "\n".join(output_parts)


# Example usage (for testing the renderer directly):
# if __name__ == '__main__':
#     renderer = DefaultXMLRenderer()
#     sample_data = [
#         {'type': 'pdf', 'id': 'pdf1', 'text': 'Hello PDF world!', 'num_pages': 1},
#         {'type': 'pptx', 'id': 'pptx1', 'text': 'Hello PPTX world!', 'num_slides': 3}
#     ]
#     print(renderer.render(sample_data)) 