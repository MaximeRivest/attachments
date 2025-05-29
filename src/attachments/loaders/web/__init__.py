"""Web loaders - URLs and web content."""

from .urls import url_to_bs4, url_to_file, url_to_response

__all__ = [
    'url_to_bs4',
    'url_to_file',
    'url_to_response'
] 