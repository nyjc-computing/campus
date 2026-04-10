"""campus.audit.client

Internal HTTP client for Campus audit service.

This client is used by campus.auth and campus.api to send trace spans
to the audit service via HTTP.

Example:
    from campus.audit.client import AuditClient

    client = AuditClient()
    client.traces.ingest(span_data)
"""

__all__ = ("AuditClient",)

from campus.common import env
from campus.common.http import DefaultClient
from .v1 import AuditRoot


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
        return f"https://{env.HOSTNAME}"

    match env.get("ENV", env.get("CAMPUS_ENV", "development")):
        case "development":
            return "https://campusaudit-development.up.railway.app"
        case "testing":
            return f"https://{env.HOSTNAME}"
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
    """

    def __init__(self, *, timeout: int = 30):
        """Initialize the audit client.

        Args:
            timeout: Request timeout in seconds (default: 30).
        """
        base_url = _get_base_url()
        http_client = DefaultClient(base_url=base_url)
        self._root = AuditRoot(json_client=http_client)

    @property
    def traces(self):
        """Get the traces resource for ingesting and querying spans."""
        return self._root.traces
