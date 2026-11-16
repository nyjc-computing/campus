"""HTTP contract tests for campus.api venues endpoints (campus#1099).

Venues are documents-backed CRUD: freeform `metadata` + freeform
markdown `notes`. These tests verify the HTTP interface contract:
status codes, response formats, PATCH semantics, and circle access
control.

Venue Endpoints Reference:
- POST   /api/v1/venues/   - Create a venue (venues.admin)
- GET    /api/v1/venues/   - List venues (auth only)
- GET    /api/v1/venues/{venue_id}/   - Get a venue (auth only)
- PATCH  /api/v1/venues/{venue_id}/   - Patch given fields (venues.admin)
- DELETE /api/v1/venues/{venue_id}/   - Delete a venue (venues.admin)

Mutations require membership in the `venues.admin` role circle (user
tokens only — client principals hold no domain authority, campus#854);
reads require authentication only.
"""

import unittest

from campus.common import schema
from tests.fixtures import services
from tests.fixtures.circles import grant_circle_admin
from tests.fixtures.tokens import create_test_token, get_bearer_auth_headers


class TestApiVenuesContract(unittest.TestCase):
    """HTTP contract tests for /api/v1/venues/ endpoints."""

    USER_ID = schema.UserID("student@campus.test")
    OTHER_USER_ID = schema.UserID("other@campus.test")

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager()
        cls.manager.initialize()
        cls.app = cls.manager.apps_app

    @classmethod
    def tearDownClass(cls):
        cls.manager.cleanup()

    def setUp(self):
        # clear_test_data wipes credentials storage and re-runs the
        # circle bootstrap, so per-test state is recreated here.
        self.manager.clear_test_data()
        self.client = self.app.test_client()
        self.token = create_test_token(self.USER_ID)
        self.auth_headers = get_bearer_auth_headers(self.token)

    def _admin_headers(self) -> dict:
        grant_circle_admin(self.USER_ID, "venues")
        return self.auth_headers

    def _create_venue(self, **body) -> dict:
        response = self.client.post(
            "/api/v1/venues/",
            json=body or {"metadata": {"name": "B1-01"}},
            headers=self._admin_headers(),
        )
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()

    # Auth and gate tests

    def test_create_without_auth_returns_401(self):
        response = self.client.post(
            "/api/v1/venues/", json={"metadata": {"name": "B1-01"}}
        )
        self.assertEqual(response.status_code, 401)

    def test_create_without_admin_circle_returns_403(self):
        # The venues.admin circle exists (bootstrap) but the caller is
        # not a member.
        other_token = create_test_token(self.OTHER_USER_ID)
        response = self.client.post(
            "/api/v1/venues/",
            json={"metadata": {"name": "B1-01"}},
            headers=get_bearer_auth_headers(other_token),
        )
        self.assertEqual(response.status_code, 403)

    def test_patch_without_admin_circle_returns_403(self):
        venue = self._create_venue()
        other_token = create_test_token(self.OTHER_USER_ID)
        response = self.client.patch(
            f"/api/v1/venues/{venue['id']}/",
            json={"notes": "hijack"},
            headers=get_bearer_auth_headers(other_token),
        )
        self.assertEqual(response.status_code, 403)

    def test_delete_without_admin_circle_returns_403(self):
        venue = self._create_venue()
        other_token = create_test_token(self.OTHER_USER_ID)
        response = self.client.delete(
            f"/api/v1/venues/{venue['id']}/",
            headers=get_bearer_auth_headers(other_token),
        )
        self.assertEqual(response.status_code, 403)

    # CRUD happy paths

    def test_create_returns_201_with_document_shape(self):
        response = self.client.post(
            "/api/v1/venues/",
            json={
                "metadata": {"name": "B1-01", "capacity": 40},
                "notes": "Projector **broken**.",
            },
            headers=self._admin_headers(),
        )
        self.assertEqual(response.status_code, 201)
        venue = response.get_json()
        self.assertTrue(venue["id"].startswith("uid-venue-"))
        self.assertEqual(venue["metadata"], {"name": "B1-01", "capacity": 40})
        self.assertEqual(venue["notes"], "Projector **broken**.")
        self.assertIn("created_at", venue)
        self.assertIsNone(venue["updated_at"])

    def test_list_returns_data_envelope(self):
        venue = self._create_venue()
        response = self.client.get(
            "/api/v1/venues/", headers=self.auth_headers
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()["data"]
        self.assertIn(venue["id"], {v["id"] for v in data})

    def test_get_by_id(self):
        venue = self._create_venue()
        response = self.client.get(
            f"/api/v1/venues/{venue['id']}/", headers=self.auth_headers
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["id"], venue["id"])

    def test_get_unknown_returns_404(self):
        response = self.client.get(
            "/api/v1/venues/uid-venue-doesnotexist/",
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 404)

    def test_patch_replaces_metadata_and_stamps_updated_at(self):
        venue = self._create_venue(metadata={"name": "B1-01", "capacity": 40})
        response = self.client.patch(
            f"/api/v1/venues/{venue['id']}/",
            json={"metadata": {"name": "B1-02"}},
            headers=self._admin_headers(),
        )
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        # whole-dict replacement, notes untouched
        self.assertEqual(body["metadata"], {"name": "B1-02"})
        self.assertIsNone(body["notes"])
        self.assertIsNotNone(body["updated_at"])

    def test_patch_null_notes_clears(self):
        venue = self._create_venue(
            metadata={"name": "B1-01"}, notes="To be cleared."
        )
        response = self.client.patch(
            f"/api/v1/venues/{venue['id']}/",
            json={"notes": None},
            headers=self._admin_headers(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.get_json()["notes"])
        # metadata untouched
        self.assertEqual(
            response.get_json()["metadata"], {"name": "B1-01"}
        )

    def test_patch_empty_body_returns_400(self):
        venue = self._create_venue()
        response = self.client.patch(
            f"/api/v1/venues/{venue['id']}/",
            json={},
            headers=self._admin_headers(),
        )
        self.assertEqual(response.status_code, 400)

    def test_patch_unknown_field_returns_400(self):
        venue = self._create_venue()
        response = self.client.patch(
            f"/api/v1/venues/{venue['id']}/",
            json={"venue_name": "nope"},
            headers=self._admin_headers(),
        )
        self.assertEqual(response.status_code, 400)

    def test_patch_unknown_venue_returns_404(self):
        response = self.client.patch(
            "/api/v1/venues/uid-venue-doesnotexist/",
            json={"notes": "x"},
            headers=self._admin_headers(),
        )
        self.assertEqual(response.status_code, 404)

    def test_delete_removes_venue(self):
        venue = self._create_venue()
        response = self.client.delete(
            f"/api/v1/venues/{venue['id']}/",
            headers=self._admin_headers(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {})
        gone = self.client.get(
            f"/api/v1/venues/{venue['id']}/", headers=self.auth_headers
        )
        self.assertEqual(gone.status_code, 404)

    def test_delete_unknown_returns_404(self):
        response = self.client.delete(
            "/api/v1/venues/uid-venue-doesnotexist/",
            headers=self._admin_headers(),
        )
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
