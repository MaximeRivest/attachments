"""Markdown presenters for various content types."""

import pandas as pd
import numpy as np
from PIL import Image as PILImage
from ..core.decorators import presenter


@presenter
def markdown(df: pd.DataFrame) -> str:
    return df.to_markdown()


@presenter  
def markdown(arr: np.ndarray) -> str:
    return f"```\n{arr}\n```"


@presenter
def markdown(img: PILImage.Image) -> str:
    return f"![Image]({img.width}x{img.height})" 