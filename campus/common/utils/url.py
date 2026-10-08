"""campus.common.utils.url

This module provides utility functions for URL manipulation and validation.

**Flask is not a dependency of this module** (nor of the rest of
campus.common): importing this module must succeed in any project,
flask-less ones included (#861). The one function that needs Flask,
`full_url_for`, imports it lazily at call time and raises a guided
ImportError when it is missing.

Rationale: `full_url_for` is request-context work — every caller already
runs inside a Flask app — while this module is imported at package scope
by campus.common, which must not pay for a web framework at import time.
Python loads an imported module exactly once, so the per-call
`import flask` costs only a sys.modules lookup after the first call;
there is nothing further to cache.

Caveats:
- Do NOT hoist the flask import to module level — not even as a tidy-up
  or because tooling suggests reordering. That silently reinstates the
  campus.common→flask edge (#861).
- A call-time dependency means a call-time failure: anything that calls
  `full_url_for` needs test coverage exercising the Flask-present path,
  while this module's tests cover the Flask-absent error path (see
  TestFullUrlForFlaskDependency in tests/unit/common/test_url.py).
"""

import typing
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


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

    The PUBLIC_URL environment variable (a full origin scheme://host[:port],
    e.g. "http://localhost:5000") is required.

    Returns:
        The canonical origin, without a trailing slash.

    Raises:
        OSError: If PUBLIC_URL is not set.
        ValueError: If PUBLIC_URL is set but is not a bare origin
                    (missing scheme/netloc, or contains a path, query,
                    params or fragment component).
    """
    from campus.common import env
    public_url = env.get("PUBLIC_URL")
    if not public_url:
        raise OSError(
            "PUBLIC_URL must be set to a full public origin "
            "(scheme://host[:port], e.g. https://your-domain.tld) for "
            "absolute URL generation. The legacy https://{HOSTNAME} "
            "fallback was removed (campus#652)."
        )
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


def full_url_for(
        endpoint: str,
        hostname: str | None = None,
        **kwargs
) -> str:
    """Get the full URL for the current request.

    The only function here that needs Flask: the import is deferred to
    call time (Python's import machinery loads Flask once; repeated
    calls pay only a sys.modules lookup).

    Args:
        endpoint: The endpoint name (Flask view function name).
        hostname: Optional explicit override. When omitted, the URL is
                  built from the canonical origin (see `canonical_origin`).
        **kwargs: Additional arguments to build the URL. Passed to
                  `url_for`.

    Raises:
        ImportError: If Flask is not installed. campus.common.utils
            deliberately does not depend on Flask; either add Flask to
            the project or use the flask-free helpers (create_url /
            canonical_origin / add_query).
    """
    # Validate that endpoint does not contain scheme or domain
    if urlparse(endpoint).scheme or urlparse(endpoint).netloc:
        raise ValueError("Endpoint should not contain scheme or domain.")
    # flask is imported HERE, at call time — not at module level. That is
    # a deliberate pattern, not an oversight: campus.common must import
    # without Flask (#861). If you are editing this function, keep the
    # import local; hoisting it to module level reinstates the
    # campus.common→flask edge and breaks flask-less consumers at import
    # time. Python loads the module once, so this costs only a
    # sys.modules lookup per call. See the module docstring for the full
    # rationale and the test-coverage caveat.
    try:
        import flask
    except ImportError as exc:
        raise ImportError(
            "full_url_for() requires Flask, which is not installed in "
            "this environment. campus.common.utils does not depend on "
            "Flask by design: either add Flask to the project, or use "
            "the flask-free helpers (create_url / canonical_origin / "
            "add_query)."
        ) from exc
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
