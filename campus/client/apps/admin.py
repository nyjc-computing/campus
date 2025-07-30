"""campus.client.apps.admin

Admin management client for Campus API /admin endpoints.
"""

from typing import Dict, Any
from campus.client.base import HttpClient
from campus.client import config

class AdminClient:
    """Client for Campus /admin endpoints."""
    def __init__(self, base_url: str | None = None):
        self._client = HttpClient(base_url or config.get_apps_base_url())

    def status(self) -> Dict[str, Any]:
        """GET /admin/status - Get admin status info."""
        return self._client.get("/admin/status")

    def init_db(self) -> Dict[str, Any]:
        """POST /admin/init-db - Initialise the database."""
        return self._client.post("/admin/init-db", data={})

    def purge_db(self) -> Dict[str, Any]:
        """POST /admin/purge-db - Purge the database."""
        return self._client.post("/admin/purge-db", data={})
