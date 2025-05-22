"""Markdown presenters for various content types."""

import pandas as pd
import numpy as np

from PIL import Image as PILImage
from ..core.decorators import presenter
# PowerPointContent removed - now using markitdown directly in presenter

try:
    from pptx.presentation import Presentation
    from markitdown import MarkItDown
    _markitdown_available = True
except ImportError:
    _markitdown_available = False
    Presentation = None  # type: ignore


if _markitdown_available:
    @presenter
    def markdown(presentation: Presentation) -> str:
        """Extract markdown from PowerPoint presentation using markitdown."""
        md = MarkItDown()
        
        # For presentations, we need to save to temp file and use markitdown
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(suffix='.pptx', delete=False) as tmp:
            try:
                presentation.save(tmp.name)
                result = md.convert(tmp.name)
                return result.text_content
            finally:
                if os.path.exists(tmp.name):
                    os.unlink(tmp.name)


@presenter
def markdown(df: pd.DataFrame) -> str:
    """Convert DataFrame to markdown table."""
    return df.to_markdown()


@presenter
def markdown(content: str) -> str:
    """Pass through markdown content."""
    return content


@presenter  
def markdown(arr: np.ndarray) -> str:
    return f"```\n{arr}\n```"


@presenter
def markdown(img: PILImage.Image) -> str:
    return f"![Image]({img.width}x{img.height})" 