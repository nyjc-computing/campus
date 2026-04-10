"""campus.audit.client.v1.root

Root resource for audit v1 API.
"""

from typing import Optional
from campus.common.http.interface import JsonClient


class AuditRoot:
    """Root resource for audit v1 API.

    Groups all v1 resources under a single entry point.
    """

    url_prefix: str = "audit/v1"

    def __init__(self, json_client: Optional[JsonClient] = None):
        """Initialize the audit root.

        Args:
            json_client: The HTTP client to use for requests.
        """
        self._client = json_client

    @property
    def base_url(self) -> str:
        """Get the base URL for this resource."""
        if not self._client:
            raise AttributeError("No client defined")
        return self._client.base_url

    @property
    def client(self) -> JsonClient:
        """Get the JsonClient associated with this resource."""
        if not self._client:
            raise AttributeError("No client defined")
        return self._client

    @property
    def traces(self):
        """Get the traces resource."""
        if not hasattr(self, "_traces"):
            from .traces import TracesResource
            self._traces = TracesResource(
                client=self._client,
                root=self
            )
        return self._traces
