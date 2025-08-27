"""campus.client.apps.admin

Admin management client for Campus API /admin endpoints.
"""

from campus.client.wrapper import JsonResponse, Resource


class AdminResource(Resource):
    """Resource for Campus /admin endpoint."""

    def status(self) -> JsonResponse:
        """GET /admin/status - Get admin status info."""
        return self.client.get(self.make_path("status"))

    def init_db(self) -> JsonResponse:
        """POST /admin/init-db - Initialise the database."""
        return self.client.post(self.make_path("init-db"), json={})

    def purge_db(self) -> JsonResponse:
        """POST /admin/purge-db - Purge the database."""
        return self.client.post(self.make_path("purge-db"), json={})
