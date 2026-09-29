"""HTTP contract tests for campus.api timetable endpoints.

These tests verify the HTTP interface contract for timetable management
operations: status codes, response formats, and validation behavior.

NOTE: /timetable/ endpoints require authentication (Basic or Bearer).
This is enforced via before_request hook in the API blueprint.

Timetable Endpoints Reference:
- POST   /timetable/                  - Create a new timetable
- GET    /timetable/                  - List timetables
- GET    /timetable/{id}/             - Get a full timetable
- GET    /timetable/current           - Get the current timetable ID
- PUT    /timetable/current           - Set the current timetable
- GET    /timetable/next              - Get the next timetable ID
- PUT    /timetable/next              - Set the next timetable
"""

import unittest

from campus.common import schema
from tests.fixtures import services
from tests.fixtures.tokens import create_test_token, get_bearer_auth_headers


class TestApiTimetablesContract(unittest.TestCase):
    """HTTP contract tests for /api/v1/timetable/ endpoints."""

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager()
        cls.manager.initialize()
        cls.app = cls.manager.apps_app
        cls.user_id = schema.UserID("test.user@campus.test")

    @classmethod
    def tearDownClass(cls):
        cls.manager.cleanup()

    def setUp(self):
        self.manager.clear_test_data()
        self.client = self.app.test_client()
        self.token = create_test_token(self.user_id)
        self.auth_headers = get_bearer_auth_headers(self.token)

    def test_create_timetable_requires_auth(self):
        """POST /timetable/ without auth returns 401."""
        response = self.client.post(
            "/api/v1/timetable/",
            json={
                "metadata": {
                    "filename": "2026.xml",
                    "start_date": "2026-01-01T00:00:00Z",
                    "end_date": "2026-12-31T00:00:00Z"
                },
                "data": {"lessongroups": []}
            }
        )

        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "UNAUTHORIZED")

    def test_create_timetable_success(self):
        """POST /timetable/ with valid metadata creates a timetable."""
        response = self.client.post(
            "/api/v1/timetable/",
            json={
                "metadata": {
                    "filename": "2026-contract.xml",
                    "start_date": "2026-01-01T00:00:00Z",
                    "end_date": "2026-12-31T00:00:00Z"
                },
                "data": {"lessongroups": []}
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()["data"]
        self.assertIn("id", data)
        self.assertEqual(data["filename"], "2026-contract.xml")
        self.assertEqual(data["entries"], [])

    def test_create_timetable_empty_filename_returns_422(self):
        """POST /timetable/ with an empty filename returns 422, not 200.

        Regression test for #600: timetable.new() used to accept and
        store a timetable with an empty filename.
        """
        response = self.client.post(
            "/api/v1/timetable/",
            json={
                "metadata": {
                    "filename": "",
                    "start_date": "2026-01-01T00:00:00Z",
                    "end_date": "2026-12-31T00:00:00Z"
                },
                "data": {"lessongroups": []}
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 422)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "VALIDATION_FAILED")
        fields = {e["field"] for e in data["error"]["errors"]}
        self.assertIn("filename", fields)


if __name__ == '__main__':
    unittest.main()
