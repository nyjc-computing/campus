"""campus.common.utils.url

This module provides utility functions for URL manipulation and validation.
"""

from typing import Any
from urllib.parse import urlparse, urlunparse, urlencode, parse_qs

from flask import url_for

from campus.common import env


def create_url(
        *,
        hostname: str = '',
        domain: str = '',
        protocol: str = "https",
        path: str = '/',
        params: dict[str, Any] | None = None
) -> str:
    """Create a URL from the given components."""
    query_string = urlencode(params or {})
    if hostname:
        parse_result = urlparse(hostname)
        protocol = parse_result.scheme or protocol
        path = parse_result.path or path
        domain = parse_result.netloc or domain
    return urlunparse((protocol, domain, path, '', query_string, ''))


def full_url_for(
        endpoint: str,
        hostname: str = env.HOSTNAME,
        **kwargs
) -> str:
    """Get the full URL for the current request.

    Args:
        endpoint: The endpoint name (Flask view function name).
        hostname: The hostname to use in the URL.
        **kwargs: Additional arguments to build the URL. Passed to
                  `url_for`.
    """
    # Validate that endpoint does not contain scheme or domain
    if urlparse(endpoint).scheme or urlparse(endpoint).netloc:
        raise ValueError("Endpoint should not contain scheme or domain.")
    full_url = create_url(
        protocol="https",
        domain=hostname,
        path=url_for(endpoint, **kwargs)
    )
    return full_url


def with_params(
        url: str,
        **params: Any
) -> str:
    """Add query parameters to the given URL."""
    # Verify that url does not have params and is an absolute URL
    parse_result = urlparse(url)
    if parse_result.scheme == '' or parse_result.netloc == '':
        raise ValueError("URL must be absolute with scheme and domain.")
    if parse_result.params != '':
        raise ValueError("URL must not contain params component.")
    new_query = urlencode(params, doseq=True)
    new_parse_result = parse_result._replace(query=new_query)
    return urlunparse(new_parse_result)
