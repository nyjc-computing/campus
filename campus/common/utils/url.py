"""campus.common.utils.url

This module provides utility functions for URL manipulation and validation.
"""

import typing
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import flask


def create_url(
        *,
        hostname: str = '',
        domain: str = '',
        protocol: str = "https",
        path: str = '/',
        params: dict[str, typing.Any] | None = None
) -> str:
    """Create a URL from the given components."""
    query_string = urlencode(params or {})
    if hostname:
        parse_result = urlparse(hostname)
        protocol = parse_result.scheme or protocol
        path = parse_result.path or path
        domain = parse_result.netloc or domain
    return urlunparse((protocol, domain, path, '', query_string, ''))


def canonical_origin() -> str:
    """Resolve the canonical public origin for absolute URL generation.

    Precedence:
        1. PUBLIC_URL environment variable: a full origin
           (scheme://host[:port]), e.g. "http://localhost:5000".
        2. https://{HOSTNAME}: legacy fallback for deployments that only
           set HOSTNAME.

    Returns:
        The canonical origin, without a trailing slash.

    Raises:
        ValueError: If PUBLIC_URL is set but is not a bare origin
                    (missing scheme/netloc, or contains a path, query,
                    params or fragment component).
    """
    from campus.common import env
    public_url = env.get("PUBLIC_URL")
    if public_url:
        parse_result = urlparse(public_url)
        if not parse_result.scheme or not parse_result.netloc:
            raise ValueError(
                "PUBLIC_URL must be a full origin (scheme://host[:port]), "
                f"got {public_url!r}"
            )
        if any((
                parse_result.path.strip('/'),
                parse_result.params,
                parse_result.query,
                parse_result.fragment,
        )):
            raise ValueError(
                "PUBLIC_URL must not contain a path, query, params or "
                f"fragment component: {public_url!r}"
            )
        return f"{parse_result.scheme}://{parse_result.netloc}"
    # DEPRECATED (campus#652): the https://{HOSTNAME} fallback assumes
    # HTTPS and no non-default port, which is wrong for local development
    # over plain HTTP. Kept for backward compatibility with deployments
    # that only set HOSTNAME; set PUBLIC_URL instead.
    return f"https://{env.HOSTNAME}"


def full_url_for(
        endpoint: str,
        hostname: str | None = None,
        **kwargs
) -> str:
    """Get the full URL for the current request.

    Args:
        endpoint: The endpoint name (Flask view function name).
        hostname: Optional explicit override. When omitted, the URL is
                  built from the canonical origin (see `canonical_origin`).
        **kwargs: Additional arguments to build the URL. Passed to
                  `url_for`.
    """
    # Validate that endpoint does not contain scheme or domain
    if urlparse(endpoint).scheme or urlparse(endpoint).netloc:
        raise ValueError("Endpoint should not contain scheme or domain.")
    if not hostname:
        parse_result = urlparse(canonical_origin())
        protocol = parse_result.scheme
        hostname = parse_result.netloc
    else:
        protocol = "https"
    full_url = create_url(
        protocol=protocol,
        domain=hostname,
        path=flask.url_for(endpoint, **kwargs)
    )
    return full_url


def add_query(
        url: str,
        **additional_queries: str
) -> str:
    """Add query parameters to the given URL."""
    # Verify that url does not have params and is an absolute URL
    parse_result = urlparse(url)
    # if parse_result.scheme == '' or parse_result.netloc == '':
    #     raise ValueError("URL must be absolute with scheme and domain.")
    if parse_result.params != '':
        raise ValueError("URL must not contain params component.")
    # https://docs.python.org/3/library/urllib.parse.html#urllib.parse.parse_qs
    # query is a dict[str, list[str]]
    query = parse_qs(parse_result.query, strict_parsing=True)
    for k, v in additional_queries.items():
        query[k] = [v]
    new_qs = urlencode(query, doseq=True)
    new_parse_result = parse_result._replace(query=new_qs)
    return urlunparse(new_parse_result)
