"""Unit tests for venue-scoped booking authority (campus#1217).

require_venue_authority must allow venues.admin globally, allow the
standalone venues.<category-slug>.admin circle for its category only,
and deny fail-closed on uncategorized venues, missing scoped circles,
client principals, and non-members. has_venue_authority answers the
same decision without raising.
"""

import contextlib
import unittest

import flask

from campus.common import env
from campus.common.errors import api_errors

# Configure test storage before importing storage-backed modules
env.set("STORAGE_MODE", "1")

ADMIN = "venues-admin@campus.test"
SPORTS_ADMIN = "sports-admin@campus.test"
OUTSIDER = "outsider@campus.test"


class TestVenueBookingAuthority(unittest.TestCase):
    """The venue-scoped gate and its global/scoped/fail-closed matrix."""

    def setUp(self):
        from campus.api.resources import booking as booking_resource
        from campus.api.resources import venue as venue_resource
        from campus.api.resources.circle import (
            CirclesResource,
            circle_storage,
        )
        from tests.fixtures.circles import (
            grant_category_booking_admin,
            grant_circle_admin,
        )

        circle_storage.delete_matching({})
        CirclesResource.init_storage()
        # The storage tables don't share the document cleanup; clear
        # the venues collection and drop any bookings rows.
        venue_resource.venue_collection.delete_matching({})
        with contextlib.suppress(Exception):
            booking_resource.venue_booking_table.delete_matching({})

        self.venue_resource = venue_resource
        self.booking_resource = booking_resource
        grant_circle_admin(ADMIN, "venues")
        grant_category_booking_admin(SPORTS_ADMIN, "Sports Facilities")
        self.sports_venue = venue_resource.new(
            metadata={"name": "Sports Hall", "category": "Sports Facilities"},
        )
        self.meeting_venue = venue_resource.new(
            metadata={"name": "MR-1", "category": "Meeting Rooms"},
        )
        self.plain_venue = venue_resource.new(metadata={"name": "Store"})

    def tearDown(self):
        from campus.api.resources import booking as booking_resource
        from campus.api.resources import venue as venue_resource
        from campus.api.resources.circle import circle_storage

        circle_storage.delete_matching({})
        venue_resource.venue_collection.delete_matching({})
        with contextlib.suppress(Exception):
            booking_resource.venue_booking_table.delete_matching({})

    def _gate(self, user, venue_id, **kwargs):
        from campus.api.authz import require_venue_authority

        app = flask.Flask(__name__)
        with app.test_request_context():
            flask.g.current_user = user
            require_venue_authority(venue_id, **kwargs)

    def _has(self, user, venue_id) -> bool:
        from campus.api.authz import has_venue_authority

        app = flask.Flask(__name__)
        with app.test_request_context():
            flask.g.current_user = user
            return has_venue_authority(venue_id)

    def _venue_id(self, venue) -> str:
        from campus.common import schema

        return str(schema.CampusID(venue.id))

    def test_global_venues_admin_passes_everywhere(self):
        """venues.admin decides bookings on any venue, categorized or not."""
        admin = {"id": ADMIN}
        self._gate(admin, self._venue_id(self.sports_venue))
        self._gate(admin, self._venue_id(self.meeting_venue))
        self._gate(admin, self._venue_id(self.plain_venue))

    def test_category_admin_passes_within_category(self):
        """The scoped circle's member decides bookings for its category."""
        self._gate({"id": SPORTS_ADMIN}, self._venue_id(self.sports_venue))

    def test_category_admin_denied_outside_category(self):
        """The scoped member has no authority over another category."""
        with self.assertRaises(api_errors.ForbiddenError) as ctx:
            self._gate(
                {"id": SPORTS_ADMIN},
                self._venue_id(self.meeting_venue),
                action_label="decide bookings",
            )
        self.assertIn("venues.meeting-rooms.admin", str(ctx.exception))

    def test_uncategorized_venue_is_global_admin_only(self):
        """No category in metadata: scoped members are denied."""
        with self.assertRaises(api_errors.ForbiddenError) as ctx:
            self._gate(
                {"id": SPORTS_ADMIN},
                self._venue_id(self.plain_venue),
            )
        self.assertIn('no "category"', str(ctx.exception))
        self._gate({"id": ADMIN}, self._venue_id(self.plain_venue))

    def test_missing_scoped_circle_denies_fail_closed(self):
        """A category with no scoped circle denies (nobody but global)."""
        from campus.api.authz import category_slug

        assert not _circle_exists(f"venues.{category_slug('Meeting Rooms')}.admin")
        with self.assertRaises(api_errors.ForbiddenError) as ctx:
            self._gate(
                {"id": SPORTS_ADMIN},
                self._venue_id(self.meeting_venue),
            )
        self.assertIn("fail-closed", str(ctx.exception))

    def test_outsider_denied_everywhere(self):
        """A non-member decides nothing, anywhere."""
        outsider = {"id": OUTSIDER}
        for venue in (self.sports_venue, self.meeting_venue):
            with self.assertRaises(api_errors.ForbiddenError):
                self._gate(outsider, self._venue_id(venue))

    def test_client_principal_denied(self):
        """A client principal (no user) is denied even by the global admin id."""
        with self.assertRaises(api_errors.ForbiddenError) as ctx:
            self._gate(None, self._venue_id(self.sports_venue))
        self.assertIn("Client principals", str(ctx.exception))

    def test_unknown_venue_404_comes_from_the_lookup_not_the_gate(self):
        """Unknown venues 404 only where the venue must be loaded.

        The gate answers global venues.admin membership without
        loading the venue (routes 404 phantoms themselves when they
        resolve the booking/venue), so a global admin passes; a
        scoped decision path does load the venue and surfaces
        NotFound.
        """
        from campus.common import schema

        missing = schema.CampusID("uid-venue-zzzzzzzz")
        self._gate({"id": ADMIN}, missing)  # global: venue never loaded
        with self.assertRaises(api_errors.NotFoundError):
            self._gate({"id": SPORTS_ADMIN}, missing)
        with self.assertRaises(api_errors.NotFoundError):
            self._gate({"id": OUTSIDER}, missing)
        self.assertTrue(self._has({"id": ADMIN}, missing))
        self.assertFalse(self._has({"id": SPORTS_ADMIN}, missing))

    def test_has_venue_authority_matches_require(self):
        """The non-raising check agrees with the gate on every row."""
        sports_id = self._venue_id(self.sports_venue)
        meeting_id = self._venue_id(self.meeting_venue)
        self.assertTrue(self._has({"id": ADMIN}, sports_id))
        self.assertTrue(self._has({"id": SPORTS_ADMIN}, sports_id))
        self.assertFalse(self._has({"id": SPORTS_ADMIN}, meeting_id))
        self.assertFalse(self._has({"id": OUTSIDER}, sports_id))
        self.assertFalse(self._has(None, sports_id))


def _circle_exists(name: str) -> bool:
    from campus.api.resources.circle import circle_storage

    return bool(circle_storage.get_matching({"name": name}))


if __name__ == "__main__":
    unittest.main()
