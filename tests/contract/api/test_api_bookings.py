"""HTTP contract tests for campus.api bookings endpoints (campus#1217).

The bookings surface implements the ratified venue-scoped authority:
creation is open to any user principal and pins status "pending";
deciding (status "approved"/"denied") and non-owner mutations are
gated on venue authority — venues.admin globally, or the standalone
venues.<category-slug>.admin circle for the venue's category.

Booking Endpoints Reference:
- POST   /api/v1/bookings/                 - Create (any user, pending)
- GET    /api/v1/bookings/                 - List + filters (auth only)
- GET    /api/v1/bookings/{booking_id}/    - Get (auth only)
- PATCH  /api/v1/bookings/{booking_id}/    - Edit/decide (owner or authority)
- DELETE /api/v1/bookings/{booking_id}/    - Withdraw/delete (owner-pending or authority)
"""

import unittest

from campus.common import schema
from tests.fixtures import services
from tests.fixtures.circles import (
    grant_category_booking_admin,
    grant_circle_admin,
    grant_staff_baseline,
)
from tests.fixtures.tokens import create_test_token, get_bearer_auth_headers

OWNER = schema.UserID("teacher@campus.test")
SPORTS_ADMIN = schema.UserID("sports-admin@campus.test")
GLOBAL_ADMIN = schema.UserID("venues-admin@campus.test")


class TestApiBookingsContract(unittest.TestCase):
    """HTTP contract tests for /api/v1/bookings/ endpoints."""

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager()
        cls.manager.initialize()
        cls.app = cls.manager.apps_app

    @classmethod
    def tearDownClass(cls):
        cls.manager.cleanup()

    def setUp(self):
        # clear_test_data wipes storage and re-runs the circle
        # bootstrap (which no longer seeds bookings circles), so
        # per-test state is recreated here.
        self.manager.clear_test_data()
        self.client = self.app.test_client()
        # The ratified model gates booking create/edit/withdraw on
        # self-scope venues authority: the fixture owner books as staff
        # (staff:viewer baseline + the staff → venues:self edge).
        grant_staff_baseline(str(OWNER))

    def _headers(self, user_id) -> dict:
        return get_bearer_auth_headers(create_test_token(user_id))

    def _grant_global(self) -> dict:
        grant_circle_admin(str(GLOBAL_ADMIN), "venues")
        return self._headers(GLOBAL_ADMIN)

    def _grant_sports(self) -> dict:
        grant_category_booking_admin(str(SPORTS_ADMIN), "Sports Facilities")
        return self._headers(SPORTS_ADMIN)

    def _create_venue(self, headers: dict, category: str | None = None, name: str = "B1-01") -> dict:
        metadata: dict = {"name": name}
        if category:
            metadata["category"] = category
        response = self.client.post(
            "/api/v1/venues/",
            json={"metadata": metadata},
            headers=headers,
        )
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()

    def _create_booking(self, venue_id: str, headers: dict, **overrides) -> dict:
        body = {
            "venue_id": venue_id,
            "description": "CCA training",
            "start_time": "1600",
            "end_time": "1800",
            "date": "2026-11-24",
        }
        body.update(overrides)
        response = self.client.post(
            "/api/v1/bookings/",
            json=body,
            headers=headers,
        )
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()

    # Creation

    def test_create_without_auth_returns_401(self):
        response = self.client.post("/api/v1/bookings/", json={})
        self.assertEqual(response.status_code, 401)

    def test_any_user_creates_pending_booking(self):
        """Staff book without venue authority: the request starts pending."""
        admin_headers = self._grant_global()
        venue = self._create_venue(admin_headers)
        created = self._create_booking(venue["id"], self._headers(OWNER))
        self.assertEqual(created["status"], "pending")
        self.assertEqual(created["user_id"], str(OWNER))

    def test_student_cannot_create_booking(self):
        """Students hold no venues edge: booking is staff-only (v1)."""
        from campus.api import resources
        from campus.api.resources.circle import (
            ACCESS_GUEST,
            circle_storage,
        )
        from campus.common import schema as sch

        student = sch.UserID("student@campus.test")
        if not circle_storage.get_matching({"name": str(student)}):
            resources.circle.new(name=str(student), tag="user")
        if not circle_storage.get_matching({"name": "student"}):
            resources.circle.new(name="student", tag="group")
        student_group = circle_storage.get_matching({"name": "student"})[0]
        resources.circle.members.add(
            schema.CampusID(student_group[schema.CAMPUS_KEY]),
            member_id=schema.CampusID(str(student)),
            access_value=ACCESS_GUEST,
        )
        admin_headers = self._grant_global()
        venue = self._create_venue(admin_headers)
        response = self.client.post(
            "/api/v1/bookings/",
            json={
                "venue_id": venue["id"],
                "description": "student booking",
                "start_time": "1600",
                "end_time": "1800",
                "date": "2026-11-24",
            },
            headers=self._headers(student),
        )
        self.assertEqual(response.status_code, 403)

    def test_create_unknown_venue_returns_404(self):
        response = self.client.post(
            "/api/v1/bookings/",
            json={
                "venue_id": "uid-venue-zzzzzzzz",
                "description": "x",
                "start_time": "1600",
                "end_time": "1800",
                "date": "2026-11-24",
            },
            headers=self._headers(OWNER),
        )
        self.assertEqual(response.status_code, 404)

    def test_create_malformed_time_returns_400(self):
        admin_headers = self._grant_global()
        venue = self._create_venue(admin_headers)
        response = self.client.post(
            "/api/v1/bookings/",
            json={
                "venue_id": venue["id"],
                "description": "x",
                "start_time": "16:00",
                "end_time": "1800",
                "date": "2026-11-24",
            },
            headers=self._headers(OWNER),
        )
        self.assertEqual(response.status_code, 400)

    def test_create_end_before_start_returns_400(self):
        admin_headers = self._grant_global()
        venue = self._create_venue(admin_headers)
        response = self.client.post(
            "/api/v1/bookings/",
            json={
                "venue_id": venue["id"],
                "description": "x",
                "start_time": "1800",
                "end_time": "1600",
                "date": "2026-11-24",
            },
            headers=self._headers(OWNER),
        )
        self.assertEqual(response.status_code, 400)

    def test_create_exact_duplicate_returns_409(self):
        admin_headers = self._grant_global()
        venue = self._create_venue(admin_headers)
        owner_headers = self._headers(OWNER)
        self._create_booking(venue["id"], owner_headers)
        response = self.client.post(
            "/api/v1/bookings/",
            json={
                "venue_id": venue["id"],
                "description": "different text, same slot",
                "start_time": "1600",
                "end_time": "1800",
                "date": "2026-11-24",
            },
            headers=owner_headers,
        )
        self.assertEqual(response.status_code, 409)

    # Deciding (status) authority

    def test_owner_cannot_set_status(self):
        admin_headers = self._grant_global()
        venue = self._create_venue(admin_headers, category="Sports Facilities")
        booking = self._create_booking(venue["id"], self._headers(OWNER))
        response = self.client.patch(
            f"/api/v1/bookings/{booking['id']}/",
            json={"status": "approved"},
            headers=self._headers(OWNER),
        )
        self.assertEqual(response.status_code, 403)

    def test_category_admin_decides_within_category(self):
        admin_headers = self._grant_global()
        sports = self._create_venue(admin_headers, category="Sports Facilities", name="Sports Hall")
        meeting = self._create_venue(admin_headers, category="Meeting Rooms", name="MR-1")
        sports_booking = self._create_booking(sports["id"], self._headers(OWNER))
        meeting_booking = self._create_booking(meeting["id"], self._headers(OWNER))
        sports_headers = self._grant_sports()

        approved = self.client.patch(
            f"/api/v1/bookings/{sports_booking['id']}/",
            json={"status": "approved"},
            headers=sports_headers,
        )
        self.assertEqual(approved.status_code, 200, approved.get_json())
        self.assertEqual(approved.get_json()["status"], "approved")

        denied_outside = self.client.patch(
            f"/api/v1/bookings/{meeting_booking['id']}/",
            json={"status": "approved"},
            headers=sports_headers,
        )
        self.assertEqual(denied_outside.status_code, 403)

    def test_global_admin_decides_anywhere(self):
        admin_headers = self._grant_global()
        meeting = self._create_venue(admin_headers, category="Meeting Rooms")
        booking = self._create_booking(meeting["id"], self._headers(OWNER))
        decided = self.client.patch(
            f"/api/v1/bookings/{booking['id']}/",
            json={"status": "denied"},
            headers=admin_headers,
        )
        self.assertEqual(decided.status_code, 200)
        self.assertEqual(decided.get_json()["status"], "denied")

    def test_uncategorized_venue_status_denied_for_scoped_admin(self):
        admin_headers = self._grant_global()
        plain = self._create_venue(admin_headers)
        booking = self._create_booking(plain["id"], self._headers(OWNER))
        response = self.client.patch(
            f"/api/v1/bookings/{booking['id']}/",
            json={"status": "approved"},
            headers=self._grant_sports(),  # scoped to a category the venue lacks
        )
        self.assertEqual(response.status_code, 403)

    def test_invalid_status_returns_400(self):
        admin_headers = self._grant_global()
        venue = self._create_venue(admin_headers)
        booking = self._create_booking(venue["id"], self._headers(OWNER))
        response = self.client.patch(
            f"/api/v1/bookings/{booking['id']}/",
            json={"status": "maybe"},
            headers=admin_headers,
        )
        self.assertEqual(response.status_code, 400)

    # Description edits (owner or authority)

    def test_owner_edits_own_description(self):
        admin_headers = self._grant_global()
        venue = self._create_venue(admin_headers)
        booking = self._create_booking(venue["id"], self._headers(OWNER))
        edited = self.client.patch(
            f"/api/v1/bookings/{booking['id']}/",
            json={"description": "NPCC training"},
            headers=self._headers(OWNER),
        )
        self.assertEqual(edited.status_code, 200)
        self.assertEqual(edited.get_json()["description"], "NPCC training")

    def test_non_owner_description_edit_denied_without_authority(self):
        admin_headers = self._grant_global()
        venue = self._create_venue(admin_headers)
        booking = self._create_booking(venue["id"], self._headers(OWNER))
        response = self.client.patch(
            f"/api/v1/bookings/{booking['id']}/",
            json={"description": "hijack"},
            headers=self._grant_sports(),  # scoped elsewhere + not owner
        )
        self.assertEqual(response.status_code, 403)

    # Deletion (owner-withdrawal or authority)

    def test_owner_withdraws_pending_booking(self):
        admin_headers = self._grant_global()
        venue = self._create_venue(admin_headers)
        booking = self._create_booking(venue["id"], self._headers(OWNER))
        response = self.client.delete(
            f"/api/v1/bookings/{booking['id']}/",
            headers=self._headers(OWNER),
        )
        self.assertEqual(response.status_code, 200)

    def test_owner_cannot_delete_decided_booking(self):
        admin_headers = self._grant_global()
        venue = self._create_venue(admin_headers, category="Sports Facilities")
        booking = self._create_booking(venue["id"], self._headers(OWNER))
        decide = self.client.patch(
            f"/api/v1/bookings/{booking['id']}/",
            json={"status": "approved"},
            headers=self._grant_sports(),
        )
        self.assertEqual(decide.status_code, 200)
        response = self.client.delete(
            f"/api/v1/bookings/{booking['id']}/",
            headers=self._headers(OWNER),
        )
        self.assertEqual(response.status_code, 403)

    def test_authority_deletes_any_booking(self):
        admin_headers = self._grant_global()
        venue = self._create_venue(admin_headers, category="Sports Facilities")
        booking = self._create_booking(venue["id"], self._headers(OWNER))
        response = self.client.delete(
            f"/api/v1/bookings/{booking['id']}/",
            headers=self._grant_sports(),
        )
        self.assertEqual(response.status_code, 200)

    # Reads (authentication only)

    def test_get_and_list_with_filters(self):
        admin_headers = self._grant_global()
        venue_a = self._create_venue(admin_headers, name="A")
        venue_b = self._create_venue(admin_headers, name="B")
        booking_a = self._create_booking(venue_a["id"], self._headers(OWNER))
        self._create_booking(venue_b["id"], self._headers(OWNER))

        listed = self.client.get(
            "/api/v1/bookings/",
            headers=self._headers(OWNER),
        )
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.get_json()["data"]), 2)

        filtered = self.client.get(
            f"/api/v1/bookings/?venue_id={venue_a['id']}",
            headers=self._headers(OWNER),
        )
        self.assertEqual([b["id"] for b in filtered.get_json()["data"]], [booking_a["id"]])

        fetched = self.client.get(
            f"/api/v1/bookings/{booking_a['id']}/",
            headers=self._headers(OWNER),
        )
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.get_json()["venue_id"], venue_a["id"])

    def test_get_unknown_booking_returns_404(self):
        response = self.client.get(
            "/api/v1/bookings/uid-booking-zzzzzzzz/",
            headers=self._headers(OWNER),
        )
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
