"""Sample data files for attachments library."""

import os
from pathlib import Path

def get_sample_path(filename: str) -> str:
    """Get the path to a sample data file.
    
    Args:
        filename: Name of the sample file
        
    Returns:
        Absolute path to the sample file
        
    Example:
        >>> from attachments.data import get_sample_path
        >>> csv_path = get_sample_path("test.csv")
        >>> attach(csv_path) | load.csv_to_pandas | present.markdown
    """
    data_dir = Path(__file__).parent
    return str(data_dir / filename)

def list_samples() -> list[str]:
    """List all available sample data files.
    
    Returns:
        List of sample file names
    """
    data_dir = Path(__file__).parent
    return [f.name for f in data_dir.glob("*") if f.is_file() and f.name != "__init__.py"]

# Convenience exports
__all__ = ["get_sample_path", "list_samples"] 