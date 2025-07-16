"""common.utils.url

This module provides utility functions for URL manipulation and validation.
"""

from urllib.parse import urlparse, urlunparse, urlencode, parse_qs

def create_url(protocol: str, domain: str, path: str) -> str:
    """Create a URL from the given components."""
    return urlunparse((protocol, domain, path, '', '', ''))
