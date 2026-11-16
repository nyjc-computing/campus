"""HTTP contract tests for campus.api subjcombi endpoints (#592).

These tests verify the HTTP interface contract for the subject-combination
mapping: status codes, response formats, and circle access control.

Subjcombi Endpoints Reference:
- PUT    /subjcombi/{user_id}           - Set mapping (subjcombi.admin)
- GET    /subjcombi/                    - Current mapping per user (bulk)
- GET    /subjcombi/{user_id}           - Current resolved mapping (?at= as-of)
- GET    /subjcombi/{user_id}/history   - Full mutation trail
- GET    /subjcombi/pending             - Scheduled, not-yet-effective records
- DELETE /subjcombi/pending/{record_id} - Cancel a pending record (subjcombi.admin)

Mutations require membership in the `subjcombi.admin` role circle
(user tokens only — client principals hold no domain authority,
campus#854); reads require authentication only.
"""

import unittest

from campus.common import schema
from tests.fixtures import services
from tests.fixtures.circles import grant_circle_admin
from tests.fixtures.tokens import create_test_token, get_bearer_auth_headers


class TestApiSubjcombiContract(unittest.TestCase):
    """HTTP contract tests for /api/v1/subjcombi/ endpoints."""

    USER_ID = schema.UserID("student@campus.test")
    LESSONGROUP_ID = "uid-lessonggroup-contract"

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
        # The timetable members table is a storage table: re-init in
        # case the clear dropped it (idempotent).
        from campus.api.resources.timetable import TimetablesResource
        TimetablesResource().init_storage()
        self.client = self.app.test_client()
        self.token = create_test_token(self.USER_ID)
        self.auth_headers = get_bearer_auth_headers(self.token)
        grant_circle_admin(self.USER_ID, "subjcombi", "timetable")
        self.timetable_id = self._create_timetable()
        # Activate the timetable so the roster fallback has a current
        # version to resolve against.
        activated = self.client.patch(
            "/api/v1/timetable/",
            json={"current": self.timetable_id},
            headers=self.auth_headers,
        )
        assert activated.status_code == 200, activated.get_json()

    def _create_timetable(self) -> str:
        """Create a timetable with one lessongroup; return its id."""
        response = self.client.post(
            "/api/v1/timetable/",
            json={
                "metadata": {
                    "filename": "subjcombi-contract.xml",
                    "start_date": "2026-01-01T00:00:00Z",
                    "end_date": "2026-12-31T00:00:00Z",
                },
                "data": {
                    "lessongroups": [{
                        "label": "25A1",
                        "members": [str(self.USER_ID)],
                        "entries": [
                            {"weekday": "MON", "timeslot": "0800",
                             "venue": "B1-01"}
                        ],
                    }],
                },
            },
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 200)
        return response.get_json()["data"]["id"]

    def _lessongroup_id(self) -> str:
        from campus.api.resources.timetable import timetable_lessongroup_collection
        records = timetable_lessongroup_collection.get_matching({
            "timetable_id": self.timetable_id,
        })
        assert records, "timetable was created without lessongroups"
        return records[0]["id"]

    # Auth and gate tests

    def test_set_without_auth_returns_401(self):
        response = self.client.put(
            f"/api/v1/subjcombi/{self.USER_ID}",
            json={"lessongroup_id": self.LESSONGROUP_ID},
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.get_json()["error"]["code"], "UNAUTHORIZED"
        )

    def test_set_without_circle_membership_returns_403(self):
        outsider = schema.UserID("outsider@campus.test")
        response = self.client.put(
            f"/api/v1/subjcombi/{self.USER_ID}",
            json={"lessongroup_id": self.LESSONGROUP_ID},
            headers=get_bearer_auth_headers(create_test_token(outsider)),
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["error"]["code"], "FORBIDDEN")

    # Set + current resolution

    def test_set_immediate_returns_record_and_resolves_current(self):
        response = self.client.put(
            f"/api/v1/subjcombi/{self.USER_ID}",
            json={"lessongroup_id": "25A1", "reason": "contract test"},
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 201)
        record = response.get_json()
        # The label is stored verbatim.
        self.assertEqual(record["lessongroup_id"], "25A1")
        self.assertEqual(record["actor_id"], str(self.USER_ID))
        self.assertIsNone(record["previous_lessongroup_id"])
        self.assertEqual(record["reason"], "contract test")

        current = self.client.get(
            f"/api/v1/subjcombi/{self.USER_ID}",
            headers=self.auth_headers,
        )
        self.assertEqual(current.status_code, 200)
        data = current.get_json()
        # The stored label translates to the current timetable's group id.
        self.assertEqual(data["lessongroup_id"], self._lessongroup_id())
        self.assertEqual(data["source"], "mapping")

    def test_orphan_label_is_stored_and_resolves_unmapped(self):
        """Mappings accept labels no timetable carries (they populate
        ahead of the upload); a mapping whose label no timetable group
        carries and whose user is in no roster resolves as unmapped
        rather than to a nonexistent group."""
        orphan = schema.UserID("orphan.student@campus.test")
        response = self.client.put(
            f"/api/v1/subjcombi/{orphan}",
            json={"lessongroup_id": "2607"},
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["lessongroup_id"], "2607")

        current = self.client.get(
            f"/api/v1/subjcombi/{orphan}",
            headers=self.auth_headers,
        )
        self.assertEqual(current.status_code, 200)
        data = current.get_json()
        self.assertIsNone(data["lessongroup_id"])
        self.assertEqual(data["source"], "unmapped")

    def test_list_all_returns_current_mapping_per_user(self):
        other = "other.student@campus.test"
        grant_circle_admin(other, "subjcombi")
        for user in (self.USER_ID, other):
            put = self.client.put(
                f"/api/v1/subjcombi/{user}",
                json={"lessongroup_id": "25A1"},
                headers=get_bearer_auth_headers(create_test_token(user)),
            )
            self.assertEqual(put.status_code, 201)
        # Fresh token for the read: minting for `other` invalidated the
        # setUp token (credentials are single-active per test user).
        listed = self.client.get(
            "/api/v1/subjcombi/",
            headers=get_bearer_auth_headers(create_test_token(self.USER_ID)),
        )
        self.assertEqual(listed.status_code, 200)
        records = listed.get_json()["data"]
        self.assertEqual(
            [r["user_id"] for r in records],
            sorted(str(u) for u in (self.USER_ID, other)),
        )
        self.assertTrue(all(r["lessongroup_id"] == "25A1" for r in records))

    def test_roster_fallback_when_unmapped(self):
        # The timetable was created with the user in the roster but no
        # maintained mapping exists yet.
        current = self.client.get(
            f"/api/v1/subjcombi/{self.USER_ID}",
            headers=self.auth_headers,
        )
        self.assertEqual(current.status_code, 200)
        data = current.get_json()
        self.assertEqual(data["source"], "roster")
        self.assertIsNotNone(data["lessongroup_id"])

    # Pending + cancel lifecycle

    def test_scheduled_record_is_pending_then_cancellable(self):
        created = self.client.put(
            f"/api/v1/subjcombi/{self.USER_ID}",
            json={"lessongroup_id": "25A1",
                  "effective_from": "2027-06-01"},
            headers=self.auth_headers,
        )
        self.assertEqual(created.status_code, 201)
        record = created.get_json()
        # Date-only effective_from applies at 07:00 SGT = 23:00 UTC.
        self.assertEqual(record["effective_from"], "2027-05-31T23:00:00+00:00")

        # Current state is untouched until the effective date.
        current = self.client.get(
            f"/api/v1/subjcombi/{self.USER_ID}",
            headers=self.auth_headers,
        )
        self.assertEqual(current.get_json()["source"], "roster")

        pending = self.client.get(
            "/api/v1/subjcombi/pending",
            headers=self.auth_headers,
        )
        self.assertEqual(pending.status_code, 200)
        self.assertEqual(len(pending.get_json()["data"]), 1)

        cancelled = self.client.delete(
            f"/api/v1/subjcombi/pending/{record['id']}",
            headers=self.auth_headers,
        )
        self.assertEqual(cancelled.status_code, 200)
        self.assertIsNotNone(cancelled.get_json()["cancelled_at"])

        pending = self.client.get(
            "/api/v1/subjcombi/pending",
            headers=self.auth_headers,
        )
        self.assertEqual(pending.get_json()["data"], [])

    def test_cancel_effective_record_returns_409(self):
        created = self.client.put(
            f"/api/v1/subjcombi/{self.USER_ID}",
            json={"lessongroup_id": "25A1"},
            headers=self.auth_headers,
        )
        record = created.get_json()
        response = self.client.delete(
            f"/api/v1/subjcombi/pending/{record['id']}",
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 409)

    def test_cancel_unknown_record_returns_404(self):
        response = self.client.delete(
            "/api/v1/subjcombi/pending/uid-subjcombi-nonexistent",
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 404)

    # History

    def test_history_lists_all_records_newest_first(self):
        other = "other.student@campus.test"
        grant_circle_admin(other, "subjcombi")
        # Mint a fresh token per request: token credentials are
        # single-active per test user, and minting for `other`
        # invalidates previously created headers.
        for user in (self.USER_ID, other):
            put = self.client.put(
                f"/api/v1/subjcombi/{user}",
                json={"lessongroup_id": "25A1"},
                headers=get_bearer_auth_headers(create_test_token(user)),
            )
            self.assertEqual(put.status_code, 201)
        put = self.client.put(
            f"/api/v1/subjcombi/{self.USER_ID}",
            json={"lessongroup_id": "25A1"},
            headers=get_bearer_auth_headers(create_test_token(self.USER_ID)),
        )
        self.assertEqual(put.status_code, 201)
        history = self.client.get(
            f"/api/v1/subjcombi/{self.USER_ID}/history",
            headers=get_bearer_auth_headers(create_test_token(self.USER_ID)),
        )
        self.assertEqual(history.status_code, 200)
        records = history.get_json()["data"]
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["user_id"], str(self.USER_ID))
        self.assertEqual(
            records[0]["previous_lessongroup_id"],
            records[1]["lessongroup_id"],
        )
