"""Data sampling modifier for DataFrames."""

import pandas as pd
from ..core.decorators import modifier


@modifier
def sample(df: pd.DataFrame, n: int = 100) -> pd.DataFrame:
    """Sample rows from DataFrame."""
    return df.sample(min(n, len(df))) 