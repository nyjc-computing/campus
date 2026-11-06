"""HTTP contract tests for campus.api timetable endpoints.

These tests verify the HTTP interface contract for timetable management
operations: status codes, response formats, and validation behavior.

NOTE: /timetable/ endpoints require authentication (Basic or Bearer).
This is enforced via before_request hook in the API blueprint.

Timetable Endpoints Reference:
- POST   /timetable/                  - Create a new timetable
- GET    /timetable/                  - Pointer state (current/next/effective_from)
- PATCH  /timetable/                  - Patch one pointer (flip current, schedule/cancel next)
- GET    /timetable/metadata/         - List timetable metadata records
- GET    /timetable/{id}/             - Get a full timetable
- GET    /timetable/current           - Get the current timetable ID
- GET    /timetable/next              - Get the next timetable ID + effective date
"""

import unittest

from campus.common import schema
from tests.fixtures import services
from tests.fixtures.circles import grant_circle_admin
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

        # Mutation routes are gated behind timetable.admin; grant the
        # test user the role (clear_test_data wipes the circles).
        grant_circle_admin(str(self.user_id), "timetable")

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


class TestTimetablePointersContract(unittest.TestCase):
    """HTTP contract tests for the effective-dated pointer routes (#1075).

    GET /timetable/ (pointer state), PATCH /timetable/ (one-key patch),
    GET /timetable/next ({value, effective_from}), and the relocated
    metadata list at GET /timetable/metadata/.
    """

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager()
        cls.manager.initialize()
        cls.app = cls.manager.apps_app
        cls.user_id = schema.UserID("pointer.admin@campus.test")

    @classmethod
    def tearDownClass(cls):
        cls.manager.cleanup()

    def setUp(self):
        import contextlib

        import campus.storage
        from campus.api.resources.timetable import (
            timetable_collection,
            timetable_effective_collection,
        )

        # The pointer trail is deployment-global: reset it per test.
        self.manager.clear_test_data()
        timetable_effective_collection.delete_matching({})
        with contextlib.suppress(campus.storage.errors.NotFoundError):
            timetable_collection.delete_by_id("@metadata")
        self.client = self.app.test_client()
        self.auth_headers = get_bearer_auth_headers(
            create_test_token(self.user_id)
        )
        grant_circle_admin(str(self.user_id), "timetable")
        self.timetable_id = self._create_timetable()

    def _create_timetable(self) -> str:
        response = self.client.post(
            "/api/v1/timetable/",
            json={
                "metadata": {
                    "filename": "pointers-contract.xml",
                    "start_date": "2026-01-01T00:00:00Z",
                    "end_date": "2026-12-31T00:00:00Z"
                },
                "data": {"lessongroups": []}
            },
            headers=self.auth_headers
        )
        assert response.status_code == 200
        return response.get_json()["data"]["id"]

    def _patch(self, payload, headers=None):
        return self.client.patch(
            "/api/v1/timetable/",
            json=payload,
            headers=headers or self.auth_headers,
        )

    def test_patch_current_flips_and_state_resolves(self):
        response = self._patch({"current": self.timetable_id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["current"], self.timetable_id)
        current = self.client.get("/api/v1/timetable/current")
        # Reads are authentication-only; the pointer reads here use the
        # same authenticated client.
        current = self.client.get(
            "/api/v1/timetable/current", headers=self.auth_headers
        )
        self.assertEqual(current.get_json()["value"], self.timetable_id)

    def test_patch_next_dated_applies_0700_school_time(self):
        response = self._patch({
            "next": self.timetable_id,
            "effective_from": "2027-06-01",
        })
        self.assertEqual(response.status_code, 200)
        state = response.get_json()
        self.assertEqual(state["next"], self.timetable_id)
        # Date-only effective_from: 07:00 SGT = 23:00 UTC the day before.
        self.assertEqual(state["effective_from"], "2027-05-31T23:00:00+00:00")
        nxt = self.client.get(
            "/api/v1/timetable/next", headers=self.auth_headers
        )
        self.assertEqual(nxt.status_code, 200)
        self.assertEqual(nxt.get_json()["value"], self.timetable_id)
        self.assertEqual(
            nxt.get_json()["effective_from"], "2027-05-31T23:00:00+00:00"
        )

    def test_patch_next_null_cancels_pending(self):
        self._patch({"next": self.timetable_id, "effective_from": "2027-06-01"})
        cancelled = self._patch({"next": None})
        self.assertEqual(cancelled.status_code, 200)
        self.assertIsNone(cancelled.get_json()["next"])
        self.assertIsNone(cancelled.get_json()["effective_from"])

    def test_patch_validation_errors(self):
        both = self._patch({
            "current": self.timetable_id, "next": self.timetable_id
        })
        self.assertEqual(both.status_code, 400)
        unknown = self._patch({"mode": "flip"})
        self.assertEqual(unknown.status_code, 400)
        date_only_cancel = self._patch({
            "next": None, "effective_from": "2027-06-01"
        })
        self.assertEqual(date_only_cancel.status_code, 400)
        empty = self._patch({"effective_from": "2027-06-01"})
        self.assertEqual(empty.status_code, 400)
        unset = self._patch({"current": None})
        self.assertEqual(unset.status_code, 400)

    def test_patch_requires_auth_and_circle(self):
        response = self.client.patch(
            "/api/v1/timetable/", json={"current": self.timetable_id}
        )
        self.assertEqual(response.status_code, 401)
        outsider = schema.UserID("pointer.outsider@campus.test")
        response = self.client.patch(
            "/api/v1/timetable/",
            json={"current": self.timetable_id},
            headers=get_bearer_auth_headers(create_test_token(outsider)),
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["error"]["code"], "FORBIDDEN")

    def test_metadata_list_route(self):
        response = self.client.get(
            "/api/v1/timetable/metadata/", headers=self.auth_headers
        )
        self.assertEqual(response.status_code, 200)
        ids = [
            t["id"] for t in response.get_json()["data"]
        ]
        self.assertIn(self.timetable_id, ids)


if __name__ == '__main__':
    unittest.main()
