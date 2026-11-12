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

    def test_create_timetable_carries_label(self):
        """POST /timetable/ stores the committee's label (0.1.7).

        The label is the user-given display name; filename stays the
        immutable identity. Legacy records without the field read as
        null (from_storage falls back to the field default).
        """
        response = self.client.post(
            "/api/v1/timetable/",
            json={
                "metadata": {
                    "filename": "labelled-contract.xml",
                    "start_date": "2026-01-01T00:00:00Z",
                    "end_date": "2026-12-31T00:00:00Z",
                    "label": "2026 Term 1",
                },
                "data": {"lessongroups": []}
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()["data"]
        self.assertEqual(data["label"], "2026 Term 1")
        self.assertEqual(data["filename"], "labelled-contract.xml")

        listed = self.client.get(
            "/api/v1/timetable/metadata/", headers=self.auth_headers
        )
        row = next(
            t for t in listed.get_json()["data"]
            if t["id"] == data["id"]
        )
        self.assertEqual(row["label"], "2026 Term 1")


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


class TestTimetableMetadataPatchContract(unittest.TestCase):
    """PATCH /timetable/{id}/metadata is a subset update: any of
    label/start_date/end_date, only the fields present change; filename
    is refused as the immutable identity."""

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager()
        cls.manager.initialize()
        cls.app = cls.manager.apps_app
        cls.user_id = schema.UserID("meta.admin@campus.test")

    @classmethod
    def tearDownClass(cls):
        cls.manager.cleanup()

    def setUp(self):
        self.manager.clear_test_data()
        self.client = self.app.test_client()
        grant_circle_admin(str(self.user_id), "timetable")
        self.auth_headers = get_bearer_auth_headers(
            create_test_token(self.user_id)
        )
        response = self.client.post(
            "/api/v1/timetable/",
            json={
                "metadata": {
                    "filename": "meta-patch.xml",
                    "start_date": "2026-01-01T00:00:00Z",
                    "end_date": "2026-12-31T00:00:00Z",
                },
                "data": {"lessongroups": []}
            },
            headers=self.auth_headers
        )
        assert response.status_code == 200, response.get_json()
        self.timetable_id = response.get_json()["data"]["id"]

    def _patch(self, payload):
        return self.client.patch(
            f"/api/v1/timetable/{self.timetable_id}/metadata",
            json=payload,
            headers=self.auth_headers,
        )

    def _metadata(self):
        return self.client.get(
            f"/api/v1/timetable/{self.timetable_id}/metadata",
            headers=self.auth_headers,
        ).get_json()

    def test_label_only_patch_leaves_dates_alone(self):
        response = self._patch({"label": "2026 Term 1"})
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["label"], "2026 Term 1")
        self.assertEqual(body["start_date"], "2026-01-01T00:00:00Z")
        self.assertEqual(body["end_date"], "2026-12-31T00:00:00Z")
        self.assertEqual(self._metadata()["label"], "2026 Term 1")

    def test_dates_patch_leaves_label_alone(self):
        self._patch({"label": "Term 1"})
        response = self._patch({
            "start_date": "2026-02-01T00:00:00Z",
            "end_date": "2026-11-30T00:00:00Z",
        })
        self.assertEqual(response.status_code, 200)
        body = self._metadata()
        self.assertEqual(body["label"], "Term 1")
        self.assertEqual(body["start_date"], "2026-02-01T00:00:00Z")

    def test_null_clears_the_label(self):
        self._patch({"label": "Term 1"})
        response = self._patch({"label": None})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self._metadata()["label"])

    def test_patch_requires_auth_and_circle(self):
        response = self.client.patch(
            f"/api/v1/timetable/{self.timetable_id}/metadata",
            json={"label": "sneaky"},
        )
        self.assertEqual(response.status_code, 401)
        outsider = schema.UserID("meta.outsider@campus.test")
        response = self.client.patch(
            f"/api/v1/timetable/{self.timetable_id}/metadata",
            json={"label": "sneaky"},
            headers=get_bearer_auth_headers(create_test_token(outsider)),
        )
        self.assertEqual(response.status_code, 403)

    def test_patch_rejects_bad_bodies(self):
        empty = self._patch({})
        self.assertEqual(empty.status_code, 400)
        unknown = self._patch({"timezone": "SGT"})
        self.assertEqual(unknown.status_code, 400)
        filename = self._patch({"filename": "renamed.xml"})
        self.assertEqual(filename.status_code, 400)
        self.assertIn(
            "cannot be changed", filename.get_json()["error"]["message"]
        )
        blank = self._patch({"label": "   "})
        self.assertEqual(blank.status_code, 400)


class TestTimetableMeContract(unittest.TestCase):
    """HTTP contract tests for GET /timetable/me (#592, #1076).

    The signed-in user's resolved view: active version + effective
    subject combination (mapping overrides roster), plus the state at
    the earliest pending change with its planning case.
    """

    USER_ID = schema.UserID("me.student@campus.test")

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager()
        cls.manager.initialize()
        cls.app = cls.manager.apps_app

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

        self.manager.clear_test_data()
        timetable_effective_collection.delete_matching({})
        with contextlib.suppress(campus.storage.errors.NotFoundError):
            timetable_collection.delete_by_id("@metadata")
        self.client = self.app.test_client()
        grant_circle_admin(str(self.USER_ID), "timetable", "subjcombi")

    def _headers(self):
        # Fresh token per request: minting a token invalidates the
        # previous credential record.
        return get_bearer_auth_headers(create_test_token(self.USER_ID))

    def _lg_id(self, timetable_id: str, label: str = "25A1") -> str:
        from campus.api.resources.timetable import timetable_lessongroup_collection
        rows = timetable_lessongroup_collection.get_matching({
            "timetable_id": timetable_id,
            "label": label,
        })
        assert rows, f"expected a {label!r} lessongroup in {timetable_id}"
        return rows[0]["id"]

    def _create_timetable(
            self,
            filename: str,
            member: str | None,
            labels: tuple[str, ...] = ("25A1",),
    ) -> str:
        lessongroups = [{
            "label": label,
            "members": [member] if (member and label == "25A1") else [],
            "entries": [{"weekday": "MON", "timeslot": "0800",
                         "venue": "B1-01"}],
        } for label in labels]
        response = self.client.post(
            "/api/v1/timetable/",
            json={
                "metadata": {
                    "filename": filename,
                    "start_date": "2026-01-01T00:00:00Z",
                    "end_date": "2026-12-31T00:00:00Z",
                },
                "data": {"lessongroups": lessongroups},
            },
            headers=self._headers(),
        )
        assert response.status_code == 200, response.get_json()
        return response.get_json()["data"]["id"]

    def test_me_requires_auth(self):
        response = self.client.get("/api/v1/timetable/me")
        self.assertEqual(response.status_code, 401)

    def test_roster_current_and_no_next(self):
        tt_v1 = self._create_timetable("me-v1.xml", str(self.USER_ID))
        self.client.patch(
            "/api/v1/timetable/",
            json={"current": tt_v1},
            headers=self._headers(),
        )
        view = self.client.get(
            "/api/v1/timetable/me", headers=self._headers()
        )
        self.assertEqual(view.status_code, 200)
        data = view.get_json()
        self.assertEqual(data["current"]["timetable_id"], tt_v1)
        self.assertEqual(data["current"]["source"], "roster")
        self.assertEqual(data["current"]["lessongroup_id"], self._lg_id(tt_v1))
        self.assertIsNone(data["next"])

    def test_scheduled_subjcombi_is_next(self):
        tt_v1 = self._create_timetable("me-s1.xml", str(self.USER_ID))
        self.client.patch(
            "/api/v1/timetable/",
            json={"current": tt_v1},
            headers=self._headers(),
        )
        put = self.client.put(
            f"/api/v1/subjcombi/{self.USER_ID}",
            json={"lessongroup_id": self._lg_id(tt_v1),
                  "effective_from": "2027-06-01"},
            headers=self._headers(),
        )
        self.assertEqual(put.status_code, 201)
        view = self.client.get(
            "/api/v1/timetable/me", headers=self._headers()
        )
        data = view.get_json()
        self.assertEqual(data["current"]["source"], "roster")
        self.assertEqual(data["next"]["lessongroup_id"], self._lg_id(tt_v1))
        self.assertEqual(data["next"]["source"], "mapping")
        self.assertEqual(
            data["next"]["effective_from"], "2027-05-31T23:00:00+00:00"
        )
        self.assertEqual(data["next"]["change_type"], "subjcombi")

    def test_scheduled_version_switch_is_next(self):
        tt_v1 = self._create_timetable("me-vv1.xml", str(self.USER_ID))
        tt_v2 = self._create_timetable("me-vv2.xml", str(self.USER_ID))
        self.client.patch(
            "/api/v1/timetable/",
            json={"current": tt_v1},
            headers=self._headers(),
        )
        self.client.patch(
            "/api/v1/timetable/",
            json={"next": tt_v2, "effective_from": "2027-07-01"},
            headers=self._headers(),
        )
        view = self.client.get(
            "/api/v1/timetable/me", headers=self._headers()
        )
        data = view.get_json()
        self.assertEqual(data["current"]["timetable_id"], tt_v1)
        self.assertEqual(data["next"]["timetable_id"], tt_v2)
        self.assertEqual(data["next"]["change_type"], "timetable")

    def test_simultaneous_switch_and_subjcombi_is_both(self):
        """Both planning changes land at one instant → change_type both.

        With label-anchored reuse (#592) a version switch alone keeps
        the group id stable, so the "both" case needs the mapping to
        actually move: the student's new combination is a group whose
        label is new to the v2 allocation.
        """
        tt_v1 = self._create_timetable("me-b1.xml", str(self.USER_ID))
        tt_v2 = self._create_timetable(
            "me-b2.xml", str(self.USER_ID), labels=("25A1", "25B2")
        )
        self.client.patch(
            "/api/v1/timetable/",
            json={"current": tt_v1},
            headers=self._headers(),
        )
        # Both changes take effect at the same instant (date-only ->
        # 07:00 SGT on the same day).
        self.client.patch(
            "/api/v1/timetable/",
            json={"next": tt_v2, "effective_from": "2027-07-01"},
            headers=self._headers(),
        )
        self.client.put(
            f"/api/v1/subjcombi/{self.USER_ID}",
            json={"lessongroup_id": self._lg_id(tt_v2, "25B2"),
                  "effective_from": "2027-07-01"},
            headers=self._headers(),
        )
        view = self.client.get(
            "/api/v1/timetable/me", headers=self._headers()
        )
        data = view.get_json()
        self.assertEqual(data["next"]["change_type"], "both")
        self.assertEqual(data["next"]["timetable_id"], tt_v2)

    def test_as_of_resolves_future_state(self):
        tt_v1 = self._create_timetable("me-a1.xml", str(self.USER_ID))
        tt_v2 = self._create_timetable("me-a2.xml", str(self.USER_ID))
        self.client.patch(
            "/api/v1/timetable/",
            json={"current": tt_v1},
            headers=self._headers(),
        )
        self.client.patch(
            "/api/v1/timetable/",
            json={"next": tt_v2, "effective_from": "2027-07-01"},
            headers=self._headers(),
        )
        view = self.client.get(
            "/api/v1/timetable/me",
            query_string={"at": "2027-08-01T00:00:00Z"},
            headers=self._headers(),
        )
        data = view.get_json()
        self.assertEqual(data["current"]["timetable_id"], tt_v2)


class TestTimetableLessongroupReuseContract(unittest.TestCase):
    """POST /timetable/ reuses lessongroup ids by label across
    allocations (#592) and refuses duplicate-label drift with 409.

    The identity ruling: a group's label anchors its identity within a
    cohort year, so subjcombi mappings keyed by lessongroup_id survive
    version switches; entries persist their own label (campus-model#5)
    so an old allocation keeps rendering after its group row moves to
    the new one.
    """

    USER_ID = schema.UserID("test.user@campus.test")

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager()
        cls.manager.initialize()
        cls.app = cls.manager.apps_app

    @classmethod
    def tearDownClass(cls):
        cls.manager.cleanup()

    def setUp(self):
        self.manager.clear_test_data()
        self.client = self.app.test_client()
        self.token = create_test_token(self.USER_ID)
        self.auth_headers = get_bearer_auth_headers(self.token)
        grant_circle_admin(str(self.USER_ID), "timetable")

    def _create_timetable(self, filename: str, labels: list[str]) -> dict:
        """POST a timetable with one group per label; return its resource."""
        response = self.client.post(
            "/api/v1/timetable/",
            json={
                "metadata": {
                    "filename": filename,
                    "start_date": "2026-01-01T00:00:00Z",
                    "end_date": "2026-12-31T00:00:00Z"
                },
                "data": {
                    "lessongroups": [
                        {
                            "label": label,
                            "members": [f"2510-{label}"],
                            "entries": [
                                {"weekday": "Mon A", "timeslot": "0800",
                                 "venue": "5-64"}
                            ],
                        }
                        for label in labels
                    ],
                },
            },
            headers=self.auth_headers
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()["data"]

    def _entries(self, timetable_id: str) -> list[dict]:
        response = self.client.get(
            f"/api/v1/timetable/{timetable_id}/entries",
            headers=self.auth_headers
        )
        self.assertEqual(response.status_code, 200)
        return response.get_json()["entries"]

    def test_reuse_keeps_lessongroup_ids_across_versions(self):
        """v2 with the same labels keeps v1's ids; v1 still renders."""
        v1 = self._create_timetable(
            "reuse-v1.xml", ["25A-Math", "25A-Phy"]
        )
        v2 = self._create_timetable("reuse-v2.xml", ["25A-Math"])

        v1_by_label = {e["label"]: e for e in self._entries(v1["id"])}
        v2_by_label = {e["label"]: e for e in self._entries(v2["id"])}
        self.assertEqual(
            v2_by_label["25A-Math"]["lessongroup_id"],
            v1_by_label["25A-Math"]["lessongroup_id"]
        )
        # v1's labels survive the switch: entries carry their own.
        self.assertEqual(
            {e["label"] for e in self._entries(v1["id"])},
            {"25A-Math", "25A-Phy"}
        )

    def test_duplicate_label_drift_returns_409(self):
        """A label claimed by two rows conflicts the create."""
        from campus.api.resources.timetable import timetable_lessongroup_collection

        v1 = self._create_timetable("drift-v1.xml", ["25A-Math"])
        self._entries(v1["id"])
        # Simulate legacy drift: a second row claiming the same label.
        timetable_lessongroup_collection.insert_one({
            "id": "uid-lesson-group-drift",
            "timetable_id": "uid-timetable-drift",
            "label": "25A-Math",
        })
        response = self.client.post(
            "/api/v1/timetable/",
            json={
                "metadata": {
                    "filename": "drift-v2.xml",
                    "start_date": "2026-01-01T00:00:00Z",
                    "end_date": "2026-12-31T00:00:00Z"
                },
                "data": {
                    "lessongroups": [{
                        "label": "25A-Math",
                        "members": [],
                        "entries": [],
                    }],
                },
            },
            headers=self.auth_headers
        )
        self.assertEqual(response.status_code, 409)
        error = response.get_json()["error"]
        self.assertEqual(error["code"], "CONFLICT")

    def test_duplicate_label_in_payload_returns_400(self):
        """The same label twice in one payload is a 400."""
        response = self.client.post(
            "/api/v1/timetable/",
            json={
                "metadata": {
                    "filename": "dupe.xml",
                    "start_date": "2026-01-01T00:00:00Z",
                    "end_date": "2026-12-31T00:00:00Z"
                },
                "data": {
                    "lessongroups": [
                        {"label": "25A-Math", "members": [], "entries": []},
                        {"label": "25A-Math", "members": [], "entries": []},
                    ],
                },
            },
            headers=self.auth_headers
        )
        self.assertEqual(response.status_code, 400)


if __name__ == '__main__':
    unittest.main()
