"""campus.audit.client

Internal HTTP client for Campus audit service.

This client is used by campus.auth and campus.api to send trace spans
to the audit service via HTTP.

Example:
    from campus.audit.client import AuditClient

    client = AuditClient()
    client.traces.ingest(span_data)
"""

from typing import Callable

__all__ = ("AuditClient", "set_http_client_factory")

from campus.common import env
from campus.common.http.interface import JsonClient
from .v1 import AuditRoot


# Global factory for creating HTTP clients (deprecated, use json_client_class instead)
_http_client_factory: Callable[[str], JsonClient] | None = None


def set_http_client_factory(factory: Callable[[str], JsonClient] | None) -> None:
    """Set a global factory for creating HTTP clients.

    .. deprecated::
        Use AuditClient.json_client_class instead. This function is kept
        for backwards compatibility only.

    Used in tests to inject TestJsonClient instead of DefaultClient.
    Call with None to reset to default behavior.

    Args:
        factory: Function that takes base_url and returns a JsonClient,
                 or None to reset to default.
    """
    global _http_client_factory
    _http_client_factory = factory


def _create_http_client(base_url: str) -> JsonClient:
    """Create HTTP client using factory, class attribute, or default.

    Priority:
    1. Global factory (if set, for backwards compatibility)
    2. AuditClient.json_client_class (if set)
    3. DefaultClient (fallback)

    Args:
        base_url: The base URL for the client

    Returns:
        A JsonClient instance
    """
    # Priority 1: Global factory (deprecated, for backwards compatibility)
    if _http_client_factory is not None:
        return _http_client_factory(base_url)

    # Priority 2: Class attribute (recommended approach)
    # Use getattr to avoid static type checker errors (attribute is set at runtime)
    client_class = getattr(AuditClient, "json_client_class", None)
    if client_class is not None:
        return client_class(base_url=base_url)

    # Priority 3: Default client
    from campus.common.http import DefaultClient
    return DefaultClient(base_url=base_url)  # type: ignore[return-value]


def _get_base_url() -> str:
    """Get the audit service base URL from environment.

    Returns the appropriate URL based on ENV setting:
    - development: Railway development URL
    - testing: localhost/current hostname
    - staging: production staging URL
    - production: production URL
    """
    # If running in the audit deployment itself, use relative URL
    if env.get("DEPLOY") == "campus.audit":
        return f"https://{env.get('HOSTNAME', 'localhost')}"

    match env.get("ENV", env.get("CAMPUS_ENV", "development")):
        case "development":
            return "https://campusaudit-development.up.railway.app"
        case "testing":
            return f"https://{env.get('HOSTNAME', 'localhost')}"
        case "staging":
            return "https://audit.campus.nyjc.dev"
        case "production":
            return "https://audit.campus.nyjc.app"
        case _:
            raise ValueError(f"Invalid ENV value for audit client")


class AuditClient:
    """Internal HTTP client for Campus audit service.

    This client provides access to audit service endpoints for internal
    service-to-server communication (e.g., campus.auth → campus.audit).

    The client uses campus.common.http.DefaultClient which handles:
    - Basic auth via CLIENT_ID/CLIENT_SECRET environment variables
    - Persistent connections via requests.Session
    - Automatic error handling and logging

    For dependency injection in tests, you can:
    1. Set json_client_class class attribute (recommended):
       AuditClient.json_client_class = TestJsonClient
    2. Pass http_client parameter directly (for custom instances):
       AuditClient(http_client=my_custom_client)
    3. Use set_http_client_factory() (deprecated, for backwards compatibility)
    """

    # Configurable JsonClient class for dependency injection
    # Set this to inject a custom JsonClient implementation (e.g., for testing)
    # When None, DefaultClient is used via _create_http_client()
    json_client_class: type[JsonClient] | None = None

    def __init__(
        self,
        *,
        http_client: JsonClient | None = None,
        base_url: str | None = None,
        timeout: int = 30
    ):
        """Initialize the audit client.

        Args:
            http_client: Optional custom JSON client for dependency injection.
                         If None, a client will be created using the factory
                         or DefaultClient.
            base_url: Optional base URL for the audit service. If None, will be
                      determined from environment. Only used when http_client
                      is None.
            timeout: Request timeout in seconds (default: 30). Only used when
                     http_client is None.
        """
        if http_client is None:
            base_url = base_url or _get_base_url()
            http_client = _create_http_client(base_url)
        self._root = AuditRoot(json_client=http_client)

    @property
    def traces(self):
        """Get the traces resource for ingesting and querying spans."""
        return self._root.traces
