"""XML presenters for various content types."""



try:
    from pptx.presentation import Presentation
    from pptx.slide import Slide
    _pptx_available = True
except ImportError:
    _pptx_available = False
    Presentation = None  # type: ignore
    Slide = None  # type: ignore

try:
    from lxml import etree
    _lxml_available = True
except ImportError:
    _lxml_available = False
    etree = None  # type: ignore

from ..core.decorators import presenter


if _pptx_available and _lxml_available:
    @presenter
    def xml(presentation: Presentation) -> str:
        """
        Extract raw XML from PowerPoint presentation.
        
        Returns the XML content of the presentation.xml file, which contains
        the core structure of the presentation including slide references,
        masters, layouts, etc.
        
        Args:
            presentation: python-pptx Presentation object
            
        Returns:
            Raw XML string of the presentation structure
        """
        # The presentation object has an element property that gives us
        # access to the underlying lxml element
        if hasattr(presentation, 'element'):
            # Convert the element back to XML string
            return etree.tostring(
                presentation.element, 
                encoding='unicode', 
                pretty_print=True
            )
        
        # Fallback: try to access the part's blob directly
        if hasattr(presentation, 'part') and hasattr(presentation.part, 'blob'):
            blob = presentation.part.blob
            if isinstance(blob, bytes):
                return blob.decode('utf-8')
            return str(blob)
        
        raise ValueError("Cannot extract XML from PowerPoint presentation")


    @presenter  
    def xml(slide: Slide) -> str:
        """
        Extract raw XML from a PowerPoint slide.
        
        Returns the XML content of the slide, showing all shapes, 
        placeholders, text content, etc.
        
        Args:
            slide: python-pptx Slide object
            
        Returns:
            Raw XML string of the slide structure
        """
        if hasattr(slide, 'element'):
            return etree.tostring(
                slide.element,
                encoding='unicode', 
                pretty_print=True
            )
        
        raise ValueError("Cannot extract XML from PowerPoint slide")


@presenter
def xml(content: str) -> str:
    """Pass through string content as XML."""
    return content


@presenter
def xml(content: object) -> str:
    """Fallback: convert object to string representation."""
    return str(content) 