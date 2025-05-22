"""CSV file loader using pandas."""

import pandas as pd
from ..core.decorators import loader


def is_csv(path: str) -> bool:
    return path.lower().endswith('.csv')


@loader(is_csv) 
def csv(path: str):
    return pd.read_csv(path) 