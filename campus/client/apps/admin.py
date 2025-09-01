"""campus.client.apps.admin

Admin management client for Campus API /admin endpoints.
"""

from typing import Any, Union

from campus.client.interface import Resource
from campus.common.http import JsonClient, JsonResponse


class AdminResource(Resource):
    """Resource for Campus /admin endpoint."""

    def __init__(self, client: JsonClient, *, raw: bool = False):
        super().__init__(client, "admin", raw=raw)

    def status(self) -> Union[JsonResponse, Any]:
        """GET /admin/status - Get admin status info."""
        response = self.client.get(self.make_path("status"))
        return self._process_response(response)

    def init_db(self) -> Union[JsonResponse, Any]:
        """POST /admin/init-db - Initialise the database."""
        response = self.client.post(self.make_path("init-db"), json={})
        return self._process_response(response)

    def purge_db(self) -> Union[JsonResponse, Any]:
        """POST /admin/purge-db - Purge the database."""
        response = self.client.post(self.make_path("purge-db"), json={})
        return self._process_response(response)
