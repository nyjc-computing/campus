"""Unit tests for venue-scoped booking authority (campus#1217/#1218).

require_venue_authority is a group-scope modify on the `venues`
family, category-narrowed: a venues:admin holder decides any venue's
bookings, a venues.<category-slug> subcircle member decides only
within the category, and everyone else (baseline viewer included)
denies. has_venue_authority answers the same decision without
raising.
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
        """venues:admin decides bookings on any venue, categorized or not."""
        admin = {"id": ADMIN}
        self._gate(admin, self._venue_id(self.sports_venue))
        self._gate(admin, self._venue_id(self.meeting_venue))
        self._gate(admin, self._venue_id(self.plain_venue))

    def test_category_edge_passes_within_category(self):
        """The category subcircle's member decides bookings for its
        category — narrowest path wins."""
        self._gate({"id": SPORTS_ADMIN}, self._venue_id(self.sports_venue))

    def test_category_edge_denied_outside_category(self):
        """The category edge is authoritative only within its category:
        for another category it is excluded, and the member has no
        family-level edges, so the modify bit is missing."""
        with self.assertRaises(api_errors.ForbiddenError) as ctx:
            self._gate(
                {"id": SPORTS_ADMIN},
                self._venue_id(self.meeting_venue),
                action_label="decide bookings",
            )
        self.assertIn("group-scope modify", str(ctx.exception))

    def test_uncategorized_venue_resolves_at_family_level(self):
        """No category in metadata: no narrowing applies. The scoped
        member (whose only edge is category-tagged) has no family-level
        authority and denies; the venues:admin holder passes."""
        with self.assertRaises(api_errors.ForbiddenError):
            self._gate(
                {"id": SPORTS_ADMIN},
                self._venue_id(self.plain_venue),
            )
        self._gate({"id": ADMIN}, self._venue_id(self.plain_venue))

    def test_outsider_denied_everywhere(self):
        """A principal with no edges and no baseline decides nothing."""
        outsider = {"id": OUTSIDER}
        for venue in (self.sports_venue, self.meeting_venue):
            with self.assertRaises(api_errors.ForbiddenError):
                self._gate(outsider, self._venue_id(venue))

    def test_client_principal_denied(self):
        """A client principal (no user) is denied even by the global admin id."""
        with self.assertRaises(api_errors.ForbiddenError) as ctx:
            self._gate(None, self._venue_id(self.sports_venue))
        self.assertIn("Client principals", str(ctx.exception))

    def test_unknown_venue_404_from_the_lookup(self):
        """Booking authority is category-narrowed, so the gate loads the
        venue for every caller: unknown venues surface NotFound for
        everyone (routes 404 phantoms the same way when they resolve
        the booking), and the non-raising check answers False."""
        from campus.common import schema

        missing = schema.CampusID("uid-venue-zzzzzzzz")
        with self.assertRaises(api_errors.NotFoundError):
            self._gate({"id": ADMIN}, missing)
        with self.assertRaises(api_errors.NotFoundError):
            self._gate({"id": SPORTS_ADMIN}, missing)
        with self.assertRaises(api_errors.NotFoundError):
            self._gate({"id": OUTSIDER}, missing)
        self.assertFalse(self._has({"id": ADMIN}, missing))
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


if __name__ == "__main__":
    unittest.main()
