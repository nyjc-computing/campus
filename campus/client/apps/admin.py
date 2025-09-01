"""campus.client.apps.admin

Admin management client for Campus API /admin endpoints.
"""

from campus.client.interface import Resource
from campus.common.http import JsonClient


class AdminResource(Resource):
    """Resource for Campus /admin endpoint."""

    def __init__(self, client: JsonClient, *, raw: bool = False):
        super().__init__(client, "admin", raw=raw)

    def status(self) -> dict:
        """GET /admin/status - Get admin status info."""
        response = self.client.get(self.make_path("status"))
        return self._process_response(response)  # type: ignore[return-value]

    def init_db(self) -> dict:
        """POST /admin/init-db - Initialise the database."""
        response = self.client.post(self.make_path("init-db"), json={})
        return self._process_response(response)  # type: ignore[return-value]

    def purge_db(self) -> dict:
        """POST /admin/purge-db - Purge the database."""
        response = self.client.post(self.make_path("purge-db"), json={})
        return self._process_response(response)  # type: ignore[return-value]
