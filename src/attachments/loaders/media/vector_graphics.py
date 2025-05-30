"""Vector graphics loaders - SVG, EPS, and other vector formats."""

import xml.etree.ElementTree as ET
from ...core import Attachment, loader
from ... import matchers


@loader(match=matchers.svg_match)
def svg_to_svgdocument(att: Attachment) -> Attachment:
    """Load SVG files as SVGDocument objects for type dispatch."""
    
    class SVGDocument:
        """Minimal wrapper for SVG documents to enable type dispatch."""
        def __init__(self, root, content):
            self.root = root
            self.content = content
        
        def __str__(self):
            return self.content
        
        def __repr__(self):
            return self.content
    
    try:
        # Use the text_content property for consistent file/URL handling
        svg_content = att.text_content
        
        # Parse SVG as XML using ElementTree
        root = ET.fromstring(svg_content)
        
        # Create SVGDocument wrapper for type dispatch
        svg_doc = SVGDocument(root, svg_content)
        
        # Store the SVGDocument as the intermediate object
        att._obj = svg_doc
        
        # Extract metadata
        att.metadata.update({
            'format': 'svg',
            'content_type': 'image/svg+xml',
            'svg_width': root.get('width', 'auto'),
            'svg_height': root.get('height', 'auto'),
            'element_count': len(list(root.iter())),
            'has_text_elements': bool(list(root.iter('{http://www.w3.org/2000/svg}text'))),
            'has_images': bool(list(root.iter('{http://www.w3.org/2000/svg}image')))
        })
        
        return att
        
    except Exception as e:
        att.text = f"Error loading SVG: {e}"
        return att


@loader(match=matchers.eps_match)
def eps_to_epsdocument(att: Attachment) -> Attachment:
    """Load EPS files as EPSDocument objects for type dispatch."""
    
    class EPSDocument:
        """Minimal wrapper for EPS documents to enable type dispatch."""
        def __init__(self, content):
            self.content = content
        
        def __str__(self):
            return self.content
        
        def __repr__(self):
            return self.content
    
    try:
        # EPS files are text-based PostScript
        eps_content = att.text_content
        
        # Create EPSDocument wrapper for type dispatch
        eps_doc = EPSDocument(eps_content)
        
        # Store as EPSDocument object
        att._obj = eps_doc
        
        # Extract basic EPS metadata from comments
        metadata = {'format': 'eps', 'content_type': 'application/postscript'}
        lines = eps_content.split('\n')
        
        for line in lines[:20]:  # Check first 20 lines for metadata
            if line.startswith('%%BoundingBox:'):
                metadata['bounding_box'] = line.split(':', 1)[1].strip()
            elif line.startswith('%%Creator:'):
                metadata['creator'] = line.split(':', 1)[1].strip()
            elif line.startswith('%%Title:'):
                metadata['title'] = line.split(':', 1)[1].strip()
            elif line.startswith('%%CreationDate:'):
                metadata['creation_date'] = line.split(':', 1)[1].strip()
        
        metadata['file_size'] = len(eps_content)
        att.metadata.update(metadata)
        
        return att
        
    except Exception as e:
        att.text = f"Error loading EPS file: {e}"
        return att
